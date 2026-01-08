"""
Universe D: High-Beta Growth

RATIONALE:
Trend-following and breakout strategies need volatility.
These stocks have higher beta (> 1.3) and larger price moves.

BIAS WARNING: This universe has moderate survivorship bias risk.
We select stocks that had high beta as of 2015, but some may have
changed characteristics. Document carefully.

USE FOR:
- Minervini VCP
- Momentum Burst
- Chandelier Exit
- Darvas Box
- Aggressive momentum strategies
"""

from typing import List, Dict

# High-beta growth stocks as of 2015-2020 period
# Selected for: Beta > 1.3, ATR > 2%, high liquidity
HIGH_BETA_UNIVERSE: Dict[str, Dict] = {
    # Tech Growth (highest beta)
    "NVDA": {"name": "NVIDIA", "sector": "technology", "beta_2015": 1.8},
    "AMD": {"name": "AMD", "sector": "technology", "beta_2015": 2.1},
    "TSLA": {"name": "Tesla", "sector": "consumer_discretionary", "beta_2015": 1.9},
    "SQ": {"name": "Block (Square)", "sector": "technology", "beta_2015": 2.0},
    "SHOP": {"name": "Shopify", "sector": "technology", "beta_2015": 1.8},
    "ROKU": {"name": "Roku", "sector": "communications", "beta_2015": 2.2},
    "SNAP": {"name": "Snap", "sector": "communications", "beta_2015": 1.9},
    "TWLO": {"name": "Twilio", "sector": "technology", "beta_2015": 1.7},
    "NET": {"name": "Cloudflare", "sector": "technology", "beta_2015": 1.8},
    "DDOG": {"name": "Datadog", "sector": "technology", "beta_2015": 1.6},
    "ZS": {"name": "Zscaler", "sector": "technology", "beta_2015": 1.7},
    "CRWD": {"name": "CrowdStrike", "sector": "technology", "beta_2015": 1.6},

    # Established high-beta tech
    "NFLX": {"name": "Netflix", "sector": "communications", "beta_2015": 1.5},
    "META": {"name": "Meta", "sector": "communications", "beta_2015": 1.3},
    "CRM": {"name": "Salesforce", "sector": "technology", "beta_2015": 1.4},
    "ADBE": {"name": "Adobe", "sector": "technology", "beta_2015": 1.3},
    "NOW": {"name": "ServiceNow", "sector": "technology", "beta_2015": 1.4},
    "PANW": {"name": "Palo Alto Networks", "sector": "technology", "beta_2015": 1.5},

    # Semiconductors (cyclical)
    "AVGO": {"name": "Broadcom", "sector": "technology", "beta_2015": 1.4},
    "MRVL": {"name": "Marvell", "sector": "technology", "beta_2015": 1.6},
    "MU": {"name": "Micron", "sector": "technology", "beta_2015": 1.8},
    "AMAT": {"name": "Applied Materials", "sector": "technology", "beta_2015": 1.5},
    "LRCX": {"name": "Lam Research", "sector": "technology", "beta_2015": 1.6},
    "KLAC": {"name": "KLA Corp", "sector": "technology", "beta_2015": 1.5},

    # Biotech (high volatility)
    "MRNA": {"name": "Moderna", "sector": "healthcare", "beta_2015": 2.0},
    "REGN": {"name": "Regeneron", "sector": "healthcare", "beta_2015": 1.4},
    "VRTX": {"name": "Vertex", "sector": "healthcare", "beta_2015": 1.3},
    "BIIB": {"name": "Biogen", "sector": "healthcare", "beta_2015": 1.5},
    "ILMN": {"name": "Illumina", "sector": "healthcare", "beta_2015": 1.4},

    # Energy (cyclical)
    "FSLR": {"name": "First Solar", "sector": "energy", "beta_2015": 1.8},
    "ENPH": {"name": "Enphase", "sector": "energy", "beta_2015": 2.0},
    "OXY": {"name": "Occidental", "sector": "energy", "beta_2015": 1.7},
    "FCX": {"name": "Freeport-McMoRan", "sector": "materials", "beta_2015": 1.9},

    # Consumer cyclical
    "LULU": {"name": "Lululemon", "sector": "consumer_discretionary", "beta_2015": 1.4},
    "RCL": {"name": "Royal Caribbean", "sector": "consumer_discretionary", "beta_2015": 1.8},
    "WYNN": {"name": "Wynn Resorts", "sector": "consumer_discretionary", "beta_2015": 1.7},
    "MGM": {"name": "MGM Resorts", "sector": "consumer_discretionary", "beta_2015": 1.6},

    # Financials (higher beta)
    "COIN": {"name": "Coinbase", "sector": "financials", "beta_2015": 2.5},
    "HOOD": {"name": "Robinhood", "sector": "financials", "beta_2015": 2.3},
    "MSTR": {"name": "MicroStrategy", "sector": "technology", "beta_2015": 2.8},
}


def get_high_beta_symbols(
    min_beta: float = 1.3,
    sectors: List[str] = None,
    max_stocks: int = None
) -> List[str]:
    """
    Get high-beta stock symbols.

    Args:
        min_beta: Minimum beta threshold
        sectors: Filter by sector
        max_stocks: Limit number of stocks

    Returns:
        List of ticker symbols
    """
    symbols = []

    for ticker, info in HIGH_BETA_UNIVERSE.items():
        if info.get("beta_2015", 0) < min_beta:
            continue
        if sectors and info["sector"] not in sectors:
            continue
        symbols.append(ticker)

    # Sort by beta (highest first)
    symbols.sort(key=lambda x: HIGH_BETA_UNIVERSE[x].get("beta_2015", 0), reverse=True)

    if max_stocks:
        symbols = symbols[:max_stocks]

    return symbols


def get_available_sectors() -> List[str]:
    """Get list of available sectors"""
    return list(set(info["sector"] for info in HIGH_BETA_UNIVERSE.values()))


# Pre-defined configurations
UNIVERSE_CONFIGS = {
    "full": {
        "symbols": list(HIGH_BETA_UNIVERSE.keys()),
        "description": "All high-beta stocks",
    },
    "tech_growth": {
        "symbols": get_high_beta_symbols(sectors=["technology", "communications"]),
        "description": "High-beta tech and communications",
    },
    "highest_beta": {
        "symbols": get_high_beta_symbols(min_beta=1.7),
        "description": "Stocks with beta > 1.7",
    },
    "semiconductor": {
        "symbols": ["NVDA", "AMD", "MU", "AVGO", "MRVL", "AMAT", "LRCX", "KLAC"],
        "description": "Semiconductor stocks only",
    },
}


DEFAULT_SYMBOLS = get_high_beta_symbols(min_beta=1.5, max_stocks=30)


if __name__ == "__main__":
    print("High-Beta Growth Universe (Universe D)")
    print("=" * 60)
    print(f"\nTotal stocks: {len(HIGH_BETA_UNIVERSE)}")
    print(f"\nAll symbols: {list(HIGH_BETA_UNIVERSE.keys())}")
    print(f"\nHighest beta (>1.7): {get_high_beta_symbols(min_beta=1.7)}")
    print(f"\nDefault (beta>1.5, max 30): {DEFAULT_SYMBOLS}")
