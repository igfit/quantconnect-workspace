"""
Percent Rank Indicator

Calculates where the current value ranks as a percentile
among the last N values. Used in Connors RSI and other
mean reversion strategies.

Values:
- 0: Current value is lowest in lookback
- 50: Current value is median
- 100: Current value is highest in lookback
"""

from collections import deque
from typing import Optional


class PercentRank:
    """
    Percent Rank Indicator

    Measures where the current value sits within the distribution
    of the last N values, expressed as a percentile (0-100).

    Usage:
        pr = PercentRank(period=100)
        for price in prices:
            pr.update(price)
            if pr.is_ready:
                print(f"Price is at {pr.value:.1f}th percentile")
    """

    def __init__(self, period: int = 100):
        """
        Initialize Percent Rank indicator.

        Args:
            period: Number of bars to look back (default: 100)
        """
        self.period = period
        self.values = deque(maxlen=period + 1)
        self._value = 50.0
        self._is_ready = False

    @property
    def value(self) -> float:
        """Current percent rank (0-100)"""
        return self._value

    @property
    def is_ready(self) -> bool:
        """True when enough data for calculation"""
        return self._is_ready

    @property
    def current(self):
        """QC-compatible accessor"""
        class ValueHolder:
            def __init__(self, val):
                self.value = val
        return ValueHolder(self._value)

    def update(self, value: float) -> float:
        """
        Update with new value.

        Args:
            value: New data point (price, indicator value, etc.)

        Returns:
            Current percent rank
        """
        self.values.append(value)

        if len(self.values) < self.period:
            return self._value

        self._is_ready = True

        # Count how many previous values are below current
        values_list = list(self.values)
        current = values_list[-1]
        previous = values_list[:-1]

        count_below = sum(1 for v in previous if v < current)
        self._value = (count_below / len(previous)) * 100

        return self._value

    def reset(self):
        """Reset indicator state"""
        self.values.clear()
        self._value = 50.0
        self._is_ready = False

    def __repr__(self) -> str:
        return f"PercentRank(period={self.period}, value={self._value:.2f})"


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test with known data
    pr = PercentRank(period=10)

    # Ascending prices - last should be 100th percentile
    for i in range(1, 12):
        pr.update(float(i))
        print(f"Value: {i}, PercentRank: {pr.value:.1f}")

    print("\n--- Now descending ---")
    pr.reset()

    # Descending prices - last should be 0th percentile
    for i in range(11, 0, -1):
        pr.update(float(i))
        print(f"Value: {i}, PercentRank: {pr.value:.1f}")
