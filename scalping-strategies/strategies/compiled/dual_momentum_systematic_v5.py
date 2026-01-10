"""
Dual Momentum Systematic v5 - Two-Stage Momentum

Insight: Use DIFFERENT lookbacks for universe selection vs trading:
- 12-month momentum to define "momentum universe" (quarterly refresh)
- 3-month momentum for trade signals (daily)

This is more realistic:
- Longer lookback for universe = more stable, less whipsaw
- Shorter lookback for signals = responsive entries/exits
- Quarterly refresh = manageable turnover
"""

from AlgorithmImports import *

class DualMomentumSystematicV5(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Broad universe
        self.universe_tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "NVDA", "AMD", "INTC", "QCOM", "AVGO", "TXN", "MU",
            "CRM", "ADBE", "ORCL", "NOW", "INTU",
            "TSLA", "NFLX", "BKNG",
            "COST", "HD", "LOW", "TGT", "NKE", "SBUX",
            "UNH", "JNJ", "PFE", "ABBV", "LLY",
            "V", "MA", "JPM", "GS", "MS",
            "DIS", "CMCSA", "T", "VZ"
        ]

        # Parameters
        self.universe_lookback = 252  # 12-month for universe selection
        self.signal_lookback = 63     # 3-month for trade signals
        self.rsi_period = 14
        self.rsi_threshold = 50
        self.trailing_stop_pct = 0.10
        self.base_risk_per_trade = 1500
        self.max_positions = 6
        self.top_n_universe = 15  # Top 15 by 12-month momentum

        # State
        self.symbols = {}
        self.highest_prices = {}
        self.entry_prices = {}
        self.selected_universe = set()  # Quarterly updated

        # Indicators
        self.mom_long = {}   # 12-month momentum (universe)
        self.mom_short = {}  # 3-month momentum (signals)
        self.rsi_indicators = {}
        self.atr_indicators = {}

        # Add SPY
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_roc_long = self.rocp(self.spy, self.universe_lookback, Resolution.DAILY)
        self.spy_roc_short = self.rocp(self.spy, self.signal_lookback, Resolution.DAILY)

        # Add universe stocks
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                symbol = equity.symbol
                self.symbols[ticker] = symbol

                self.mom_long[symbol] = self.rocp(symbol, self.universe_lookback, Resolution.DAILY)
                self.mom_short[symbol] = self.rocp(symbol, self.signal_lookback, Resolution.DAILY)
                self.rsi_indicators[symbol] = self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY)
                self.atr_indicators[symbol] = self.atr(symbol, 14, MovingAverageType.WILDERS, Resolution.DAILY)
            except Exception as e:
                self.debug(f"Could not add {ticker}: {e}")

        # Schedule quarterly universe refresh
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.refresh_universe
        )

        self.set_warm_up(280, Resolution.DAILY)  # Need 252 days
        self.set_benchmark("SPY")

    def refresh_universe(self):
        """Quarterly: Select top 15 by 12-month momentum"""
        if self.is_warming_up:
            return

        # Rank by 12-month momentum
        rankings = []
        for ticker, symbol in self.symbols.items():
            if symbol not in self.mom_long or not self.mom_long[symbol].is_ready:
                continue
            mom = self.mom_long[symbol].current.value
            rankings.append((symbol, mom))

        rankings.sort(key=lambda x: x[1], reverse=True)
        self.selected_universe = set(s[0] for s in rankings[:self.top_n_universe])

        # Log the selected universe
        self.debug(f"Universe refreshed: {[str(s) for s in list(self.selected_universe)[:6]]}")

    def on_data(self, data):
        if self.is_warming_up:
            return

        if not self.spy_sma.is_ready or not self.spy_roc_short.is_ready:
            return

        if self.spy not in data or data[self.spy] is None:
            return

        # Initial universe refresh if needed
        if len(self.selected_universe) == 0:
            self.refresh_universe()

        spy_price = data[self.spy].close
        spy_mom = self.spy_roc_short.current.value
        in_bull_market = spy_price > self.spy_sma.current.value

        if not in_bull_market:
            for symbol in list(self.highest_prices.keys()):
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol, "Bear market")
            self.highest_prices.clear()
            self.entry_prices.clear()
            return

        # Check exits
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

            # Trailing stop
            stop_price = self.highest_prices[symbol] * (1 - self.trailing_stop_pct)
            if current_price < stop_price:
                should_exit = True

            # Lost SHORT-TERM momentum (3-month)
            if symbol in self.mom_short and self.mom_short[symbol].is_ready:
                if self.mom_short[symbol].current.value < 0:
                    should_exit = True

            # Dropped out of selected universe
            if symbol not in self.selected_universe:
                should_exit = True

            if should_exit:
                self.liquidate(symbol)
                del self.highest_prices[symbol]
                if symbol in self.entry_prices:
                    del self.entry_prices[symbol]

        # Count positions
        current_positions = len([s for s in self.highest_prices if self.portfolio[s].invested])

        # Only consider stocks in selected universe
        candidates = []
        for symbol in self.selected_universe:
            if symbol not in self.mom_short or not self.mom_short[symbol].is_ready:
                continue
            if symbol not in self.rsi_indicators or not self.rsi_indicators[symbol].is_ready:
                continue
            if symbol not in self.atr_indicators or not self.atr_indicators[symbol].is_ready:
                continue
            if symbol not in data or data[symbol] is None:
                continue

            mom = self.mom_short[symbol].current.value
            rsi = self.rsi_indicators[symbol].current.value
            atr_val = self.atr_indicators[symbol].current.value
            price = data[symbol].close

            # Use SHORT-TERM momentum for trade signals
            if mom > 0 and mom > spy_mom and rsi > self.rsi_threshold:
                candidates.append((symbol, mom, price, atr_val))

        candidates.sort(key=lambda x: x[1], reverse=True)

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
