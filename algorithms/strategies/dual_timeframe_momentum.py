from AlgorithmImports import *

class DualTimeframeMomentum(QCAlgorithm):
    """
    Dual Timeframe Momentum Strategy

    Hypothesis: Requiring BOTH 3-month AND 6-month momentum to be positive
    filters out false signals and reduces whipsaw.

    Signal: 3-month return > 0 AND 6-month return > SPY AND Price > 50 SMA
    Positions: Top 3 stocks (33% each)
    Rebalance: Monthly
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # === PARAMETERS ===
        self.num_positions = 3
        self.lookback_short = 63   # 3 months
        self.lookback_long = 126   # 6 months
        self.sma_period = 50

        # === UNIVERSE ===
        self.universe_tickers = [
            "NVDA", "TSLA", "AMD", "META", "AVGO", "AAPL", "MSFT", "GOOGL", "AMZN",
            "CRM", "NOW", "ADBE", "PANW", "CRWD", "NFLX",
            "AMAT", "LRCX", "MRVL",
            "COIN", "HOOD", "UBER", "ABNB",
            "FSLR", "ENPH",
            "V", "MA", "UNH"
        ]

        # === ADD SECURITIES ===
        self.symbols = {}
        for ticker in self.universe_tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            self.symbols[ticker] = equity.symbol

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # === DATA STRUCTURES ===
        self.price_windows = {}
        window_size = self.lookback_long + 10

        for ticker in self.universe_tickers:
            self.price_windows[ticker] = RollingWindow[float](window_size)

        self.spy_prices = RollingWindow[float](window_size)

        # === INDICATORS ===
        self.sma_indicators = {}
        for ticker, symbol in self.symbols.items():
            self.sma_indicators[ticker] = self.sma(symbol, self.sma_period, Resolution.DAILY)

        # === WARMUP ===
        self.set_warm_up(self.lookback_long + 20)

        # === MONTHLY REBALANCING ===
        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

    def on_data(self, data):
        if self.is_warming_up:
            return

        for ticker, symbol in self.symbols.items():
            if data.bars.contains_key(symbol):
                self.price_windows[ticker].add(data.bars[symbol].close)

        if data.bars.contains_key(self.spy):
            self.spy_prices.add(data.bars[self.spy].close)

    def calculate_return(self, window, lookback):
        if not window.is_ready or window.count < lookback + 1:
            return None
        current = window[0]
        past = window[lookback]
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

        # Calculate both timeframe returns
        return_3m = self.calculate_return(window, self.lookback_short)
        return_6m = self.calculate_return(window, self.lookback_long)
        spy_return_6m = self.calculate_return(self.spy_prices, self.lookback_long)

        if return_3m is None or return_6m is None or spy_return_6m is None:
            return False, 0

        # DUAL CONDITION: Both timeframes must confirm
        short_term_positive = return_3m > 0
        long_term_beats_spy = return_6m > spy_return_6m
        above_sma = current_price > sma.current.value

        if not (short_term_positive and long_term_beats_spy and above_sma):
            return False, 0

        # Score based on combined momentum
        combined_score = (return_3m + return_6m) / 2
        return True, combined_score

    def rebalance(self):
        if self.is_warming_up:
            return

        # Collect signals
        signals = []
        for ticker in self.universe_tickers:
            passes, score = self.get_signal_score(ticker)
            if passes:
                signals.append({'ticker': ticker, 'symbol': self.symbols[ticker], 'score': score})

        signals.sort(key=lambda x: x['score'], reverse=True)
        top_signals = signals[:self.num_positions]

        self.debug(f"=== REBALANCE {self.time.strftime('%Y-%m-%d')} ===")
        self.debug(f"Dual TF signals: {len(signals)}, Taking top {len(top_signals)}")
        for s in top_signals:
            self.debug(f"  {s['ticker']}: {s['score']*100:.1f}%")

        target_tickers = {s['ticker'] for s in top_signals}

        # Exit positions not in top
        for ticker, symbol in self.symbols.items():
            if self.portfolio[symbol].invested and ticker not in target_tickers:
                self.liquidate(symbol)

        if len(top_signals) == 0:
            self.debug("  No stocks pass dual timeframe filter - holding cash")
            return

        position_size = 1.0 / len(top_signals)

        for sig in top_signals:
            symbol = sig['symbol']
            current_pct = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value
            if abs(current_pct - position_size) > 0.02:
                self.set_holdings(symbol, position_size)
