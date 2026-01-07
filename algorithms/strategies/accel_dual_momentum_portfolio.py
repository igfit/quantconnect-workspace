from AlgorithmImports import *

class AccelDualMomentumPortfolio(QCAlgorithm):
    """
    Accelerating Dual Momentum Portfolio Strategy

    Based on extensive research combining:
    - Accelerating Momentum (1m + 3m + 6m returns averaged)
    - Dual Momentum (absolute + relative to SPY)
    - 52-Week High Filter (crash protection)
    - Trend Confirmation (50-day SMA)

    Entry Conditions (ALL must be true):
    1. Accelerating Momentum > 0 (absolute momentum)
    2. Accelerating Momentum > SPY Accelerating Momentum (relative)
    3. Price > 50-day SMA (trend confirmation)
    4. Price within 25% of 52-week high (near-high filter)

    Exit Conditions (ANY triggers exit):
    1. Accelerating Momentum < 0
    2. Accelerating Momentum < SPY Accelerating Momentum
    3. Price < 50-day SMA

    Position Sizing:
    - Capped equal weight (max 5% per position)
    - Min positions: 5 (else hold more cash)
    - Max positions: 20

    Rebalance: Weekly (Friday close signals, Monday open execution)

    Universe: 28 stocks (22 high-beta momentum + 6 stable large-caps)

    Target Performance:
    - CAGR: 30-50%
    - Max Drawdown: 15-20%
    - Sharpe: > 1.0
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # === PARAMETERS ===
        self.max_position_pct = 0.05  # 5% max per position
        self.min_positions = 5
        self.max_positions = 20
        self.near_high_threshold = 0.25  # Within 25% of 52-week high

        # Lookback periods (trading days)
        self.lookback_1m = 21   # ~1 month
        self.lookback_3m = 63   # ~3 months
        self.lookback_6m = 126  # ~6 months
        self.lookback_52w = 252 # ~1 year for 52-week high
        self.sma_period = 50    # 50-day SMA

        # === UNIVERSE ===
        # High-Beta Momentum (22 stocks)
        self.high_beta = [
            "NVDA", "TSLA", "AMD", "META", "AVGO", "CRM", "NOW", "ADBE", "PANW", "CRWD",  # Tech Growth
            "AMAT", "LRCX", "MRVL",  # Semiconductors
            "AMZN", "NFLX", "BKNG",  # Consumer Discretionary
            "COIN", "HOOD",  # Fintech
            "FSLR", "ENPH",  # Energy
            "UBER", "ABNB"   # Industrial
        ]

        # Stable Large-Caps (6 stocks)
        self.stable = ["AAPL", "MSFT", "GOOGL", "V", "MA", "UNH"]

        # Full universe
        self.universe_tickers = self.high_beta + self.stable

        # === ADD SECURITIES ===
        self.symbols = {}
        for ticker in self.universe_tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            self.symbols[ticker] = equity.symbol

        # Add SPY as benchmark
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # === DATA STRUCTURES ===
        # Price history windows for each symbol
        self.price_windows = {}
        window_size = self.lookback_52w + 10  # Extra buffer for 52-week high

        for ticker, symbol in self.symbols.items():
            self.price_windows[ticker] = RollingWindow[float](window_size)

        # SPY price window
        self.spy_prices = RollingWindow[float](window_size)

        # === INDICATORS ===
        # 50-day SMA for each symbol
        self.sma_indicators = {}
        for ticker, symbol in self.symbols.items():
            self.sma_indicators[ticker] = self.sma(symbol, self.sma_period, Resolution.DAILY)

        # SPY SMA
        self.spy_sma = self.sma(self.spy, self.sma_period, Resolution.DAILY)

        # === REBALANCING ===
        self.last_rebalance = self.time
        self.rebalance_days = 5  # Weekly

        # Track active positions and signals
        self.active_signals = {}

        # === WARMUP ===
        self.set_warm_up(self.lookback_52w + 20)

        # === SCHEDULED REBALANCING ===
        # Rebalance every Monday at market open
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

    def on_data(self, data):
        """Update price windows with new data"""
        if self.is_warming_up:
            return

        # Update all price windows
        for ticker, symbol in self.symbols.items():
            if data.bars.contains_key(symbol):
                self.price_windows[ticker].add(data.bars[symbol].close)

        if data.bars.contains_key(self.spy):
            self.spy_prices.add(data.bars[self.spy].close)

    def calculate_return(self, window, lookback):
        """Calculate return over specified lookback period"""
        if not window.is_ready or window.count < lookback + 1:
            return None

        current = window[0]
        past = window[lookback]

        if past == 0:
            return None

        return (current - past) / past

    def calculate_accel_momentum(self, window):
        """
        Calculate Accelerating Momentum Score
        Formula: (1-month return + 3-month return + 6-month return) / 3
        """
        ret_1m = self.calculate_return(window, self.lookback_1m)
        ret_3m = self.calculate_return(window, self.lookback_3m)
        ret_6m = self.calculate_return(window, self.lookback_6m)

        if ret_1m is None or ret_3m is None or ret_6m is None:
            return None

        return (ret_1m + ret_3m + ret_6m) / 3

    def calculate_52w_high(self, window):
        """Calculate 52-week high from price window"""
        if not window.is_ready or window.count < self.lookback_52w:
            return None

        high = 0
        for i in range(self.lookback_52w):
            if window[i] > high:
                high = window[i]

        return high

    def get_signal(self, ticker):
        """
        Determine if a stock has a valid entry/hold signal

        Returns: (has_signal, reason) tuple
        """
        window = self.price_windows.get(ticker)
        symbol = self.symbols.get(ticker)
        sma = self.sma_indicators.get(ticker)

        if window is None or not window.is_ready:
            return False, "No data"

        if sma is None or not sma.is_ready:
            return False, "SMA not ready"

        current_price = window[0]

        # Calculate accelerating momentum
        accel_mom = self.calculate_accel_momentum(window)
        if accel_mom is None:
            return False, "Momentum calc failed"

        # Calculate SPY accelerating momentum
        spy_accel_mom = self.calculate_accel_momentum(self.spy_prices)
        if spy_accel_mom is None:
            return False, "SPY momentum calc failed"

        # Calculate 52-week high
        high_52w = self.calculate_52w_high(window)
        if high_52w is None:
            return False, "52WH calc failed"

        # Check distance from 52-week high
        distance_from_high = (high_52w - current_price) / high_52w if high_52w > 0 else 1

        # === ENTRY/HOLD CONDITIONS ===

        # 1. Absolute momentum: AccelMom > 0
        abs_momentum = accel_mom > 0

        # 2. Relative momentum: AccelMom > SPY AccelMom
        rel_momentum = accel_mom > spy_accel_mom

        # 3. Trend confirmation: Price > 50 SMA
        trend_confirm = current_price > sma.current.value

        # 4. Near 52-week high: Within 25%
        near_high = distance_from_high <= self.near_high_threshold

        # All conditions must be true
        if not abs_momentum:
            return False, "Abs Mom < 0"
        if not rel_momentum:
            return False, "Rel Mom < SPY"
        if not trend_confirm:
            return False, "Below 50 SMA"
        if not near_high:
            return False, f"Far from 52WH ({distance_from_high*100:.1f}%)"

        return True, f"AccelMom={accel_mom*100:.1f}%"

    def rebalance(self):
        """Weekly rebalancing logic"""
        if self.is_warming_up:
            return

        # Collect all signals
        signals = []

        for ticker in self.universe_tickers:
            has_signal, reason = self.get_signal(ticker)

            if has_signal:
                # Calculate momentum score for ranking
                accel_mom = self.calculate_accel_momentum(self.price_windows[ticker])
                signals.append({
                    'ticker': ticker,
                    'symbol': self.symbols[ticker],
                    'accel_mom': accel_mom,
                    'reason': reason
                })

        # Sort by accelerating momentum (highest first)
        signals.sort(key=lambda x: x['accel_mom'], reverse=True)

        # Limit to max positions
        top_signals = signals[:self.max_positions]

        self.debug(f"=== REBALANCE {self.time.strftime('%Y-%m-%d')} ===")
        self.debug(f"Signals: {len(signals)} passed, taking top {len(top_signals)}")

        # Get target tickers
        target_tickers = {s['ticker'] for s in top_signals}

        # === EXIT POSITIONS NOT IN SIGNALS ===
        for ticker, symbol in self.symbols.items():
            if self.portfolio[symbol].invested and ticker not in target_tickers:
                self.liquidate(symbol, f"Signal lost for {ticker}")
                self.debug(f"  EXIT: {ticker}")

        # === CALCULATE POSITION SIZES ===
        if len(top_signals) == 0:
            self.debug("  No signals - holding cash")
            return

        # Equal weight, capped at max_position_pct
        num_positions = len(top_signals)
        equal_weight = 1.0 / num_positions
        position_size = min(equal_weight, self.max_position_pct)

        # If we have fewer than min_positions, reduce exposure
        if num_positions < self.min_positions:
            # Scale down to limit risk with few positions
            total_exposure = num_positions * position_size
            self.debug(f"  Only {num_positions} signals (< {self.min_positions} min), exposure: {total_exposure*100:.1f}%")

        # === ENTER/ADJUST POSITIONS ===
        for sig in top_signals:
            ticker = sig['ticker']
            symbol = sig['symbol']

            current_pct = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value

            # Only adjust if significantly different (> 1% difference)
            if abs(current_pct - position_size) > 0.01:
                self.set_holdings(symbol, position_size)
                self.debug(f"  {'ENTER' if current_pct == 0 else 'ADJUST'}: {ticker} @ {position_size*100:.1f}% (AccelMom: {sig['accel_mom']*100:.1f}%)")

        # Log portfolio summary
        invested_count = sum(1 for s in self.symbols.values() if self.portfolio[s].invested)
        cash_pct = self.portfolio.cash / self.portfolio.total_portfolio_value * 100
        self.debug(f"  Portfolio: {invested_count} positions, {cash_pct:.1f}% cash")

    def on_end_of_algorithm(self):
        """Log final statistics"""
        self.debug("=== FINAL PORTFOLIO ===")
        for ticker, symbol in self.symbols.items():
            if self.portfolio[symbol].invested:
                pnl = self.portfolio[symbol].unrealized_profit_percent * 100
                self.debug(f"  {ticker}: {pnl:.1f}% unrealized P&L")
