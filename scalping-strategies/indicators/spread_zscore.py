"""
Spread Z-Score Indicator

Calculates the Z-score of a price spread between two correlated assets.
Used for pairs trading strategies.

Z-score = (Current Spread - Mean Spread) / Std Dev of Spread

Trading signals:
- Z > 2.0: Spread too wide, expect mean reversion (short spread)
- Z < -2.0: Spread too narrow, expect mean reversion (long spread)
- Z near 0: Spread at fair value, close positions
"""

from collections import deque
from typing import Optional, Tuple
import math


class SpreadZScore:
    """
    Spread Z-Score Indicator for Pairs Trading

    Measures how far the current spread between two assets deviates
    from its historical mean, normalized by standard deviation.

    Usage:
        zscore = SpreadZScore(lookback=60)
        for price_a, price_b in prices:
            zscore.update(price_a, price_b)
            if zscore.is_ready:
                if zscore.value > 2.0:
                    # Short A, Long B
                elif zscore.value < -2.0:
                    # Long A, Short B
    """

    def __init__(
        self,
        lookback: int = 60,
        hedge_ratio: Optional[float] = None
    ):
        """
        Initialize Spread Z-Score indicator.

        Args:
            lookback: Period for mean/std calculation (default: 60)
            hedge_ratio: Fixed hedge ratio. If None, uses price ratio.
        """
        self.lookback = lookback
        self.fixed_hedge_ratio = hedge_ratio

        # State
        self.prices_a = deque(maxlen=lookback + 10)
        self.prices_b = deque(maxlen=lookback + 10)
        self.spreads = deque(maxlen=lookback + 10)

        # Output
        self._value = 0.0
        self._spread = 0.0
        self._mean = 0.0
        self._std = 1.0
        self._hedge_ratio = hedge_ratio or 1.0
        self._is_ready = False

    @property
    def value(self) -> float:
        """Current Z-score"""
        return self._value

    @property
    def spread(self) -> float:
        """Current spread value"""
        return self._spread

    @property
    def mean(self) -> float:
        """Mean spread over lookback period"""
        return self._mean

    @property
    def std(self) -> float:
        """Standard deviation of spread"""
        return self._std

    @property
    def hedge_ratio(self) -> float:
        """Current hedge ratio"""
        return self._hedge_ratio

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

    def update(self, price_a: float, price_b: float) -> float:
        """
        Update with new prices.

        Args:
            price_a: Price of first asset (long leg when z < 0)
            price_b: Price of second asset (short leg when z < 0)

        Returns:
            Current Z-score
        """
        self.prices_a.append(price_a)
        self.prices_b.append(price_b)

        # Calculate hedge ratio if not fixed
        if self.fixed_hedge_ratio is None and len(self.prices_a) >= 20:
            self._hedge_ratio = self._calculate_hedge_ratio()

        # Calculate spread: price_a - hedge_ratio * price_b
        self._spread = price_a - self._hedge_ratio * price_b
        self.spreads.append(self._spread)

        # Need enough data
        if len(self.spreads) < self.lookback:
            return self._value

        self._is_ready = True

        # Calculate mean and std of spread
        spreads_list = list(self.spreads)[-self.lookback:]
        self._mean = sum(spreads_list) / len(spreads_list)

        variance = sum((s - self._mean) ** 2 for s in spreads_list) / len(spreads_list)
        self._std = math.sqrt(variance) if variance > 0 else 0.0001

        # Z-score
        self._value = (self._spread - self._mean) / self._std

        return self._value

    def _calculate_hedge_ratio(self) -> float:
        """
        Calculate hedge ratio using simple regression.

        hedge_ratio = Cov(A, B) / Var(B)
        """
        prices_a = list(self.prices_a)[-self.lookback:]
        prices_b = list(self.prices_b)[-self.lookback:]

        if len(prices_a) < 20:
            return 1.0

        n = len(prices_a)
        mean_a = sum(prices_a) / n
        mean_b = sum(prices_b) / n

        # Covariance
        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(prices_a, prices_b)) / n

        # Variance of B
        var_b = sum((b - mean_b) ** 2 for b in prices_b) / n

        if var_b == 0:
            return 1.0

        return cov / var_b

    def get_position_sizes(
        self,
        capital: float,
        price_a: float,
        price_b: float
    ) -> Tuple[int, int]:
        """
        Calculate position sizes for a dollar-neutral trade.

        Args:
            capital: Total capital for the pair
            price_a: Current price of asset A
            price_b: Current price of asset B

        Returns:
            Tuple of (shares_a, shares_b)
        """
        # Split capital equally adjusted for hedge ratio
        value_a = capital / 2
        value_b = capital / 2

        shares_a = int(value_a / price_a)
        shares_b = int(value_b / price_b)

        return shares_a, shares_b

    def reset(self):
        """Reset indicator state"""
        self.prices_a.clear()
        self.prices_b.clear()
        self.spreads.clear()
        self._value = 0.0
        self._spread = 0.0
        self._mean = 0.0
        self._std = 1.0
        self._is_ready = False

    def __repr__(self) -> str:
        return (
            f"SpreadZScore(zscore={self._value:.2f}, "
            f"spread={self._spread:.2f}, "
            f"mean={self._mean:.2f}, "
            f"std={self._std:.2f}, "
            f"hedge_ratio={self._hedge_ratio:.3f})"
        )


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    import random

    zscore = SpreadZScore(lookback=60)

    # Simulate two correlated prices (NVDA and AMD-like)
    price_a = 500.0  # NVDA
    price_b = 150.0  # AMD

    print("Simulating correlated price movements...\n")

    for i in range(100):
        # Correlated random walk
        common_move = random.uniform(-0.02, 0.02)
        idio_a = random.uniform(-0.01, 0.01)
        idio_b = random.uniform(-0.01, 0.01)

        price_a *= 1 + common_move + idio_a
        price_b *= 1 + common_move + idio_b

        zscore.update(price_a, price_b)

        if i >= 60:
            signal = ""
            if zscore.value > 2.0:
                signal = "SHORT SPREAD (Short A, Long B)"
            elif zscore.value < -2.0:
                signal = "LONG SPREAD (Long A, Short B)"
            elif abs(zscore.value) < 0.5:
                signal = "EXIT (at mean)"

            print(f"Day {i}: A=${price_a:.2f}, B=${price_b:.2f}, {zscore}")
            if signal:
                print(f"  --> {signal}")
