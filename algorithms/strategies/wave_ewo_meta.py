from AlgorithmImports import *

class WaveEWO_META(QCAlgorithm):
    """
    Wave-EWO on META - Testing large-cap tech with high volatility
    Note: Ticker changed from FB to META in June 2022
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.ticker = "META"
        self.symbol = self.add_equity(self.ticker, Resolution.DAILY).symbol

        # EWO params
        self.fast_period = 5
        self.slow_period = 34

        # RSI filter
        self.rsi_period = 14
        self.rsi_entry_threshold = 40
        self.rsi_exit_threshold = 30

        # Indicators
        self.sma_fast = self.sma(self.symbol, self.fast_period, Resolution.DAILY)
        self.sma_slow = self.sma(self.symbol, self.slow_period, Resolution.DAILY)
        self.rsi_indicator = self.rsi(self.symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY)

        self.ewo = None
        self.prev_ewo = None

        self.set_warm_up(50, Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_data(self, data):
        if self.is_warming_up or self.symbol not in data or data[self.symbol] is None:
            return
        if not self.sma_fast.is_ready or not self.sma_slow.is_ready or not self.rsi_indicator.is_ready:
            return

        self.ewo = self.sma_fast.current.value - self.sma_slow.current.value
        rsi_val = self.rsi_indicator.current.value

        if self.prev_ewo is not None:
            crossed_bullish = self.prev_ewo < 0 and self.ewo >= 0
            crossed_bearish = self.prev_ewo >= 0 and self.ewo < 0

            if crossed_bullish and rsi_val >= self.rsi_entry_threshold:
                if not self.portfolio[self.symbol].invested:
                    self.set_holdings(self.symbol, 1.0)

            elif self.portfolio[self.symbol].invested:
                if crossed_bearish or rsi_val < self.rsi_exit_threshold:
                    self.liquidate(self.symbol)

        self.prev_ewo = self.ewo
