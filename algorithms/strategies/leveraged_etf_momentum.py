from AlgorithmImports import *

class LeveragedETFMomentum(QCAlgorithm):
    """
    Leveraged ETF Momentum Strategy

    Hypothesis: Use leveraged ETFs (3x) with momentum timing
    to amplify returns during uptrends, cash during downtrends.

    Universe: TQQQ (3x QQQ), UPRO (3x SPY), SOXL (3x Semiconductors)
    Signal: 1-month return > 0, Price > 20 SMA (faster for leveraged)
    Positions: Top 2 leveraged ETFs (50% each)
    Rebalance: Weekly (faster for leveraged products)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # === PARAMETERS ===
        self.num_positions = 2
        self.lookback = 21  # 1 month - faster for leveraged
        self.sma_period = 20  # Faster SMA

        # === LEVERAGED ETFs ===
        self.leveraged_etfs = [
            "TQQQ",   # 3x QQQ (Nasdaq)
            "UPRO",   # 3x SPY (S&P 500)
            "SOXL",   # 3x Semiconductors
            "TECL",   # 3x Technology
            "FAS",    # 3x Financials
        ]

        # === ADD SECURITIES ===
        self.symbols = {}
        for ticker in self.leveraged_etfs:
            equity = self.add_equity(ticker, Resolution.DAILY)
            self.symbols[ticker] = equity.symbol

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # === DATA STRUCTURES ===
        self.price_windows = {}
        window_size = self.lookback + 10

        for ticker in self.leveraged_etfs:
            self.price_windows[ticker] = RollingWindow[float](window_size)

        # === INDICATORS ===
        self.sma_indicators = {}
        for ticker, symbol in self.symbols.items():
            self.sma_indicators[ticker] = self.sma(symbol, self.sma_period, Resolution.DAILY)

        # === WARMUP ===
        self.set_warm_up(self.lookback + 20)

        # === WEEKLY REBALANCING ===
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

    def on_data(self, data):
        if self.is_warming_up:
            return

        for ticker, symbol in self.symbols.items():
            if data.bars.contains_key(symbol):
                self.price_windows[ticker].add(data.bars[symbol].close)

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
        etf_return = self.calculate_return(window)

        if etf_return is None:
            return False, 0

        # Positive momentum and above SMA
        if etf_return <= 0:
            return False, 0
        if current_price <= sma.current.value:
            return False, 0

        return True, etf_return

    def rebalance(self):
        if self.is_warming_up:
            return

        # Collect signals
        signals = []
        for ticker in self.leveraged_etfs:
            passes, score = self.get_signal_score(ticker)
            if passes:
                signals.append({'ticker': ticker, 'symbol': self.symbols[ticker], 'score': score})

        signals.sort(key=lambda x: x['score'], reverse=True)
        top_signals = signals[:self.num_positions]

        self.debug(f"=== REBALANCE {self.time.strftime('%Y-%m-%d')} ===")
        self.debug(f"Leveraged ETF signals: {len(signals)}, Taking top {len(top_signals)}")
        for s in top_signals:
            self.debug(f"  {s['ticker']}: {s['score']*100:.1f}%")

        target_tickers = {s['ticker'] for s in top_signals}

        # Exit positions not in top
        for ticker, symbol in self.symbols.items():
            if self.portfolio[symbol].invested and ticker not in target_tickers:
                self.liquidate(symbol)

        if len(top_signals) == 0:
            self.debug("  No leveraged ETFs with positive momentum - holding cash")
            return

        position_size = 1.0 / len(top_signals)

        for sig in top_signals:
            symbol = sig['symbol']
            current_pct = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value
            if abs(current_pct - position_size) > 0.02:
                self.set_holdings(symbol, position_size)
