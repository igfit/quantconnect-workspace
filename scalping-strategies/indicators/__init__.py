"""
Custom Indicators for Scalping Strategies

Includes indicators not built into QuantConnect:
- ConnorsRSI: Multi-factor mean reversion indicator
- StreakRSI: RSI of consecutive up/down day streaks
- PercentRank: Percentile rank within lookback period
- SpreadZScore: Z-score of price spread for pairs trading
"""

from .connors_rsi import ConnorsRSI
from .percent_rank import PercentRank
from .streak_rsi import StreakRSI
from .spread_zscore import SpreadZScore

__all__ = [
    "ConnorsRSI",
    "PercentRank",
    "StreakRSI",
    "SpreadZScore",
]
