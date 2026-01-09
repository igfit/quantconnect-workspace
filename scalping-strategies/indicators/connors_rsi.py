"""
Connors RSI Indicator

A composite indicator combining:
1. RSI(3) - Short-term relative strength
2. StreakRSI - RSI of consecutive up/down day streaks
3. PercentRank - Percentile rank of current price in lookback

Formula: ConnorsRSI = (RSI(3) + StreakRSI + PercentRank) / 3

Academic basis: Larry Connors & Cesar Alvarez
Reference: "Short-Term Trading Strategies That Work"
"""

from collections import deque
from typing import Optional


class ConnorsRSI:
    """
    Connors RSI Composite Indicator

    This indicator combines three components:
    - RSI(3): Traditional RSI with very short period (3 days)
    - StreakRSI: RSI applied to consecutive up/down day streak values
    - PercentRank: Where current close ranks vs last N closes

    Usage:
        crsi = ConnorsRSI(rsi_period=3, streak_period=2, rank_period=100)
        for close, rsi_value in data:
            crsi.update(close, rsi_value)
            if crsi.is_ready:
                print(crsi.value)

    Values:
        - < 10: Extremely oversold (strong buy signal)
        - < 20: Very oversold (buy signal)
        - 40-60: Neutral
        - > 80: Very overbought (sell signal)
        - > 90: Extremely overbought (strong sell signal)
    """

    def __init__(
        self,
        rsi_period: int = 3,
        streak_period: int = 2,
        rank_period: int = 100
    ):
        """
        Initialize Connors RSI.

        Args:
            rsi_period: Period for the short-term RSI (default: 3)
            streak_period: Period for StreakRSI calculation (default: 2)
            rank_period: Lookback for percentile rank (default: 100)
        """
        self.rsi_period = rsi_period
        self.streak_period = streak_period
        self.rank_period = rank_period

        # State
        self.streak = 0
        self.prev_close: Optional[float] = None
        self.closes = deque(maxlen=rank_period + 10)
        self.streak_history = deque(maxlen=streak_period + 10)

        # Output
        self._value = 50.0  # Default neutral
        self._is_ready = False

        # Component values for debugging
        self._rsi_component = 50.0
        self._streak_rsi_component = 50.0
        self._rank_component = 50.0

    @property
    def value(self) -> float:
        """Current Connors RSI value (0-100)"""
        return self._value

    @property
    def is_ready(self) -> bool:
        """True when enough data has been processed"""
        return self._is_ready

    @property
    def current(self):
        """QC-compatible current value accessor"""
        class ValueHolder:
            def __init__(self, val):
                self.value = val
        return ValueHolder(self._value)

    def update(self, close: float, rsi_value: float) -> float:
        """
        Update with new data point.

        Args:
            close: Current closing price
            rsi_value: Pre-calculated RSI(3) value from QC indicator

        Returns:
            Current Connors RSI value
        """
        # Update streak
        if self.prev_close is not None:
            if close > self.prev_close:
                self.streak = max(1, self.streak + 1) if self.streak > 0 else 1
            elif close < self.prev_close:
                self.streak = min(-1, self.streak - 1) if self.streak < 0 else -1
            else:
                self.streak = 0

        self.prev_close = close
        self.closes.append(close)
        self.streak_history.append(self.streak)

        # Need enough data
        if len(self.closes) < self.rank_period:
            return self._value

        self._is_ready = True
        self._rsi_component = rsi_value

        # Calculate StreakRSI
        self._streak_rsi_component = self._calculate_streak_rsi()

        # Calculate PercentRank
        self._rank_component = self._calculate_percent_rank(close)

        # Connors RSI = average of three components
        self._value = (
            self._rsi_component +
            self._streak_rsi_component +
            self._rank_component
        ) / 3

        return self._value

    def _calculate_streak_rsi(self) -> float:
        """
        Calculate RSI of streak values.

        StreakRSI measures how extreme the current streak is relative
        to recent streak behavior. Helps identify exhaustion in trends.
        """
        if len(self.streak_history) < self.streak_period + 1:
            return 50.0

        streaks = list(self.streak_history)[-self.streak_period - 1:]
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

    def _calculate_percent_rank(self, close: float) -> float:
        """
        Calculate percentile rank of current close.

        Returns 0-100 representing where current close ranks among
        the last N closes. Low values = price near bottom of range.
        """
        closes = list(self.closes)
        if len(closes) < 2:
            return 50.0

        # Count how many previous closes are below current
        count_below = sum(1 for c in closes[:-1] if c < close)
        return (count_below / (len(closes) - 1)) * 100

    def reset(self):
        """Reset indicator state"""
        self.streak = 0
        self.prev_close = None
        self.closes.clear()
        self.streak_history.clear()
        self._value = 50.0
        self._is_ready = False

    def __repr__(self) -> str:
        return (
            f"ConnorsRSI(value={self._value:.2f}, "
            f"rsi={self._rsi_component:.2f}, "
            f"streak_rsi={self._streak_rsi_component:.2f}, "
            f"rank={self._rank_component:.2f})"
        )


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    import random

    # Simulate price data with RSI values
    crsi = ConnorsRSI(rsi_period=3, streak_period=2, rank_period=100)

    # Generate fake data
    price = 100.0
    for i in range(150):
        # Random walk
        price *= 1 + random.uniform(-0.02, 0.02)

        # Fake RSI value (would come from QC)
        fake_rsi = random.uniform(30, 70)

        crsi.update(price, fake_rsi)

        if i >= 100:
            print(f"Day {i}: price={price:.2f}, {crsi}")
