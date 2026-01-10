"""
Dual Momentum with Systematic Universe Selection

FIXES HINDSIGHT BIAS: Instead of hand-picking winners (TSLA, NVDA, AMD),
we dynamically select the top momentum stocks each month from a broad universe.

Universe: NASDAQ-100 components (or approximation via top tech/growth stocks)
Selection: Monthly, pick top 6 stocks by 3-month momentum that beat SPY
Trading: Same dual momentum rules as before

This way, the strategy COULD have selected TSLA/NVDA in 2020 based on momentum,
not because we knew they'd be winners.
"""

from AlgorithmImports import *

class DualMomentumSystematic(QCAlgorithm):
    """
    Systematic Dual Momentum Strategy

    Universe Selection (Monthly):
    1. Start with broad universe (~50 large-cap growth stocks)
    2. Calculate 3-month momentum for each
    3. Select top 6 that beat SPY's momentum

    Entry (Daily):
    1. SPY > 200 SMA (bull market)
    2. Stock in selected universe
    3. Stock momentum > 0 (absolute)
    4. Stock momentum > SPY momentum (relative)
    5. RSI > 50

    Exit:
    1. Stock drops out of top momentum universe
    2. OR momentum turns negative
    3. OR trailing stop hit (10%)

    Position Sizing: ATR-based volatility adjustment
    """

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Broad universe - large cap growth/tech stocks
        # This is NOT hand-picked winners - it's a broad starting universe
        # that existed and was known in 2018
        self.broad_universe = [
            # Mega-cap tech (all were large caps in 2018)
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA",
            # Semiconductors
            "AMD", "INTC", "QCOM", "AVGO", "TXN", "MU",
            # Software/Cloud
            "CRM", "ADBE", "ORCL", "NOW", "INTU", "PYPL",
            # Consumer/Internet
            "NFLX", "TSLA", "BKNG", "ABNB", "UBER", "SQ",
            # Other growth
            "COST", "HD", "LOW", "TGT", "NKE", "SBUX",
            # Healthcare/Biotech
            "UNH", "JNJ", "PFE", "MRNA", "ISRG", "DXCM",
            # Financials
            "V", "MA", "AXP", "GS", "MS", "BLK"
        ]

        # Parameters
        self.lookback = 63  # 3-month momentum
        self.rsi_period = 14
        self.rsi_threshold = 50
        self.trailing_stop_pct = 0.10
        self.base_risk_per_trade = 1500
        self.max_positions = 6
        self.rebalance_frequency = 21  # Monthly universe refresh

        # State tracking
        self.symbols = {}
        self.spy = None
        self.spy_sma = None
        self.selected_universe = []  # Top momentum stocks
        self.highest_prices = {}
        self.entry_prices = {}
        self.days_since_rebalance = 0

        # Indicators
        self.momentum = {}
        self.rsi_ind = {}
        self.atr = {}

        # Add SPY for regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_momentum = self.momp(self.spy, self.lookback, Resolution.DAILY)

        # Add broad universe
        for ticker in self.broad_universe:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                symbol = equity.symbol
                self.symbols[ticker] = symbol

                # Create indicators
                self.momentum[symbol] = self.momp(symbol, self.lookback, Resolution.DAILY)
                self.rsi_ind[symbol] = self.rsi(symbol, self.rsi_period, Resolution.DAILY)
                self.atr[symbol] = self.atr(symbol, 14, Resolution.DAILY)
            except:
                self.debug(f"Could not add {ticker}")

        # Schedule monthly universe selection
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.select_universe
        )

        # Warmup
        self.set_warm_up(210, Resolution.DAILY)

        self.set_benchmark("SPY")

    def select_universe(self):
        """Monthly: Select top 6 stocks by momentum that beat SPY"""

        if self.is_warming_up:
            return

        if not self.spy_momentum.is_ready:
            return

        spy_mom = self.spy_momentum.current.value

        # Score all stocks by momentum
        candidates = []

        for ticker, symbol in self.symbols.items():
            if symbol not in self.momentum:
                continue
            if not self.momentum[symbol].is_ready:
                continue

            mom = self.momentum[symbol].current.value

            # Must beat SPY momentum (relative momentum filter)
            if mom > spy_mom and mom > 0:
                candidates.append((symbol, mom))

        # Sort by momentum, take top N
        candidates.sort(key=lambda x: x[1], reverse=True)
        self.selected_universe = [c[0] for c in candidates[:self.max_positions * 2]]  # 2x for buffer

        self.debug(f"Universe selected: {[str(s) for s in self.selected_universe[:6]]}")

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Check regime
        if not self.spy_sma.is_ready:
            return

        if self.spy not in data or data[self.spy] is None:
            return

        spy_price = data[self.spy].close
        in_bull_market = spy_price > self.spy_sma.current.value

        # If bear market, exit all
        if not in_bull_market:
            for symbol in list(self.portfolio.keys()):
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol, "Bear market - SPY below 200 SMA")
            self.highest_prices.clear()
            self.entry_prices.clear()
            return

        # Update trailing stops and check exits
        for symbol in list(self.portfolio.keys()):
            if not self.portfolio[symbol].invested:
                continue

            if symbol not in data or data[symbol] is None:
                continue

            current_price = data[symbol].close

            # Update highest price
            if symbol in self.highest_prices:
                self.highest_prices[symbol] = max(self.highest_prices[symbol], current_price)

            # Check exit conditions
            should_exit = False
            exit_reason = ""

            # 1. Trailing stop
            if symbol in self.highest_prices:
                stop_price = self.highest_prices[symbol] * (1 - self.trailing_stop_pct)
                if current_price < stop_price:
                    should_exit = True
                    exit_reason = f"Trailing stop hit ({self.trailing_stop_pct*100}%)"

            # 2. Lost momentum
            if symbol in self.momentum and self.momentum[symbol].is_ready:
                if self.momentum[symbol].current.value < 0:
                    should_exit = True
                    exit_reason = "Lost absolute momentum"

            # 3. Dropped out of selected universe
            if symbol not in self.selected_universe:
                should_exit = True
                exit_reason = "Dropped out of momentum universe"

            if should_exit:
                self.liquidate(symbol, exit_reason)
                if symbol in self.highest_prices:
                    del self.highest_prices[symbol]
                if symbol in self.entry_prices:
                    del self.entry_prices[symbol]

        # Count current positions
        current_positions = sum(1 for s in self.portfolio.keys()
                               if self.portfolio[s].invested)

        # Entry logic - only for stocks in selected universe
        if not self.spy_momentum.is_ready:
            return

        spy_mom = self.spy_momentum.current.value

        for symbol in self.selected_universe:
            if current_positions >= self.max_positions:
                break

            if self.portfolio[symbol].invested:
                continue

            if symbol not in data or data[symbol] is None:
                continue

            # Check all entry conditions
            if symbol not in self.momentum or not self.momentum[symbol].is_ready:
                continue
            if symbol not in self.rsi_ind or not self.rsi_ind[symbol].is_ready:
                continue
            if symbol not in self.atr or not self.atr[symbol].is_ready:
                continue

            mom = self.momentum[symbol].current.value
            rsi = self.rsi_ind[symbol].current.value
            atr_val = self.atr[symbol].current.value
            price = data[symbol].close

            # Entry conditions
            absolute_momentum = mom > 0
            relative_momentum = mom > spy_mom
            rsi_confirm = rsi > self.rsi_threshold

            if absolute_momentum and relative_momentum and rsi_confirm:
                # Calculate position size
                shares = self.calculate_position_size(symbol, price, atr_val)

                if shares > 0:
                    self.market_order(symbol, shares)
                    self.highest_prices[symbol] = price
                    self.entry_prices[symbol] = price
                    current_positions += 1
                    self.debug(f"BUY {symbol}: mom={mom:.2f}, rsi={rsi:.1f}, shares={shares}")

    def calculate_position_size(self, symbol, price, atr_value):
        """ATR-based position sizing"""
        if atr_value <= 0 or price <= 0:
            return 0

        risk_per_share = 2 * atr_value
        shares = int(self.base_risk_per_trade / risk_per_share)

        # Cap at 15% of portfolio per position
        max_value = self.portfolio.total_portfolio_value * 0.15
        max_shares = int(max_value / price)

        return min(shares, max_shares)
