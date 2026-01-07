from AlgorithmImports import *
import numpy as np


class WaveSupertrend(QCAlgorithm):
    """
    Wave Supertrend - Combines wave oscillator with SuperTrend trailing stop

    SuperTrend = volatility-based trailing stop that adapts to market conditions
    Formula: Upper Band = (High + Low) / 2 + ATR * multiplier
             Lower Band = (High + Low) / 2 - ATR * multiplier

    Entry: Wave crosses bullish AND price above SuperTrend
    Exit: Price closes below SuperTrend (trailing stop)

    Hypothesis: SuperTrend acts as adaptive trailing stop that
                lets winners run while cutting losers quickly.
                Wave oscillator filters entry timing.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.ticker = "TSLA"
        self.symbol = self.add_equity(self.ticker, Resolution.DAILY).symbol

        # Wave params
        self.wave_fast = 8
        self.wave_slow = 21

        # SuperTrend params
        self.atr_period = 10
        self.multiplier = 3.0

        # Indicators
        self.ema_fast = self.ema(self.symbol, self.wave_fast, Resolution.DAILY)
        self.ema_slow = self.ema(self.symbol, self.wave_slow, Resolution.DAILY)
        self.atr_indicator = self.atr(self.symbol, self.atr_period, MovingAverageType.SIMPLE, Resolution.DAILY)

        # SuperTrend state
        self.supertrend = None
        self.supertrend_direction = 0  # 1 = bullish, -1 = bearish
        self.prev_supertrend = None
        self.prev_direction = 0

        # Wave state
        self.wave = None
        self.prev_wave = None

        # Price tracking
        self.prev_close = None

        self.set_warm_up(50, Resolution.DAILY)
        self.set_benchmark("SPY")

    def calculate_supertrend(self, high, low, close):
        """
        Calculate SuperTrend value and direction.
        """
        if not self.atr_indicator.is_ready:
            return None, 0

        atr_val = self.atr_indicator.current.value
        hl2 = (high + low) / 2

        upper_band = hl2 + self.multiplier * atr_val
        lower_band = hl2 - self.multiplier * atr_val

        # Initialize on first calculation
        if self.supertrend is None:
            if close > hl2:
                return lower_band, 1  # Bullish
            else:
                return upper_band, -1  # Bearish

        # Update based on previous state
        if self.supertrend_direction == 1:  # Was bullish
            # Lower band can only go up (trailing stop)
            new_lower = max(lower_band, self.supertrend)

            if close < self.supertrend:  # Closed below support
                return upper_band, -1  # Flip to bearish
            else:
                return new_lower, 1  # Stay bullish with updated stop
        else:  # Was bearish
            # Upper band can only go down
            new_upper = min(upper_band, self.supertrend)

            if close > self.supertrend:  # Closed above resistance
                return lower_band, 1  # Flip to bullish
            else:
                return new_upper, -1  # Stay bearish with updated stop

    def on_data(self, data):
        if self.is_warming_up or self.symbol not in data:
            return
        if data[self.symbol] is None:
            return
        if not self.ema_fast.is_ready or not self.ema_slow.is_ready:
            return

        bar = data[self.symbol]
        high = bar.high
        low = bar.low
        close = bar.close

        # Calculate wave
        self.wave = self.ema_fast.current.value - self.ema_slow.current.value

        # Calculate SuperTrend
        self.supertrend, self.supertrend_direction = self.calculate_supertrend(high, low, close)

        if self.supertrend is None or self.prev_wave is None:
            self.prev_wave = self.wave
            self.prev_close = close
            return

        # Entry: Wave crosses bullish AND SuperTrend flips bullish
        wave_bullish = self.prev_wave < 0 and self.wave >= 0
        supertrend_bullish = self.supertrend_direction == 1

        # SuperTrend flip detection
        supertrend_flipped_bull = self.prev_direction == -1 and self.supertrend_direction == 1
        supertrend_flipped_bear = self.prev_direction == 1 and self.supertrend_direction == -1

        if not self.portfolio[self.symbol].invested:
            # Entry on wave bullish crossover if SuperTrend is bullish
            # OR on SuperTrend flip to bullish if wave is positive
            if (wave_bullish and supertrend_bullish) or (supertrend_flipped_bull and self.wave > 0):
                self.set_holdings(self.symbol, 1.0)
                self.debug(f"{self.time}: BUY {self.ticker} - Wave: {self.wave:.2f}, ST: {self.supertrend:.2f}")

        else:
            # Exit on SuperTrend flip to bearish (trailing stop triggered)
            if supertrend_flipped_bear:
                self.liquidate(self.symbol)
                self.debug(f"{self.time}: SELL {self.ticker} [STOP] - Wave: {self.wave:.2f}, ST: {self.supertrend:.2f}")

        self.prev_wave = self.wave
        self.prev_close = close
        self.prev_supertrend = self.supertrend
        self.prev_direction = self.supertrend_direction

    def on_end_of_algorithm(self):
        self.log(f"Wave-Supertrend Final: ${self.portfolio.total_portfolio_value:,.2f}")
