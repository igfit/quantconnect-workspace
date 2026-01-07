from AlgorithmImports import *
import numpy as np


class WaveAdaptive(QCAlgorithm):
    """
    Wave Adaptive - Volatility-adjusted wave indicator with dynamic thresholds

    Modification: ATR-normalized wave oscillator with adaptive entry/exit levels

    Formula:
    - Raw Wave = EMA(fast) - EMA(slow)
    - Normalized Wave = Raw Wave / ATR(14)
    - Dynamic threshold = based on recent wave volatility

    Key features:
    - Normalization makes waves comparable across time
    - High ATR periods require larger waves to trigger signals
    - Low ATR periods can trigger on smaller waves
    - Reduces whipsaws in volatile markets

    Entry: Normalized Wave crosses above dynamic threshold
    Exit: Normalized Wave crosses below -dynamic threshold

    Hypothesis: Volatility adjustment prevents false signals during
                high-volatility regimes while staying responsive in calm markets
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.ticker = "TSLA"
        self.symbol = self.add_equity(self.ticker, Resolution.DAILY).symbol

        # Wave params
        self.fast_period = 8
        self.slow_period = 21
        self.atr_period = 14

        # Adaptive threshold params
        self.wave_lookback = 20  # Period for threshold calculation
        self.threshold_multiplier = 0.5  # How many stdevs for threshold

        # Indicators
        self.ema_fast = self.ema(self.symbol, self.fast_period, Resolution.DAILY)
        self.ema_slow = self.ema(self.symbol, self.slow_period, Resolution.DAILY)
        self.atr_indicator = self.atr(self.symbol, self.atr_period, MovingAverageType.SIMPLE, Resolution.DAILY)

        # Rolling windows
        self.norm_wave_window = RollingWindow[float](self.wave_lookback)

        self.norm_wave = None
        self.prev_norm_wave = None
        self.threshold = 0.5  # Initial threshold

        self.set_warm_up(50, Resolution.DAILY)
        self.set_benchmark("SPY")

    def calculate_adaptive_threshold(self):
        """
        Calculate threshold based on recent wave volatility.
        Higher volatility = higher threshold to filter noise.
        """
        if self.norm_wave_window.count < 10:
            return 0.5  # Default

        waves = [self.norm_wave_window[i] for i in range(self.norm_wave_window.count)]
        stdev = np.std(waves)

        # Threshold = fraction of standard deviation
        # But bounded to reasonable range
        threshold = stdev * self.threshold_multiplier
        threshold = max(0.2, min(1.5, threshold))  # Bound between 0.2 and 1.5

        return threshold

    def on_data(self, data):
        if self.is_warming_up or self.symbol not in data:
            return
        if data[self.symbol] is None:
            return
        if not self.ema_fast.is_ready or not self.ema_slow.is_ready or not self.atr_indicator.is_ready:
            return

        atr_val = self.atr_indicator.current.value
        if atr_val <= 0:
            return

        # Calculate normalized wave
        raw_wave = self.ema_fast.current.value - self.ema_slow.current.value
        self.norm_wave = raw_wave / atr_val

        self.norm_wave_window.add(self.norm_wave)

        # Calculate adaptive threshold
        self.threshold = self.calculate_adaptive_threshold()

        if self.prev_norm_wave is not None:
            # Dynamic threshold crossover signals
            crossed_bullish = self.prev_norm_wave < self.threshold and self.norm_wave >= self.threshold
            crossed_bearish = self.prev_norm_wave >= -self.threshold and self.norm_wave < -self.threshold

            # Also check zero crossover for confirmation
            zero_cross_bull = self.prev_norm_wave < 0 and self.norm_wave >= 0
            zero_cross_bear = self.prev_norm_wave >= 0 and self.norm_wave < 0

            if crossed_bullish or (zero_cross_bull and self.norm_wave > self.threshold * 0.5):
                if not self.portfolio[self.symbol].invested:
                    self.set_holdings(self.symbol, 1.0)
                    self.debug(f"{self.time}: BUY {self.ticker} - Wave: {self.norm_wave:.2f}, Thresh: {self.threshold:.2f}")

            elif self.portfolio[self.symbol].invested:
                if crossed_bearish or (zero_cross_bear and self.norm_wave < -self.threshold * 0.5):
                    self.liquidate(self.symbol)
                    self.debug(f"{self.time}: SELL {self.ticker} - Wave: {self.norm_wave:.2f}, Thresh: {self.threshold:.2f}")

        self.prev_norm_wave = self.norm_wave

    def on_end_of_algorithm(self):
        self.log(f"Wave-Adaptive Final: ${self.portfolio.total_portfolio_value:,.2f}")
