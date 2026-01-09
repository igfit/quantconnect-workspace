"""
Scalping Strategies Configuration

Central configuration for all scalping strategy parameters,
risk management settings, and backtesting periods.
"""

from enum import Enum
from typing import Dict, List, Tuple

# =============================================================================
# RESOLUTION SETTINGS
# =============================================================================

class Resolution(Enum):
    """Supported data resolutions"""
    MINUTE = "Resolution.MINUTE"
    HOUR = "Resolution.HOUR"
    DAILY = "Resolution.DAILY"


# Slippage models by resolution (more realistic for higher frequency)
SLIPPAGE_BY_RESOLUTION: Dict[Resolution, float] = {
    Resolution.MINUTE: 0.0002,  # 2 bps - tight for liquid stocks
    Resolution.HOUR: 0.0005,    # 5 bps - moderate
    Resolution.DAILY: 0.001,    # 10 bps - conservative
}

# Default resolution for new strategies
DEFAULT_RESOLUTION = Resolution.DAILY


# =============================================================================
# UNIVERSE SETTINGS
# =============================================================================

# Primary universe - high-beta stocks
HIGH_BETA_UNIVERSE: List[str] = [
    "TSLA",  # Tesla - strong trends, retail momentum
    "NVDA",  # NVIDIA - AI/semiconductor cycles
    "AMD",   # AMD - semiconductor, correlated to NVDA
]

# Secondary universe - mega-cap liquid stocks
MEGA_CAP_UNIVERSE: List[str] = [
    "AAPL",  # Apple
    "MSFT",  # Microsoft
    "GOOGL", # Alphabet
    "META",  # Meta
    "AMZN",  # Amazon
]

# Full universe for comprehensive testing
FULL_UNIVERSE: List[str] = HIGH_BETA_UNIVERSE + MEGA_CAP_UNIVERSE

# Pairs for pairs trading
PAIRS_UNIVERSE: List[Tuple[str, str]] = [
    ("NVDA", "AMD"),   # Semiconductors
    ("AAPL", "MSFT"),  # Mega-cap tech
    ("TSLA", "RIVN"),  # EVs (if RIVN has enough history)
]

# Minimum requirements for universe filtering
MIN_PRICE = 5.0
MIN_DOLLAR_VOLUME = 500_000  # Daily dollar volume


# =============================================================================
# BACKTESTING PERIODS (Walk-Forward Analysis)
# =============================================================================

BACKTEST_PERIODS: Dict[str, Dict[str, str]] = {
    "train": {
        "start": "2018-01-01",
        "end": "2020-12-31",
        "description": "Training period - parameter development"
    },
    "test": {
        "start": "2021-01-01",
        "end": "2022-12-31",
        "description": "Test period - ONE attempt, no changes"
    },
    "validate": {
        "start": "2023-01-01",
        "end": "2024-12-31",
        "description": "Validation period - ZERO changes allowed"
    },
    "full": {
        "start": "2018-01-01",
        "end": "2024-12-31",
        "description": "Full period - for final analysis only"
    }
}

# Active period for development
ACTIVE_PERIOD = "train"


# =============================================================================
# RISK MANAGEMENT
# =============================================================================

# Capital settings
DEFAULT_INITIAL_CAPITAL = 100_000

# Position sizing
RISK_PER_TRADE_PCT = 0.01      # 1% of capital per trade
MAX_POSITION_PCT = 0.25        # Max 25% in single position
MAX_CONCURRENT_POSITIONS = 5   # Max 5 positions at once
MAX_SECTOR_EXPOSURE_PCT = 0.40 # Max 40% in one sector

# Stop loss defaults by strategy type
STOP_LOSS_DEFAULTS: Dict[str, float] = {
    "mean_reversion": 0.03,    # 3% hard stop
    "momentum": None,          # Use trailing stop instead
    "breakout": None,          # Use entry bar low
    "pairs": None,             # Use Z-score stop
}

# Time stops (max holding days)
TIME_STOP_DEFAULTS: Dict[str, int] = {
    "mean_reversion": 5,       # Exit after 5 days
    "momentum": 20,            # Exit after 20 days
    "breakout": 10,            # Exit after 10 days
    "pairs": 20,               # Exit after 20 days
}

# Portfolio-level risk controls
MAX_DAILY_LOSS_PCT = 0.03     # 3% daily loss limit
MAX_WEEKLY_LOSS_PCT = 0.05    # 5% weekly loss limit
DRAWDOWN_REDUCE_TRIGGER = 0.15 # At 15% DD, reduce position sizes 50%
DRAWDOWN_HALT_TRIGGER = 0.20   # At 20% DD, stop trading


