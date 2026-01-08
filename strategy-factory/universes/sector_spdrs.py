"""
Universe B: Sector SPDRs (11 S&P 500 Sectors)

RATIONALE:
Sector rotation is pure signal alpha - we're not picking stocks, we're
picking which sector is trending. All original sector SPDRs have existed
since 1998.

LIQUIDITY: All sector SPDRs have extremely high volume (>$100M daily)
BIAS RISK: Zero (sector ETFs don't get delisted)

USE FOR:
- Sector momentum rotation
- Relative strength ranking
- Faber-style sector momentum
- Mean reversion between sectors

NOTE: XLRE (Real Estate) split from XLF in 2015, XLC (Communications)
created in 2018. For backtests before these dates, use 9 original sectors.
"""

from typing import List, Dict
from datetime import datetime

# Sector SPDR definitions with metadata
SECTOR_SPDR_UNIVERSE: Dict[str, Dict] = {
    # Original 9 sectors (1998)
    "XLK": {
        "name": "Technology",
        "inception": "1998-12-16",
        "description": "Apple, Microsoft, NVIDIA, etc.",
    },
    "XLF": {
        "name": "Financials",
        "inception": "1998-12-16",
        "description": "JPMorgan, Berkshire, Bank of America, etc.",
    },
    "XLV": {
        "name": "Health Care",
        "inception": "1998-12-16",
        "description": "UnitedHealth, Johnson & Johnson, Eli Lilly, etc.",
    },
    "XLE": {
        "name": "Energy",
        "inception": "1998-12-16",
        "description": "Exxon, Chevron, ConocoPhillips, etc.",
    },
    "XLI": {
        "name": "Industrials",
        "inception": "1998-12-16",
        "description": "Caterpillar, UPS, Honeywell, etc.",
    },
    "XLP": {
        "name": "Consumer Staples",
        "inception": "1998-12-16",
        "description": "Procter & Gamble, Costco, Walmart, etc.",
    },
    "XLY": {
        "name": "Consumer Discretionary",
        "inception": "1998-12-16",
        "description": "Amazon, Tesla, Home Depot, etc.",
    },
    "XLB": {
        "name": "Materials",
        "inception": "1998-12-16",
        "description": "Linde, Sherwin-Williams, Freeport, etc.",
    },
    "XLU": {
        "name": "Utilities",
        "inception": "1998-12-16",
        "description": "NextEra, Duke Energy, Southern Co, etc.",
    },

    # Newer sectors (use with date awareness)
    "XLRE": {
        "name": "Real Estate",
        "inception": "2015-10-07",
        "description": "Prologis, American Tower, Equinix, etc.",
        "note": "Split from XLF in 2015",
    },
    "XLC": {
        "name": "Communication Services",
        "inception": "2018-06-18",
        "description": "Meta, Alphabet, Netflix, etc.",
        "note": "Created in 2018 from XLK/XLY components",
    },
}


def get_sector_spdr_symbols(
    backtest_start_date: str = None,
    include_real_estate: bool = True,
    include_communications: bool = True
) -> List[str]:
    """
    Get sector SPDR symbols for Universe B.

    Args:
        backtest_start_date: If provided (YYYY-MM-DD), only includes sectors
                            that existed before this date
        include_real_estate: If False, excludes XLRE
        include_communications: If False, excludes XLC

    Returns:
        List of ticker symbols
    """
    symbols = []

    for ticker, info in SECTOR_SPDR_UNIVERSE.items():
        # Date filter
        if backtest_start_date:
            inception = datetime.strptime(info["inception"], "%Y-%m-%d")
            start = datetime.strptime(backtest_start_date, "%Y-%m-%d")
            if inception > start:
                continue

        # Explicit exclusions
        if ticker == "XLRE" and not include_real_estate:
            continue
        if ticker == "XLC" and not include_communications:
            continue

        symbols.append(ticker)

    return symbols


def get_original_9_sectors() -> List[str]:
    """
    Get the original 9 sector SPDRs (1998).
    Safe for any backtest from 2000 onwards.
    """
    return [
        "XLK", "XLF", "XLV", "XLE", "XLI",
        "XLP", "XLY", "XLB", "XLU"
    ]


def get_all_11_sectors() -> List[str]:
    """
    Get all 11 sector SPDRs.
    Only use for backtests starting 2019 or later.
    """
    return list(SECTOR_SPDR_UNIVERSE.keys())


# Pre-defined rotation strategies
ROTATION_CONFIGS = {
    # Classic sector rotation (9 sectors)
    "classic_rotation": {
        "symbols": get_original_9_sectors(),
        "hold_count": 3,  # Hold top 3 sectors
        "rebalance": "monthly",
        "description": "Top 3 sectors by momentum, monthly rebalance",
    },

    # Defensive rotation (exclude tech/growth)
    "defensive_rotation": {
        "symbols": ["XLP", "XLV", "XLU", "XLF", "XLI"],
        "hold_count": 2,
        "rebalance": "monthly",
        "description": "Top 2 defensive sectors",
    },

    # Growth rotation (tech-heavy)
    "growth_rotation": {
        "symbols": ["XLK", "XLY", "XLV", "XLF"],
        "hold_count": 2,
        "rebalance": "monthly",
        "description": "Top 2 growth sectors",
    },

    # Full 11-sector rotation (2019+)
    "full_rotation": {
        "symbols": get_all_11_sectors(),
        "hold_count": 3,
        "rebalance": "monthly",
        "description": "Top 3 of all 11 sectors",
    },
}


def get_rotation_config(name: str) -> Dict:
    """Get a pre-defined rotation configuration"""
    if name not in ROTATION_CONFIGS:
        raise ValueError(f"Unknown config: {name}. Available: {list(ROTATION_CONFIGS.keys())}")
    return ROTATION_CONFIGS[name]


# Sector characteristics (for strategy design)
SECTOR_CHARACTERISTICS = {
    "XLK": {"beta": 1.2, "cyclical": True, "growth": True},
    "XLF": {"beta": 1.1, "cyclical": True, "growth": False},
    "XLV": {"beta": 0.8, "cyclical": False, "growth": True},
    "XLE": {"beta": 1.3, "cyclical": True, "growth": False},
    "XLI": {"beta": 1.0, "cyclical": True, "growth": False},
    "XLP": {"beta": 0.6, "cyclical": False, "growth": False},
    "XLY": {"beta": 1.1, "cyclical": True, "growth": True},
    "XLB": {"beta": 1.1, "cyclical": True, "growth": False},
    "XLU": {"beta": 0.5, "cyclical": False, "growth": False},
    "XLRE": {"beta": 0.9, "cyclical": True, "growth": False},
    "XLC": {"beta": 1.0, "cyclical": True, "growth": True},
}


if __name__ == "__main__":
    print("Sector SPDR Universe")
    print("=" * 50)

    print(f"\nOriginal 9 sectors (1998+):")
    print(get_original_9_sectors())

    print(f"\nAll 11 sectors (2019+):")
    print(get_all_11_sectors())

    print(f"\nSectors available for 2015-01-01 backtest:")
    print(get_sector_spdr_symbols(backtest_start_date="2015-01-01"))

    print(f"\nClassic rotation config:")
    print(get_rotation_config("classic_rotation"))
