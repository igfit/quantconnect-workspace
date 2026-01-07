from AlgorithmImports import *
import numpy as np


class WaveEWONVDA(QCAlgorithm):
    """
    Wave EWO on NVDA - Testing robustness on different high-beta stock
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.ticker = "NVDA"
        self.symbol = self.add_equity(self.ticker, Resolution.DAILY).symbol

        self.fast_period = 5
        self.slow_period = 34
        self.rsi_period = 14
        self.rsi_entry_threshold = 40
        self.rsi_exit_threshold = 30

        self.sma_fast = self.sma(self.symbol, self.fast_period, Resolution.DAILY)
        self.sma_slow = self.sma(self.symbol, self.slow_period, Resolution.DAILY)
        self.rsi_indicator = self.rsi(self.symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY)

        self.ewo = None
        self.prev_ewo = None

        self.set_warm_up(50, Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_data(self, data):
        if self.is_warming_up or self.symbol not in data:
            return
        if data[self.symbol] is None:
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
                    self.debug(f"{self.time}: BUY {self.ticker}")

            elif self.portfolio[self.symbol].invested:
                if crossed_bearish or rsi_val < self.rsi_exit_threshold:
                    self.liquidate(self.symbol)
                    self.debug(f"{self.time}: SELL {self.ticker}")

        self.prev_ewo = self.ewo

    def on_end_of_algorithm(self):
        self.log(f"Wave-EWO NVDA Final: ${self.portfolio.total_portfolio_value:,.2f}")
