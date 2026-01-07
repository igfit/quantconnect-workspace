"""
Strategy Factory Configuration

Constants, thresholds, and settings for the strategy generation pipeline.
"""

from typing import Dict, Tuple

# =============================================================================
# DATE RANGES
# =============================================================================

DATE_RANGES: Dict[str, Dict[str, Tuple[str, str]]] = {
    "5_year": {
        "full": ("2020-01-01", "2024-12-31"),
        "train": ("2020-01-01", "2022-06-30"),
        "validate": ("2022-07-01", "2023-06-30"),
        "test": ("2023-07-01", "2024-12-31"),
    },
    "10_year": {
        "full": ("2015-01-01", "2024-12-31"),
        "train": ("2015-01-01", "2020-06-30"),
        "validate": ("2020-07-01", "2022-06-30"),
        "test": ("2022-07-01", "2024-12-31"),
    },
}

# Active date range (can be overridden via CLI)
ACTIVE_DATE_RANGE = "5_year"

# =============================================================================
# EVALUATION THRESHOLDS
# =============================================================================

# Minimum thresholds for initial filtering
# Thresholds for initial filtering - can adjust based on market conditions
MIN_SHARPE_RATIO = 0.4  # Lowered for initial testing, production: 0.8
MIN_CAGR = 0.08  # 8% - production: 0.10
MAX_DRAWDOWN = 0.30  # 30% - production: 0.25
MIN_PROFIT_FACTOR = 1.2  # production: 1.3
MIN_WIN_RATE = 0.40  # 40% - production: 0.45
MIN_TRADE_COUNT = 20  # production: 30

# Disqualifier thresholds
DISQUALIFY_MAX_DRAWDOWN = 0.40  # 40%
DISQUALIFY_NEGATIVE_YEARS = 2  # Max years with negative returns

# =============================================================================
# SCORING WEIGHTS
# =============================================================================

SCORING_WEIGHTS = {
    "sharpe_ratio": 0.30,
    "cagr": 0.25,
    "max_drawdown": 0.20,
    "profit_factor": 0.15,
    "win_rate": 0.10,
}

# Scoring normalization ranges
SCORE_RANGES = {
    "sharpe_ratio": (0, 3),      # Sharpe 0-3 maps to 0-1
    "cagr": (0, 0.5),            # CAGR 0-50% maps to 0-1
    "max_drawdown": (0, 0.4),    # DD 0-40% maps to 1-0 (inverted)
    "profit_factor": (1, 3),     # PF 1-3 maps to 0-1
    "win_rate": (0.3, 0.7),      # WR 30-70% maps to 0-1
}

# Penalties (multipliers)
PENALTY_HIGH_TURNOVER = 0.90      # >50 trades/year
PENALTY_LOW_TRADE_COUNT = 0.80    # <30 trades total
PENALTY_SINGLE_REGIME = 0.70      # Only works in bull market

# =============================================================================
# STRATEGY CONSTRAINTS (KISS)
# =============================================================================

MAX_INDICATORS = 3
MAX_ENTRY_CONDITIONS = 2
MAX_EXIT_CONDITIONS = 2

# =============================================================================
# EXECUTION MODEL (Live-Safety)
# =============================================================================

# Slippage model
SLIPPAGE_PERCENT = 0.001  # 0.1%

# Commission model (IBKR)
COMMISSION_PER_SHARE = 0.005  # $0.005 per share
COMMISSION_MIN = 1.0           # $1 minimum

# Liquidity filters
MIN_PRICE = 5.0                    # Minimum stock price
MIN_DOLLAR_VOLUME = 500_000        # Minimum daily dollar volume

# Warmup buffer (added to longest indicator period)
WARMUP_BUFFER_DAYS = 10

# =============================================================================
# POSITION SIZING
# =============================================================================

DEFAULT_POSITION_SIZE_DOLLARS = 10_000
DEFAULT_INITIAL_CAPITAL = 100_000

# =============================================================================
# QUANTCONNECT API
# =============================================================================

QC_API_BASE = "https://www.quantconnect.com/api/v2"
QC_RATE_LIMIT = 30  # requests per minute
QC_RATE_LIMIT_BUFFER = 5  # safety buffer

# Backtest polling
BACKTEST_POLL_INTERVAL = 5  # seconds
BACKTEST_TIMEOUT = 300  # 5 minutes max wait

# Sandbox project
SANDBOX_PROJECT_ID = 27315240  # Strategy Factory Sandbox

# =============================================================================
# INDICATOR MAPPINGS
# =============================================================================

# Map indicator type names to QuantConnect class names
INDICATOR_MAPPING = {
    # Trend
    "SMA": "SimpleMovingAverage",
    "EMA": "ExponentialMovingAverage",
    "WMA": "WeightedMovingAverage",
    "ADX": "AverageDirectionalIndex",

    # Momentum
    "RSI": "RelativeStrengthIndex",
    "MACD": "MovingAverageConvergenceDivergence",
    "ROC": "RateOfChange",
    "MOM": "Momentum",
    "STOCH": "Stochastic",

    # Volatility
    "ATR": "AverageTrueRange",
    "BB": "BollingerBands",

    # Volume
    "OBV": "OnBalanceVolume",
    "VWAP": "VolumeWeightedAveragePriceIndicator",
}

# Indicator default parameters
INDICATOR_DEFAULTS = {
    "SMA": {"period": 20},
    "EMA": {"period": 20},
    "WMA": {"period": 20},
    "ADX": {"period": 14},
    "RSI": {"period": 14},
    "MACD": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
    "ROC": {"period": 14},
    "MOM": {"period": 14},
    "STOCH": {"period": 14, "k_period": 3, "d_period": 3},
    "ATR": {"period": 14},
    "BB": {"period": 20, "k": 2},
    "OBV": {},
    "VWAP": {},
}

# =============================================================================
# UNIVERSE OPTIONS
# =============================================================================

# Static universes
STATIC_UNIVERSES = {
    "high_beta_tech": ["TSLA", "NVDA", "AMD", "COIN", "SQ", "SHOP", "MARA", "RIOT"],
    "faang_plus": ["AAPL", "AMZN", "GOOGL", "META", "MSFT", "NFLX", "NVDA", "TSLA"],
    "sector_etfs": ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE"],
    "mega_cap": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "BRK.B", "LLY", "TSM", "V"],
}

# Dynamic universe options
DYNAMIC_UNIVERSE_OPTIONS = {
    "indices": ["SP500", "NASDAQ100", "DJIA"],
    "sectors": [
        "Technology", "Healthcare", "Financials", "Consumer Discretionary",
        "Industrials", "Energy", "Materials", "Utilities", "Real Estate",
        "Consumer Staples", "Communication Services"
    ],
}

# =============================================================================
# GENERATION SETTINGS
# =============================================================================

DEFAULT_BATCH_SIZE = 15  # Number of strategies to generate per batch
MAX_PARAMETER_COMBINATIONS = 50  # Max variations per strategy in sweep

# =============================================================================
# FILE PATHS
# =============================================================================

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPECS_DIR = os.path.join(BASE_DIR, "strategies", "specs")
COMPILED_DIR = os.path.join(BASE_DIR, "strategies", "compiled")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
REGISTRY_PATH = os.path.join(BASE_DIR, "strategies", "registry.json")
