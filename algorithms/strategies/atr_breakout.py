from AlgorithmImports import *

class ATRBreakoutStrategy(QCAlgorithm):
    """
    ATR Breakout Strategy - Self-adjusting to each stock's volatility

    Logic:
    - Entry: Price breaks above 20-day high AND ATR is expanding (ATR > 1.2x avg ATR)
    - Exit: Trailing stop at entry - 2*ATR, or price breaks below 10-day low

    Parameters:
    - breakout_period: 20 days (Donchian channel high)
    - atr_period: 14 days
    - atr_expansion_mult: 1.2 (ATR must be 20% above average)
    - trail_atr_mult: 2.0 (trailing stop distance)
    - exit_period: 10 days (Donchian channel low for exit)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        # Parameters
        self.breakout_period = 20
        self.atr_period = 14
        self.atr_avg_period = 50  # Period to calculate average ATR
        self.atr_expansion_mult = 1.0  # Reduced from 1.2 - just above average
        self.trail_atr_mult = 2.0
        self.exit_period = 10

        # Add equity
        self.symbol = self.add_equity("TSLA", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # Indicators
        self.atr = self.atr_indicator(self.symbol, self.atr_period, MovingAverageType.WILDERS, Resolution.DAILY)
        self.atr_sma = SimpleMovingAverage(self.atr_avg_period)

        # Rolling windows for Donchian channels (add 1 to exclude current bar)
        self.high_window = RollingWindow[float](self.breakout_period + 1)
        self.low_window = RollingWindow[float](self.exit_period + 1)

        # Track entry price and trailing stop
        self.entry_price = 0
        self.trailing_stop = 0
        self.highest_since_entry = 0

        # Warmup
        self.set_warm_up(max(self.breakout_period, self.atr_avg_period) + 10)

    def atr_indicator(self, symbol, period, ma_type, resolution):
        return self.atr(symbol, period, ma_type, resolution)

    def on_data(self, data):
        if self.is_warming_up:
            return

        if not data.bars.contains_key(self.symbol):
            return

        bar = data.bars[self.symbol]

        # Update rolling windows
        self.high_window.add(bar.high)
        self.low_window.add(bar.low)

        # Update ATR SMA
        if self.atr.is_ready:
            self.atr_sma.update(self.time, self.atr.current.value)

        # Check if indicators are ready
        if not self.high_window.is_ready or not self.low_window.is_ready:
            return
        if not self.atr.is_ready or not self.atr_sma.is_ready:
            return

        # Calculate Donchian channels (exclude current bar - start from index 1)
        donchian_high = max([self.high_window[i] for i in range(1, self.breakout_period + 1)])
        donchian_low = min([self.low_window[i] for i in range(1, self.exit_period + 1)])

        current_price = bar.close
        current_atr = self.atr.current.value
        avg_atr = self.atr_sma.current.value

        # Check if we have a position
        if self.portfolio[self.symbol].invested:
            # Update highest price since entry
            if current_price > self.highest_since_entry:
                self.highest_since_entry = current_price
                # Update trailing stop
                self.trailing_stop = self.highest_since_entry - (self.trail_atr_mult * current_atr)

            # Exit conditions
            exit_signal = False
            exit_reason = ""

            # 1. Trailing stop hit
            if current_price < self.trailing_stop:
                exit_signal = True
                exit_reason = "Trailing Stop"

            # 2. Price breaks below exit Donchian low
            elif current_price < donchian_low:
                exit_signal = True
                exit_reason = "Donchian Low Break"

            if exit_signal:
                self.liquidate(self.symbol, exit_reason)
                self.entry_price = 0
                self.trailing_stop = 0
                self.highest_since_entry = 0

        else:
            # Entry conditions
            # 1. Price breaks above Donchian high (20-day high)
            breakout = current_price > donchian_high

            # 2. ATR is expanding (volatility confirmation)
            atr_expanding = current_atr > (avg_atr * self.atr_expansion_mult)

            if breakout and atr_expanding:
                self.set_holdings(self.symbol, 1.0)
                self.entry_price = current_price
                self.highest_since_entry = current_price
                self.trailing_stop = current_price - (self.trail_atr_mult * current_atr)
                self.debug(f"ENTRY: Price={current_price:.2f}, ATR={current_atr:.2f}, AvgATR={avg_atr:.2f}, Stop={self.trailing_stop:.2f}")
