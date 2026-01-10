"""
Dual Momentum with Systematic Universe Selection v2

FIXES HINDSIGHT BIAS: Uses a broad, pre-defined universe of large-cap
growth stocks. The dual momentum filter naturally selects winners.

Key Insight: Instead of pre-selecting TSLA/NVDA/AMD, we include them
in a broader universe (40+ stocks) and let the momentum filter choose.
If TSLA/NVDA/AMD were truly the best momentum stocks, the filter would
have selected them anyway - that's the edge, not stock picking.
"""

from AlgorithmImports import *

class DualMomentumSystematicV2(QCAlgorithm):
    """
    Systematic Dual Momentum Strategy v2

    Universe: 40+ large-cap growth/tech stocks (static, known in 2018)
    Filter: Dual momentum dynamically selects top performers
    No hindsight: We don't pick winners, the momentum filter does
    """

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Broad universe - all stocks that existed and were liquid in 2018
        # NOT selected for performance, just for being large tech/growth
        self.universe_tickers = [
            # Mega-cap tech
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            # Semiconductors (all large in 2018)
            "NVDA", "AMD", "INTC", "QCOM", "AVGO", "TXN", "MU",
            # Software/Cloud
            "CRM", "ADBE", "ORCL", "NOW", "INTU",
            # Consumer/EV
            "TSLA", "NFLX", "BKNG",
            # Retail/Consumer
            "COST", "HD", "LOW", "TGT", "NKE", "SBUX",
            # Healthcare
            "UNH", "JNJ", "PFE", "ABBV", "LLY",
            # Financials
            "V", "MA", "JPM", "GS", "MS",
            # Communication
            "DIS", "CMCSA", "T", "VZ"
        ]

        # Parameters
        self.lookback = 63  # 3-month momentum
        self.rsi_period = 14
        self.rsi_threshold = 50
        self.trailing_stop_pct = 0.10
        self.base_risk_per_trade = 1500
        self.max_positions = 6

        # State
        self.symbols = {}
        self.highest_prices = {}
        self.entry_prices = {}

        # Indicators storage - use unique names to avoid QCAlgorithm method shadowing
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

                # Use ROCP (rate of change percent) for comparable momentum
                self.mom_indicators[symbol] = self.rocp(symbol, self.lookback, Resolution.DAILY)
                self.rsi_indicators[symbol] = self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY)
                self.atr_indicators[symbol] = self.atr(symbol, 14, MovingAverageType.WILDERS, Resolution.DAILY)
            except Exception as e:
                self.debug(f"Could not add {ticker}: {e}")

        # Warmup
        self.set_warm_up(210, Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Check data and indicators
        if not self.spy_sma.is_ready or not self.spy_roc.is_ready:
            return

        if self.spy not in data or data[self.spy] is None:
            return

        spy_price = data[self.spy].close
        spy_mom = self.spy_roc.current.value
        in_bull_market = spy_price > self.spy_sma.current.value

        # Bear market - exit all
        if not in_bull_market:
            for symbol in list(self.highest_prices.keys()):
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol, "Bear market")
            self.highest_prices.clear()
            self.entry_prices.clear()
            return

        # Update trailing stops and check exits
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

            if should_exit:
                self.liquidate(symbol, exit_reason)
                del self.highest_prices[symbol]
                if symbol in self.entry_prices:
                    del self.entry_prices[symbol]

        # Count positions
        current_positions = len([s for s in self.highest_prices if self.portfolio[s].invested])

        # Rank all stocks by momentum
        candidates = []
        for ticker, symbol in self.symbols.items():
            if symbol not in self.mom_indicators or not self.mom_indicators[symbol].is_ready:
                continue
            if symbol not in self.rsi_indicators or not self.rsi_indicators[symbol].is_ready:
                continue
            if symbol not in self.atr_indicators or not self.atr_indicators[symbol].is_ready:
                continue
            if symbol not in data or data[symbol] is None:
                continue

            mom = self.mom_indicators[symbol].current.value
            rsi = self.rsi_indicators[symbol].current.value
            atr_val = self.atr_indicators[symbol].current.value
            price = data[symbol].close

            # Dual momentum filter
            absolute_momentum = mom > 0
            relative_momentum = mom > spy_mom
            rsi_confirm = rsi > self.rsi_threshold

            if absolute_momentum and relative_momentum and rsi_confirm:
                candidates.append((symbol, mom, price, atr_val))

        # Sort by momentum descending
        candidates.sort(key=lambda x: x[1], reverse=True)

        # Enter top candidates (that we don't already own)
        for symbol, mom, price, atr_val in candidates:
            if current_positions >= self.max_positions:
                break

            if self.portfolio[symbol].invested:
                continue

            # Calculate position size
            shares = self.calculate_position_size(price, atr_val)
            if shares > 0:
                self.market_order(symbol, shares)
                self.highest_prices[symbol] = price
                self.entry_prices[symbol] = price
                current_positions += 1
                self.debug(f"BUY {symbol}: mom={mom:.2%}, rsi={self.rsi_indicators[symbol].current.value:.1f}")

    def calculate_position_size(self, price, atr_value):
        """ATR-based position sizing"""
        if atr_value <= 0 or price <= 0:
            return 0

        risk_per_share = 2 * atr_value
        shares = int(self.base_risk_per_trade / risk_per_share)

        # Cap at 15% of portfolio
        max_value = self.portfolio.total_portfolio_value * 0.15
        max_shares = int(max_value / price)

        return min(shares, max_shares)
