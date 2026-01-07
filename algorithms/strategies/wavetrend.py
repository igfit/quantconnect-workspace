from AlgorithmImports import *
import numpy as np


class WaveTrendStrategy(QCAlgorithm):
    """
    WaveTrend Oscillator Strategy

    Strategy:
        - Go long when WaveTrend crosses up from oversold zone (<-60)
        - Exit when WaveTrend crosses down from overbought zone (>+60)

    Based on LazyBear's WaveTrend Oscillator.

    Parameters:
        - channel_length: 10 (n1)
        - average_length: 21 (n2)
        - oversold: -60
        - overbought: 60

    Universe: SPY
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        # Add equity
        self.symbol = self.add_equity("SPY", Resolution.DAILY).symbol

        # WaveTrend parameters
        self.n1 = 10  # Channel length
        self.n2 = 21  # Average length
        self.overbought = 60
        self.oversold = -60

        # Rolling windows for calculation
        self.hlc3_window = RollingWindow[float](max(self.n1, self.n2) + 50)
        self.esa_window = RollingWindow[float](self.n1 + 50)
        self.d_window = RollingWindow[float](self.n1 + 50)
        self.ci_window = RollingWindow[float](self.n2 + 50)
        self.wt1_window = RollingWindow[float](5)

        # Previous values for crossover detection
        self.prev_wt1 = None
        self.prev_wt2 = None

        # Warm up
        self.set_warm_up(100, Resolution.DAILY)

        # Set benchmark
        self.set_benchmark("SPY")

    def calculate_ema(self, values, period):
        """Calculate EMA of a list of values"""
        if len(values) < period:
            return None
        multiplier = 2 / (period + 1)
        ema = values[0]
        for val in values[1:]:
            ema = (val - ema) * multiplier + ema
        return ema

    def on_data(self, data):
        if self.is_warming_up:
            return

        if self.symbol not in data or data[self.symbol] is None:
            return

        bar = data[self.symbol]
        hlc3 = (bar.high + bar.low + bar.close) / 3
        self.hlc3_window.add(hlc3)

        if self.hlc3_window.count < self.n1 + self.n2:
            return

        # Get HLC3 values (reversed to chronological order)
        hlc3_vals = [self.hlc3_window[i] for i in range(min(self.hlc3_window.count, 50))]
        hlc3_vals.reverse()

        # Calculate ESA = EMA(HLC3, n1)
        esa = self.calculate_ema(hlc3_vals[-self.n1-10:], self.n1)
        if esa is None:
            return

        self.esa_window.add(esa)

        # Calculate D = EMA(|HLC3 - ESA|, n1)
        diff = abs(hlc3 - esa)
        self.d_window.add(diff)

        if self.d_window.count < self.n1:
            return

        d_vals = [self.d_window[i] for i in range(min(self.d_window.count, 20))]
        d_vals.reverse()
        d = self.calculate_ema(d_vals, self.n1)

        if d is None or d == 0:
            return

        # Calculate CI = (HLC3 - ESA) / (0.015 * D)
        ci = (hlc3 - esa) / (0.015 * d)
        self.ci_window.add(ci)

        if self.ci_window.count < self.n2:
            return

        # Calculate WT1 = EMA(CI, n2)
        ci_vals = [self.ci_window[i] for i in range(min(self.ci_window.count, 30))]
        ci_vals.reverse()
        wt1 = self.calculate_ema(ci_vals, self.n2)

        if wt1 is None:
            return

        self.wt1_window.add(wt1)

        if self.wt1_window.count < 4:
            return

        # Calculate WT2 = SMA(WT1, 4)
        wt1_vals = [self.wt1_window[i] for i in range(4)]
        wt2 = np.mean(wt1_vals)

        # Trading logic
        if self.prev_wt1 is not None and self.prev_wt2 is not None:
            # Buy signal: WT1 crosses above WT2 while in oversold zone
            prev_below = self.prev_wt1 < self.prev_wt2
            curr_above = wt1 > wt2
            in_oversold = wt1 < self.oversold or self.prev_wt1 < self.oversold

            # Sell signal: WT1 crosses below WT2 while in overbought zone
            prev_above = self.prev_wt1 > self.prev_wt2
            curr_below = wt1 < wt2
            in_overbought = wt1 > self.overbought or self.prev_wt1 > self.overbought

            if prev_below and curr_above and in_oversold:
                if not self.portfolio[self.symbol].invested:
                    self.set_holdings(self.symbol, 1.0)
                    self.debug(f"{self.time}: BUY - WaveTrend cross up from oversold (WT1: {wt1:.2f})")

            elif prev_above and curr_below and in_overbought:
                if self.portfolio[self.symbol].invested:
                    self.liquidate(self.symbol)
                    self.debug(f"{self.time}: SELL - WaveTrend cross down from overbought (WT1: {wt1:.2f})")

        self.prev_wt1 = wt1
        self.prev_wt2 = wt2

    def on_end_of_algorithm(self):
        self.log(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
