from AlgorithmImports import *

class HighFlyerAggressive(QCAlgorithm):
    """
    High Flyer Aggressive Strategy

    Hypothesis: Focus on the absolute highest momentum stocks
    with aggressive 3-month lookback. Accept high volatility.

    Universe: Small set of proven high-beta winners
    Signal: 3-month return > 20%, Price > 20 SMA
    Positions: Top 2 only (50% each) for maximum concentration
    Rebalance: Bi-weekly (more active for high-beta)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # === PARAMETERS ===
        self.num_positions = 2  # ULTRA CONCENTRATED
        self.lookback = 63  # 3 months
        self.min_return = 0.20  # Must have 20%+ return
        self.sma_period = 20  # Faster SMA for volatile stocks

        # === UNIVERSE - Only proven high-flyers ===
        self.high_flyers = [
            "NVDA",   # AI leader
            "TSLA",   # EV/AI leader
            "AMD",    # AI chips
            "AVGO",   # AI networking
            "META",   # AI/social
            "COIN",   # Crypto proxy
            "MSTR",   # Bitcoin proxy
            "SMCI",   # AI servers
            "ARM",    # AI chips
            "PLTR",   # AI software
        ]

        # === ADD SECURITIES ===
        self.symbols = {}
        for ticker in self.high_flyers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                self.symbols[ticker] = equity.symbol
            except:
                self.debug(f"Could not add {ticker}")

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # === DATA STRUCTURES ===
        self.price_windows = {}
        window_size = self.lookback + 10

        for ticker in self.symbols.keys():
            self.price_windows[ticker] = RollingWindow[float](window_size)

        # === INDICATORS ===
        self.sma_indicators = {}
        for ticker, symbol in self.symbols.items():
            self.sma_indicators[ticker] = self.sma(symbol, self.sma_period, Resolution.DAILY)

        # === WARMUP ===
        self.set_warm_up(self.lookback + 20)

        # === BI-WEEKLY REBALANCING ===
        self.last_rebalance = None
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open(self.spy, 30),
            self.check_rebalance
        )

    def on_data(self, data):
        if self.is_warming_up:
            return

        for ticker, symbol in self.symbols.items():
            if data.bars.contains_key(symbol):
                self.price_windows[ticker].add(data.bars[symbol].close)

    def check_rebalance(self):
        # Bi-weekly rebalancing
        if self.last_rebalance is not None:
            days_since = (self.time - self.last_rebalance).days
            if days_since < 10:
                return

        self.rebalance()
        self.last_rebalance = self.time

    def calculate_return(self, window):
        if not window.is_ready or window.count < self.lookback + 1:
            return None
        current = window[0]
        past = window[self.lookback]
        if past == 0:
            return None
        return (current - past) / past

    def get_signal_score(self, ticker):
        window = self.price_windows.get(ticker)
        sma = self.sma_indicators.get(ticker)

        if window is None or not window.is_ready:
            return False, 0

        if sma is None or not sma.is_ready:
            return False, 0

        current_price = window[0]
        stock_return = self.calculate_return(window)

        if stock_return is None:
            return False, 0

        # High bar: must have 20%+ 3-month return
        if stock_return < self.min_return:
            return False, 0

        # Must be in uptrend
        if current_price <= sma.current.value:
            return False, 0

        return True, stock_return

    def rebalance(self):
        if self.is_warming_up:
            return

        # Collect signals
        signals = []
        for ticker in self.symbols.keys():
            passes, score = self.get_signal_score(ticker)
            if passes:
                signals.append({'ticker': ticker, 'symbol': self.symbols[ticker], 'score': score})

        signals.sort(key=lambda x: x['score'], reverse=True)
        top_signals = signals[:self.num_positions]

        self.debug(f"=== REBALANCE {self.time.strftime('%Y-%m-%d')} ===")
        self.debug(f"High-flyers with 20%+ return: {len(signals)}, Taking top {len(top_signals)}")
        for s in top_signals:
            self.debug(f"  {s['ticker']}: {s['score']*100:.1f}%")

        target_tickers = {s['ticker'] for s in top_signals}

        # Exit positions not in top
        for ticker, symbol in self.symbols.items():
            if self.portfolio[symbol].invested and ticker not in target_tickers:
                self.liquidate(symbol)

        if len(top_signals) == 0:
            self.debug("  No high-flyers meeting criteria - holding cash")
            return

        position_size = 1.0 / len(top_signals)

        for sig in top_signals:
            symbol = sig['symbol']
            current_pct = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value
            if abs(current_pct - position_size) > 0.02:
                self.set_holdings(symbol, position_size)
