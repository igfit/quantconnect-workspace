"""
Streak RSI Indicator

Calculates the RSI of consecutive up/down day streaks.
A component of Connors RSI.

Streak counting:
- Up day: streak += 1 (or resets to +1 if was negative)
- Down day: streak -= 1 (or resets to -1 if was positive)
- Flat day: streak = 0

Then RSI is calculated on these streak values.

This measures how "tired" a streak is getting - high StreakRSI
after many up days suggests exhaustion.
"""

from collections import deque
from typing import Optional


class StreakRSI:
    """
    Streak RSI Indicator

    Measures the relative strength of consecutive up/down streaks.
    Used to identify exhaustion in short-term trends.

    Usage:
        srsi = StreakRSI(period=2)
        for close in closes:
            srsi.update(close)
            if srsi.is_ready:
                print(f"StreakRSI: {srsi.value:.1f}")
    """

    def __init__(self, period: int = 2):
        """
        Initialize Streak RSI.

        Args:
            period: RSI period for streak values (default: 2)
        """
        self.period = period

        # State
        self.streak = 0
        self.prev_close: Optional[float] = None
        self.streak_history = deque(maxlen=period + 10)

        # Output
        self._value = 50.0
        self._is_ready = False

    @property
    def value(self) -> float:
        """Current Streak RSI value (0-100)"""
        return self._value

    @property
    def is_ready(self) -> bool:
        """True when enough data for calculation"""
        return self._is_ready

    @property
    def current_streak(self) -> int:
        """Current streak count"""
        return self.streak

    @property
    def current(self):
        """QC-compatible accessor"""
        class ValueHolder:
            def __init__(self, val):
                self.value = val
        return ValueHolder(self._value)

    def update(self, close: float) -> float:
        """
        Update with new closing price.

        Args:
            close: Closing price

        Returns:
            Current Streak RSI value
        """
        # Calculate streak
        if self.prev_close is not None:
            if close > self.prev_close:
                # Up day
                if self.streak > 0:
                    self.streak += 1
                else:
                    self.streak = 1
            elif close < self.prev_close:
                # Down day
                if self.streak < 0:
                    self.streak -= 1
                else:
                    self.streak = -1
            else:
                # Flat day
                self.streak = 0

        self.prev_close = close
        self.streak_history.append(self.streak)

        # Need enough data
        if len(self.streak_history) < self.period + 1:
            return self._value

        self._is_ready = True

        # Calculate RSI of streak values
        self._value = self._calculate_rsi()

        return self._value

    def _calculate_rsi(self) -> float:
        """Calculate RSI of streak values"""
        streaks = list(self.streak_history)[-self.period - 1:]
        gains = []
        losses = []

        for i in range(1, len(streaks)):
            change = streaks[i] - streaks[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_loss = sum(losses) / len(losses) if losses else 0.0001

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def reset(self):
        """Reset indicator state"""
        self.streak = 0
        self.prev_close = None
        self.streak_history.clear()
        self._value = 50.0
        self._is_ready = False

    def __repr__(self) -> str:
        return f"StreakRSI(period={self.period}, streak={self.streak}, value={self._value:.2f})"


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    srsi = StreakRSI(period=2)

    # Simulate 5 up days, then 5 down days
    closes = [100, 101, 102, 103, 104, 105, 104, 103, 102, 101, 100]

    for i, close in enumerate(closes):
        srsi.update(close)
        direction = "UP" if i > 0 and close > closes[i-1] else "DOWN" if i > 0 and close < closes[i-1] else "START"
        print(f"Close: {close}, Direction: {direction}, Streak: {srsi.current_streak}, StreakRSI: {srsi.value:.1f}")