# =============================================================================
# COMMISSION MODEL (IBKR)
# =============================================================================

COMMISSION_PER_SHARE = 0.005   # $0.005 per share
COMMISSION_MIN = 1.0           # $1 minimum per order
COMMISSION_MAX_PCT = 0.01      # 1% max of trade value


# =============================================================================
# INDICATOR DEFAULTS
# =============================================================================

# RSI settings
RSI_PERIOD_SHORT = 2           # RSI(2) for mean reversion
RSI_PERIOD_STANDARD = 14       # Standard RSI
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
RSI_EXTREME_OVERSOLD = 10      # For RSI(2) strategy
RSI_EXTREME_OVERBOUGHT = 90

# Connors RSI components
CONNORS_RSI_PERIOD = 3
CONNORS_STREAK_PERIOD = 2
CONNORS_RANK_PERIOD = 100

# Moving averages
SMA_TREND_FILTER = 200         # Long-term trend filter
SMA_FAST = 50                  # Medium-term
EMA_FAST = 12
EMA_SLOW = 26

# Bollinger Bands
BB_PERIOD = 20
BB_STD_DEV = 2.0

# ATR for stops/sizing
ATR_PERIOD = 14
ATR_MULTIPLIER_STOP = 2.0      # 2x ATR for trailing stop

# VWAP (intraday only)
VWAP_DEVIATION_ENTRY = 1.5     # Enter at 1.5% below VWAP

# Pairs trading
PAIRS_LOOKBACK = 60            # 60-day lookback for spread stats
PAIRS_ENTRY_ZSCORE = 2.0       # Enter at 2 std dev
PAIRS_EXIT_ZSCORE = 0.0        # Exit at mean
PAIRS_STOP_ZSCORE = 3.5        # Stop at 3.5 std dev


# =============================================================================
# SUCCESS CRITERIA
# =============================================================================

TARGET_SHARPE = 0.8
TARGET_CAGR = 0.15             # 15%
TARGET_MAX_DRAWDOWN = 0.25     # 25%
TARGET_WIN_RATE = 0.55         # 55%
TARGET_PROFIT_FACTOR = 1.5

STRETCH_SHARPE = 1.2
STRETCH_CAGR = 0.25            # 25%
STRETCH_MAX_DRAWDOWN = 0.15    # 15%
STRETCH_WIN_RATE = 0.65        # 65%
STRETCH_PROFIT_FACTOR = 2.0

MIN_TRADES_FOR_SIGNIFICANCE = 30


# =============================================================================
# FILE PATHS
# =============================================================================

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPECS_DIR = os.path.join(BASE_DIR, "strategies", "specs")
COMPILED_DIR = os.path.join(BASE_DIR, "strategies", "compiled")
BACKTESTS_DIR = os.path.join(BASE_DIR, "backtests", "results")
DOCS_DIR = os.path.join(BASE_DIR, "docs")


# =============================================================================
# QC INDICATOR MAPPING
# =============================================================================

INDICATOR_MAPPING: Dict[str, str] = {
    "SMA": "SimpleMovingAverage",
    "EMA": "ExponentialMovingAverage",
    "RSI": "RelativeStrengthIndex",
    "MACD": "MovingAverageConvergenceDivergence",
    "BB": "BollingerBands",
    "ATR": "AverageTrueRange",
    "ADX": "AverageDirectionalIndex",
    "VWAP": "VolumeWeightedAveragePriceIndicator",
    "ROC": "RateOfChange",
    "MOM": "Momentum",
    "STOCH": "Stochastic",
}


# =============================================================================
# WARMUP CALCULATION
# =============================================================================

WARMUP_BUFFER_DAYS = 10  # Extra buffer for warmup

def calculate_warmup(indicators: list, resolution: Resolution) -> int:
    """Calculate required warmup period based on indicators and resolution"""
    max_period = max((ind.get("period", 14) for ind in indicators), default=14)

    # Adjust for resolution
    if resolution == Resolution.MINUTE:
        # For minute data, periods are in minutes, need more warmup
        return max_period + WARMUP_BUFFER_DAYS * 390  # 390 minutes/day
    elif resolution == Resolution.HOUR:
        return max_period + WARMUP_BUFFER_DAYS * 7  # ~7 hours/day
    else:
        return max_period + WARMUP_BUFFER_DAYS
