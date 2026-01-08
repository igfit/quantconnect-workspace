"""
Universe A: Core ETFs

RATIONALE:
ETFs don't have survivorship bias - SPY existed in 2010, still exists today.
Same underlying methodology. This is the cleanest test of signal alpha.

LIQUIDITY: All ETFs have extremely high volume (>$500M daily)
BIAS RISK: Zero (ETFs don't get delisted like individual stocks)

USE FOR:
- Dual Momentum (GEM)
- Leveraged ETF rotation
- Cross-asset momentum
- VIX timing strategies
"""

from typing import List, Dict

# Core ETF definitions with metadata
ETF_CORE_UNIVERSE: Dict[str, Dict] = {
    # Broad Market (inception dates in comments)
    "SPY": {"name": "S&P 500", "category": "broad_market", "inception": "1993-01-22"},
    "QQQ": {"name": "Nasdaq 100", "category": "broad_market", "inception": "1999-03-10"},
    "IWM": {"name": "Russell 2000", "category": "broad_market", "inception": "2000-05-22"},
    "DIA": {"name": "Dow 30", "category": "broad_market", "inception": "1998-01-14"},

    # Leveraged (use with caution - decay over time)
    "TQQQ": {"name": "3x Nasdaq Bull", "category": "leveraged", "inception": "2010-02-09"},
    "SQQQ": {"name": "3x Nasdaq Bear", "category": "leveraged", "inception": "2010-02-09"},
    "UPRO": {"name": "3x S&P 500 Bull", "category": "leveraged", "inception": "2009-06-23"},
    "SPXU": {"name": "3x S&P 500 Bear", "category": "leveraged", "inception": "2009-06-23"},

    # Bonds / Safety
    "TLT": {"name": "20+ Year Treasury", "category": "bonds", "inception": "2002-07-22"},
    "IEF": {"name": "7-10 Year Treasury", "category": "bonds", "inception": "2002-07-22"},
    "BND": {"name": "Total Bond Market", "category": "bonds", "inception": "2007-04-03"},
    "SHY": {"name": "1-3 Year Treasury", "category": "bonds", "inception": "2002-07-22"},

    # Volatility
    "VXX": {"name": "VIX Short-term Futures", "category": "volatility", "inception": "2009-01-29"},

    # Commodities
    "GLD": {"name": "Gold", "category": "commodity", "inception": "2004-11-18"},
    "USO": {"name": "Oil", "category": "commodity", "inception": "2006-04-10"},
    "SLV": {"name": "Silver", "category": "commodity", "inception": "2006-04-21"},

    # International
    "EFA": {"name": "EAFE (Developed ex-US)", "category": "international", "inception": "2001-08-14"},
    "EEM": {"name": "Emerging Markets", "category": "international", "inception": "2003-04-07"},
}


def get_etf_core_symbols(
    categories: List[str] = None,
    exclude_leveraged: bool = False,
    min_inception_year: int = None
) -> List[str]:
    """
    Get ETF symbols for Universe A.

    Args:
        categories: Filter by category (e.g., ['broad_market', 'bonds'])
                   If None, returns all categories
        exclude_leveraged: If True, excludes leveraged ETFs (TQQQ, SQQQ, etc.)
        min_inception_year: Only include ETFs launched before this year

    Returns:
        List of ticker symbols
    """
    symbols = []

    for ticker, info in ETF_CORE_UNIVERSE.items():
        # Category filter
        if categories and info["category"] not in categories:
            continue

        # Leveraged filter
        if exclude_leveraged and info["category"] == "leveraged":
            continue

        # Inception year filter
        if min_inception_year:
            inception_year = int(info["inception"][:4])
            if inception_year > min_inception_year:
                continue

        symbols.append(ticker)

    return symbols


# Pre-defined universe configurations
UNIVERSE_CONFIGS = {
    # Dual Momentum (GEM): Stock index + Bonds + Cash proxy
    "dual_momentum": {
        "symbols": ["SPY", "EFA", "BND"],
        "description": "Global Equities Momentum - stocks vs bonds rotation",
    },

    # Aggressive Momentum: Tech-heavy with leverage option
    "aggressive_momentum": {
        "symbols": ["QQQ", "SPY", "TLT"],
        "description": "Risk-on/risk-off rotation",
    },

    # Cross-Asset: Full diversification
    "cross_asset": {
        "symbols": ["SPY", "QQQ", "TLT", "GLD", "EFA", "EEM"],
        "description": "Multi-asset class momentum",
    },

    # Leveraged Rotation (high risk)
    "leveraged_rotation": {
        "symbols": ["TQQQ", "UPRO", "TLT", "SHY"],
        "description": "Leveraged ETF rotation with bond hedge",
    },
}


def get_universe_config(name: str) -> Dict:
    """Get a pre-defined universe configuration"""
    if name not in UNIVERSE_CONFIGS:
        raise ValueError(f"Unknown universe config: {name}. Available: {list(UNIVERSE_CONFIGS.keys())}")
    return UNIVERSE_CONFIGS[name]


# Default universe for testing
DEFAULT_SYMBOLS = ["SPY", "QQQ", "TLT", "GLD"]


if __name__ == "__main__":
    # Test the module
    print("ETF Core Universe")
    print("=" * 50)

    print(f"\nAll symbols ({len(ETF_CORE_UNIVERSE)}):")
    print(get_etf_core_symbols())

    print(f"\nBroad market only:")
    print(get_etf_core_symbols(categories=["broad_market"]))

    print(f"\nExcluding leveraged:")
    print(get_etf_core_symbols(exclude_leveraged=True))

    print(f"\nPre-2005 inception (safe for 2005+ backtests):")
    print(get_etf_core_symbols(min_inception_year=2005, exclude_leveraged=True))

    print(f"\nDual Momentum config:")
    print(get_universe_config("dual_momentum"))
