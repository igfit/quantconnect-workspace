"""
Indicator Modules for Strategy Factory

Provides helper functions and custom indicators for swing trading strategies.

Modules:
    - trend: Trend-following indicators (SuperTrend, HMA, Elder Impulse)
    - momentum: Momentum indicators (ROC, Clenow slope, momentum score)
    - volatility: Volatility indicators (ATR, Chandelier, NR7)
    - oscillators: Oscillators (RSI, Williams %R, TSI, CMO)
    - breakout: Breakout detection (Donchian, 52-week high, Darvas)
"""

from .core import (
    IndicatorHelper,
    calculate_roc,
    calculate_atr_pct,
    is_above_sma,
    crosses_above,
    crosses_below,
)

__all__ = [
    'IndicatorHelper',
    'calculate_roc',
    'calculate_atr_pct',
    'is_above_sma',
    'crosses_above',
    'crosses_below',
]
