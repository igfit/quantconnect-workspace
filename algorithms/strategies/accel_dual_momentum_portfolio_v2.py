from AlgorithmImports import *

class AccelDualMomentumPortfolioV2(QCAlgorithm):
    """
    Accelerating Dual Momentum Portfolio Strategy - V2 (Less Restrictive)

    Changes from V1:
    - Relaxed entry conditions (only 2 required, others used for ranking)
    - Increased near-high threshold to 40%
    - Increased max position size to 8%
    - More aggressive exposure

    Entry Conditions (REQUIRED):
    1. Accelerating Momentum > 0 (absolute momentum)
    2. Price > 50-day SMA (trend confirmation)

    Ranking Factors (for position selection):
    - Accelerating Momentum value (higher is better)
    - Bonus for: AccelMom > SPY
    - Bonus for: Near 52-week high

    Exit Conditions (ANY triggers exit):
    1. Accelerating Momentum < 0
    2. Price < 50-day SMA

    Position Sizing:
    - Capped equal weight (max 8% per position)
    - Min positions: 5
    - Max positions: 15
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # === PARAMETERS (ADJUSTED) ===
        self.max_position_pct = 0.08  # Increased from 5% to 8%
        self.min_positions = 5
        self.max_positions = 15  # Reduced from 20 to concentrate more
        self.near_high_threshold = 0.40  # Relaxed from 25% to 40%

        # Lookback periods (trading days)
        self.lookback_1m = 21   # ~1 month
        self.lookback_3m = 63   # ~3 months
        self.lookback_6m = 126  # ~6 months
        self.lookback_52w = 252 # ~1 year for 52-week high
        self.sma_period = 50    # 50-day SMA

        # === UNIVERSE ===
        # High-Beta Momentum (22 stocks)
        self.high_beta = [
            "NVDA", "TSLA", "AMD", "META", "AVGO", "CRM", "NOW", "ADBE", "PANW", "CRWD",
            "AMAT", "LRCX", "MRVL",
            "AMZN", "NFLX", "BKNG",
            "COIN", "HOOD",
            "FSLR", "ENPH",
            "UBER", "ABNB"
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
        self.price_windows = {}
        window_size = self.lookback_52w + 10

        for ticker, symbol in self.symbols.items():
            self.price_windows[ticker] = RollingWindow[float](window_size)

        self.spy_prices = RollingWindow[float](window_size)

        # === INDICATORS ===
        self.sma_indicators = {}
        for ticker, symbol in self.symbols.items():
            self.sma_indicators[ticker] = self.sma(symbol, self.sma_period, Resolution.DAILY)

        self.spy_sma = self.sma(self.spy, self.sma_period, Resolution.DAILY)

        # === WARMUP ===
        self.set_warm_up(self.lookback_52w + 20)

        # === SCHEDULED REBALANCING ===
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

    def on_data(self, data):
        """Update price windows with new data"""
        if self.is_warming_up:
            return

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
        """Calculate Accelerating Momentum Score"""
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

    def get_signal_score(self, ticker):
        """
        Calculate signal score for ranking.
        Returns: (passes_entry, score, reason)
        - passes_entry: True if stock passes minimum entry conditions
        - score: Ranking score for position selection
        """
        window = self.price_windows.get(ticker)
        symbol = self.symbols.get(ticker)
        sma = self.sma_indicators.get(ticker)

        if window is None or not window.is_ready:
            return False, 0, "No data"

        if sma is None or not sma.is_ready:
            return False, 0, "SMA not ready"

        current_price = window[0]

        # Calculate accelerating momentum
        accel_mom = self.calculate_accel_momentum(window)
        if accel_mom is None:
            return False, 0, "Momentum calc failed"

        # Calculate SPY accelerating momentum
        spy_accel_mom = self.calculate_accel_momentum(self.spy_prices)
        if spy_accel_mom is None:
            return False, 0, "SPY momentum calc failed"

        # Calculate 52-week high
        high_52w = self.calculate_52w_high(window)
        distance_from_high = (high_52w - current_price) / high_52w if high_52w and high_52w > 0 else 1

        # === REQUIRED CONDITIONS (must pass) ===
        abs_momentum = accel_mom > 0
        trend_confirm = current_price > sma.current.value

        if not abs_momentum:
            return False, 0, "Abs Mom < 0"
        if not trend_confirm:
            return False, 0, "Below 50 SMA"

        # === CALCULATE RANKING SCORE ===
        score = accel_mom  # Base score is accelerating momentum

        # Bonus for beating SPY momentum
        if accel_mom > spy_accel_mom:
            score += 0.05  # 5% bonus

        # Bonus for being near 52-week high
        if distance_from_high <= self.near_high_threshold:
            score += 0.03  # 3% bonus

        return True, score, f"AccelMom={accel_mom*100:.1f}%"

    def rebalance(self):
        """Weekly rebalancing logic"""
        if self.is_warming_up:
            return

        # Collect all signals
        signals = []

        for ticker in self.universe_tickers:
            passes, score, reason = self.get_signal_score(ticker)

            if passes:
                signals.append({
                    'ticker': ticker,
                    'symbol': self.symbols[ticker],
                    'score': score,
                    'reason': reason
                })

        # Sort by score (highest first)
        signals.sort(key=lambda x: x['score'], reverse=True)

        # Take top positions
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

        # Equal weight with higher cap
        num_positions = len(top_signals)
        equal_weight = 1.0 / num_positions
        position_size = min(equal_weight, self.max_position_pct)

        # Total target exposure
        total_exposure = num_positions * position_size
        self.debug(f"  Target exposure: {total_exposure*100:.1f}% across {num_positions} positions")

        # === ENTER/ADJUST POSITIONS ===
        for sig in top_signals:
            ticker = sig['ticker']
            symbol = sig['symbol']

            current_pct = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value

            if abs(current_pct - position_size) > 0.01:
                self.set_holdings(symbol, position_size)
                action = 'ENTER' if current_pct == 0 else 'ADJUST'
                self.debug(f"  {action}: {ticker} @ {position_size*100:.1f}% (Score: {sig['score']*100:.1f}%)")

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
