from AlgorithmImports import *

class AccelDualMomentumPortfolioV3(QCAlgorithm):
    """
    Accelerating Dual Momentum Portfolio Strategy - V3 (Simpler, Monthly)

    Key Changes:
    - Simpler momentum: 6-month return only (more stable)
    - Monthly rebalancing (less whipsaw, lower costs)
    - Momentum must beat SPY to enter
    - Only exit when trend breaks (Price < 50 SMA)

    Entry Conditions:
    1. 6-month return > 0 (absolute momentum)
    2. 6-month return > SPY 6-month return (relative momentum)
    3. Price > 50-day SMA (trend confirmation)

    Exit Conditions:
    1. Price < 50-day SMA (trend breaks)

    Position Sizing:
    - Equal weight across signals (max 10% per position)
    - Max 12 positions for concentration
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # === PARAMETERS ===
        self.max_position_pct = 0.10  # 10% max per position
        self.max_positions = 12  # More concentrated
        self.lookback = 126  # 6 months only
        self.sma_period = 50

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
        window_size = self.lookback + 10

        for ticker, symbol in self.symbols.items():
            self.price_windows[ticker] = RollingWindow[float](window_size)

        self.spy_prices = RollingWindow[float](window_size)

        # === INDICATORS ===
        self.sma_indicators = {}
        for ticker, symbol in self.symbols.items():
            self.sma_indicators[ticker] = self.sma(symbol, self.sma_period, Resolution.DAILY)

        # === WARMUP ===
        self.set_warm_up(self.lookback + 20)

        # === MONTHLY REBALANCING ===
        self.schedule.on(
            self.date_rules.month_start(self.spy),
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

    def calculate_return(self, window):
        """Calculate 6-month return"""
        if not window.is_ready or window.count < self.lookback + 1:
            return None
        current = window[0]
        past = window[self.lookback]
        if past == 0:
            return None
        return (current - past) / past

    def get_signal_score(self, ticker):
        """
        Returns: (passes_entry, score, reason)
        """
        window = self.price_windows.get(ticker)
        symbol = self.symbols.get(ticker)
        sma = self.sma_indicators.get(ticker)

        if window is None or not window.is_ready:
            return False, 0, "No data"

        if sma is None or not sma.is_ready:
            return False, 0, "SMA not ready"

        current_price = window[0]

        # Calculate 6-month returns
        stock_return = self.calculate_return(window)
        spy_return = self.calculate_return(self.spy_prices)

        if stock_return is None or spy_return is None:
            return False, 0, "Return calc failed"

        # === CONDITIONS ===
        abs_momentum = stock_return > 0
        rel_momentum = stock_return > spy_return
        trend_confirm = current_price > sma.current.value

        # Need all three to enter
        if not abs_momentum:
            return False, 0, "Abs Mom < 0"
        if not rel_momentum:
            return False, 0, "Rel Mom < SPY"
        if not trend_confirm:
            return False, 0, "Below 50 SMA"

        return True, stock_return, f"6mo={stock_return*100:.1f}%"

    def rebalance(self):
        """Monthly rebalancing logic"""
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

        # Sort by 6-month return (highest first)
        signals.sort(key=lambda x: x['score'], reverse=True)

        # Take top positions
        top_signals = signals[:self.max_positions]

        self.debug(f"=== REBALANCE {self.time.strftime('%Y-%m-%d')} ===")
        self.debug(f"Signals: {len(signals)} passed, taking top {len(top_signals)}")

        # Get target tickers
        target_tickers = {s['ticker'] for s in top_signals}

        # === EXIT POSITIONS ===
        for ticker, symbol in self.symbols.items():
            if self.portfolio[symbol].invested and ticker not in target_tickers:
                self.liquidate(symbol, f"Signal lost for {ticker}")
                self.debug(f"  EXIT: {ticker}")

        # === POSITION SIZING ===
        if len(top_signals) == 0:
            self.debug("  No signals - holding cash")
            return

        num_positions = len(top_signals)
        equal_weight = 1.0 / num_positions
        position_size = min(equal_weight, self.max_position_pct)

        total_exposure = num_positions * position_size
        self.debug(f"  Target: {total_exposure*100:.1f}% across {num_positions} positions")

        # === ENTER/ADJUST POSITIONS ===
        for sig in top_signals:
            ticker = sig['ticker']
            symbol = sig['symbol']

            current_pct = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value

            if abs(current_pct - position_size) > 0.01:
                self.set_holdings(symbol, position_size)
                self.debug(f"  {'ENTER' if current_pct == 0 else 'ADJUST'}: {ticker} @ {position_size*100:.1f}%")

        invested_count = sum(1 for s in self.symbols.values() if self.portfolio[s].invested)
        cash_pct = self.portfolio.cash / self.portfolio.total_portfolio_value * 100
        self.debug(f"  Portfolio: {invested_count} positions, {cash_pct:.1f}% cash")
