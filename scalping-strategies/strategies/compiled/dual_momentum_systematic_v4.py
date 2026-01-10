"""
Dual Momentum Systematic v4 - Concentrated Top Momentum

Key insight: The hand-picked strategy worked because it concentrated
on the HIGHEST momentum stocks. Let's do that systematically.

Instead of buying any stock that passes dual momentum filter,
ONLY buy the top 6 by momentum ranking. This forces concentration
in the strongest performers while still being systematic.

Also: Exit if stock drops out of top 10 ranking (not just loses momentum)
"""

from AlgorithmImports import *

class DualMomentumSystematicV4(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Broad universe - we'll concentrate in top performers
        self.universe_tickers = [
            # Mega-cap tech
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            # Semiconductors
            "NVDA", "AMD", "INTC", "QCOM", "AVGO", "TXN", "MU",
            # Software/Cloud
            "CRM", "ADBE", "ORCL", "NOW", "INTU",
            # Consumer/EV
            "TSLA", "NFLX", "BKNG",
            # Retail
            "COST", "HD", "LOW", "TGT", "NKE", "SBUX",
            # Healthcare
            "UNH", "JNJ", "PFE", "ABBV", "LLY",
            # Financials
            "V", "MA", "JPM", "GS", "MS",
            # Communication
            "DIS", "CMCSA", "T", "VZ"
        ]

        # Parameters
        self.lookback = 63
        self.rsi_period = 14
        self.rsi_threshold = 50
        self.trailing_stop_pct = 0.10
        self.base_risk_per_trade = 1500
        self.max_positions = 6
        self.top_n_universe = 10  # Only consider top 10 by momentum

        # State
        self.symbols = {}
        self.highest_prices = {}
        self.entry_prices = {}

        # Indicators
        self.mom_indicators = {}
        self.rsi_indicators = {}
        self.atr_indicators = {}

        # Add SPY
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_roc = self.rocp(self.spy, self.lookback, Resolution.DAILY)

        # Add universe stocks
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                symbol = equity.symbol
                self.symbols[ticker] = symbol

                self.mom_indicators[symbol] = self.rocp(symbol, self.lookback, Resolution.DAILY)
                self.rsi_indicators[symbol] = self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY)
                self.atr_indicators[symbol] = self.atr(symbol, 14, MovingAverageType.WILDERS, Resolution.DAILY)
            except Exception as e:
                self.debug(f"Could not add {ticker}: {e}")

        self.set_warm_up(210, Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_data(self, data):
        if self.is_warming_up:
            return

        if not self.spy_sma.is_ready or not self.spy_roc.is_ready:
            return

        if self.spy not in data or data[self.spy] is None:
            return

        spy_price = data[self.spy].close
        spy_mom = self.spy_roc.current.value
        in_bull_market = spy_price > self.spy_sma.current.value

        if not in_bull_market:
            for symbol in list(self.highest_prices.keys()):
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol, "Bear market")
            self.highest_prices.clear()
            self.entry_prices.clear()
            return

        # First, rank ALL stocks by momentum
        all_stocks_ranked = []
        for ticker, symbol in self.symbols.items():
            if symbol not in self.mom_indicators or not self.mom_indicators[symbol].is_ready:
                continue
            if symbol not in data or data[symbol] is None:
                continue

            mom = self.mom_indicators[symbol].current.value
            all_stocks_ranked.append((symbol, mom))

        # Sort by momentum
        all_stocks_ranked.sort(key=lambda x: x[1], reverse=True)
        top_n_symbols = set(s[0] for s in all_stocks_ranked[:self.top_n_universe])

        # Check exits - including if stock drops out of top N
        for symbol in list(self.highest_prices.keys()):
            if not self.portfolio[symbol].invested:
                if symbol in self.highest_prices:
                    del self.highest_prices[symbol]
                continue

            if symbol not in data or data[symbol] is None:
                continue

            current_price = data[symbol].close
            self.highest_prices[symbol] = max(self.highest_prices[symbol], current_price)

            should_exit = False
            exit_reason = ""

            # Trailing stop
            stop_price = self.highest_prices[symbol] * (1 - self.trailing_stop_pct)
            if current_price < stop_price:
                should_exit = True
                exit_reason = "Trailing stop"

            # Lost momentum
            if symbol in self.mom_indicators and self.mom_indicators[symbol].is_ready:
                if self.mom_indicators[symbol].current.value < 0:
                    should_exit = True
                    exit_reason = "Lost momentum"

            # Dropped out of top N - KEY DIFFERENCE
            if symbol not in top_n_symbols:
                should_exit = True
                exit_reason = "Dropped out of top 10"

            if should_exit:
                self.liquidate(symbol, exit_reason)
                del self.highest_prices[symbol]
                if symbol in self.entry_prices:
                    del self.entry_prices[symbol]

        # Count positions
        current_positions = len([s for s in self.highest_prices if self.portfolio[s].invested])

        # Only consider top N stocks for entry
        candidates = []
        for symbol, mom in all_stocks_ranked[:self.top_n_universe]:
            if symbol not in self.rsi_indicators or not self.rsi_indicators[symbol].is_ready:
                continue
            if symbol not in self.atr_indicators or not self.atr_indicators[symbol].is_ready:
                continue
            if symbol not in data or data[symbol] is None:
                continue

            rsi = self.rsi_indicators[symbol].current.value
            atr_val = self.atr_indicators[symbol].current.value
            price = data[symbol].close

            # Still require dual momentum + RSI
            if mom > 0 and mom > spy_mom and rsi > self.rsi_threshold:
                candidates.append((symbol, mom, price, atr_val))

        # Enter top candidates
        for symbol, mom, price, atr_val in candidates:
            if current_positions >= self.max_positions:
                break

            if self.portfolio[symbol].invested:
                continue

            shares = self.calculate_position_size(price, atr_val)
            if shares > 0:
                self.market_order(symbol, shares)
                self.highest_prices[symbol] = price
                self.entry_prices[symbol] = price
                current_positions += 1

    def calculate_position_size(self, price, atr_value):
        if atr_value <= 0 or price <= 0:
            return 0

        risk_per_share = 2 * atr_value
        shares = int(self.base_risk_per_trade / risk_per_share)
        max_value = self.portfolio.total_portfolio_value * 0.15
        max_shares = int(max_value / price)

        return min(shares, max_shares)
