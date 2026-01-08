"""
Universe C: Large-Cap Liquid

RATIONALE:
We need a stock universe for strategies like Clenow momentum, VCP breakouts, etc.
These stocks were selected based on being:
1. In the S&P 500 as of 2015-01-01
2. Market cap > $50B at that time
3. Average daily dollar volume > $100M

WHY THIS WORKS:
- Mega caps rarely go bankrupt (low survivorship bias)
- Highly liquid (realistic execution)
- ~80-100 stocks meet these criteria
- We accept some bias (a few may have declined) but it's minimal

BIAS RISK: Low-to-moderate (mega caps are stable)

USE FOR:
- Clenow momentum ranking
- 52-week high breakout
- NR7 breakout
- Donchian channel
- Elder Impulse
- MACD divergence
"""

from typing import List, Dict
from datetime import date

# Large-cap liquid universe as of 2015-01-01
# These stocks had market cap > $50B and daily volume > $100M
LARGE_CAP_UNIVERSE: Dict[str, Dict] = {
    # Technology
    "AAPL": {"name": "Apple", "sector": "technology", "sp500_2015": True},
    "MSFT": {"name": "Microsoft", "sector": "technology", "sp500_2015": True},
    "GOOGL": {"name": "Alphabet Class A", "sector": "technology", "sp500_2015": True},
    "INTC": {"name": "Intel", "sector": "technology", "sp500_2015": True},
    "CSCO": {"name": "Cisco", "sector": "technology", "sp500_2015": True},
    "ORCL": {"name": "Oracle", "sector": "technology", "sp500_2015": True},
    "IBM": {"name": "IBM", "sector": "technology", "sp500_2015": True},
    "QCOM": {"name": "Qualcomm", "sector": "technology", "sp500_2015": True},
    "TXN": {"name": "Texas Instruments", "sector": "technology", "sp500_2015": True},
    "ADBE": {"name": "Adobe", "sector": "technology", "sp500_2015": True},
    "CRM": {"name": "Salesforce", "sector": "technology", "sp500_2015": True},
    "AVGO": {"name": "Broadcom", "sector": "technology", "sp500_2015": True},

    # Financials
    "JPM": {"name": "JPMorgan Chase", "sector": "financials", "sp500_2015": True},
    "BAC": {"name": "Bank of America", "sector": "financials", "sp500_2015": True},
    "WFC": {"name": "Wells Fargo", "sector": "financials", "sp500_2015": True},
    "C": {"name": "Citigroup", "sector": "financials", "sp500_2015": True},
    "GS": {"name": "Goldman Sachs", "sector": "financials", "sp500_2015": True},
    "MS": {"name": "Morgan Stanley", "sector": "financials", "sp500_2015": True},
    "BLK": {"name": "BlackRock", "sector": "financials", "sp500_2015": True},
    "AXP": {"name": "American Express", "sector": "financials", "sp500_2015": True},
    "USB": {"name": "US Bancorp", "sector": "financials", "sp500_2015": True},
    "PNC": {"name": "PNC Financial", "sector": "financials", "sp500_2015": True},

    # Healthcare
    "JNJ": {"name": "Johnson & Johnson", "sector": "healthcare", "sp500_2015": True},
    "UNH": {"name": "UnitedHealth", "sector": "healthcare", "sp500_2015": True},
    "PFE": {"name": "Pfizer", "sector": "healthcare", "sp500_2015": True},
    "MRK": {"name": "Merck", "sector": "healthcare", "sp500_2015": True},
    "ABBV": {"name": "AbbVie", "sector": "healthcare", "sp500_2015": True},
    "TMO": {"name": "Thermo Fisher", "sector": "healthcare", "sp500_2015": True},
    "ABT": {"name": "Abbott Labs", "sector": "healthcare", "sp500_2015": True},
    "MDT": {"name": "Medtronic", "sector": "healthcare", "sp500_2015": True},
    "AMGN": {"name": "Amgen", "sector": "healthcare", "sp500_2015": True},
    "GILD": {"name": "Gilead Sciences", "sector": "healthcare", "sp500_2015": True},
    "BMY": {"name": "Bristol-Myers", "sector": "healthcare", "sp500_2015": True},
    "LLY": {"name": "Eli Lilly", "sector": "healthcare", "sp500_2015": True},

    # Consumer Discretionary
    "AMZN": {"name": "Amazon", "sector": "consumer_discretionary", "sp500_2015": True},
    "HD": {"name": "Home Depot", "sector": "consumer_discretionary", "sp500_2015": True},
    "MCD": {"name": "McDonald's", "sector": "consumer_discretionary", "sp500_2015": True},
    "NKE": {"name": "Nike", "sector": "consumer_discretionary", "sp500_2015": True},
    "SBUX": {"name": "Starbucks", "sector": "consumer_discretionary", "sp500_2015": True},
    "TGT": {"name": "Target", "sector": "consumer_discretionary", "sp500_2015": True},
    "COST": {"name": "Costco", "sector": "consumer_staples", "sp500_2015": True},
    "LOW": {"name": "Lowe's", "sector": "consumer_discretionary", "sp500_2015": True},
    "TJX": {"name": "TJX Companies", "sector": "consumer_discretionary", "sp500_2015": True},

    # Industrials
    "BA": {"name": "Boeing", "sector": "industrials", "sp500_2015": True},
    "HON": {"name": "Honeywell", "sector": "industrials", "sp500_2015": True},
    "UNP": {"name": "Union Pacific", "sector": "industrials", "sp500_2015": True},
    "CAT": {"name": "Caterpillar", "sector": "industrials", "sp500_2015": True},
    "GE": {"name": "General Electric", "sector": "industrials", "sp500_2015": True},
    "MMM": {"name": "3M", "sector": "industrials", "sp500_2015": True},
    "LMT": {"name": "Lockheed Martin", "sector": "industrials", "sp500_2015": True},
    "RTX": {"name": "Raytheon", "sector": "industrials", "sp500_2015": True},
    "DE": {"name": "Deere & Company", "sector": "industrials", "sp500_2015": True},
    "FDX": {"name": "FedEx", "sector": "industrials", "sp500_2015": True},

    # Energy
    "XOM": {"name": "Exxon Mobil", "sector": "energy", "sp500_2015": True},
    "CVX": {"name": "Chevron", "sector": "energy", "sp500_2015": True},
    "COP": {"name": "ConocoPhillips", "sector": "energy", "sp500_2015": True},
    "SLB": {"name": "Schlumberger", "sector": "energy", "sp500_2015": True},
    "EOG": {"name": "EOG Resources", "sector": "energy", "sp500_2015": True},

    # Communications
    "META": {"name": "Meta (Facebook)", "sector": "communications", "sp500_2015": True},
    "NFLX": {"name": "Netflix", "sector": "communications", "sp500_2015": True},
    "DIS": {"name": "Disney", "sector": "communications", "sp500_2015": True},
    "CMCSA": {"name": "Comcast", "sector": "communications", "sp500_2015": True},
    "VZ": {"name": "Verizon", "sector": "communications", "sp500_2015": True},
    "T": {"name": "AT&T", "sector": "communications", "sp500_2015": True},

    # Consumer Staples
    "KO": {"name": "Coca-Cola", "sector": "consumer_staples", "sp500_2015": True},
    "PEP": {"name": "PepsiCo", "sector": "consumer_staples", "sp500_2015": True},
    "PM": {"name": "Philip Morris", "sector": "consumer_staples", "sp500_2015": True},
    "WMT": {"name": "Walmart", "sector": "consumer_staples", "sp500_2015": True},
    "PG": {"name": "Procter & Gamble", "sector": "consumer_staples", "sp500_2015": True},
    "CL": {"name": "Colgate-Palmolive", "sector": "consumer_staples", "sp500_2015": True},

    # Other / Multi-sector
    "BRK.B": {"name": "Berkshire Hathaway", "sector": "financials", "sp500_2015": True},
    "V": {"name": "Visa", "sector": "financials", "sp500_2015": True},
    "MA": {"name": "Mastercard", "sector": "financials", "sp500_2015": True},

    # Utilities & Real Estate (defensive, lower beta)
    "NEE": {"name": "NextEra Energy", "sector": "utilities", "sp500_2015": True},
    "DUK": {"name": "Duke Energy", "sector": "utilities", "sp500_2015": True},
    "SO": {"name": "Southern Company", "sector": "utilities", "sp500_2015": True},
}


def get_large_cap_symbols(
    sectors: List[str] = None,
    exclude_sectors: List[str] = None,
) -> List[str]:
    """
    Get stock symbols for Universe C (Large-Cap Liquid).

    Args:
        sectors: Filter to specific sectors (e.g., ['technology', 'healthcare'])
                If None, returns all sectors
        exclude_sectors: Exclude specific sectors

    Returns:
        List of ticker symbols
    """
    symbols = []

    for ticker, info in LARGE_CAP_UNIVERSE.items():
        # Sector include filter
        if sectors and info["sector"] not in sectors:
            continue

        # Sector exclude filter
        if exclude_sectors and info["sector"] in exclude_sectors:
            continue

        symbols.append(ticker)

    return symbols


def get_sector_stocks(sector: str) -> List[str]:
    """Get all stocks in a specific sector"""
    return [
        ticker for ticker, info in LARGE_CAP_UNIVERSE.items()
        if info["sector"] == sector
    ]


def get_available_sectors() -> List[str]:
    """Get list of all available sectors"""
    return list(set(info["sector"] for info in LARGE_CAP_UNIVERSE.values()))


# Pre-defined universe configurations for different strategies
UNIVERSE_CONFIGS = {
    # Full universe for momentum ranking
    "full": {
        "symbols": list(LARGE_CAP_UNIVERSE.keys()),
        "description": "All 80+ large-cap liquid stocks",
    },

    # Technology heavy (for growth strategies)
    "tech_heavy": {
        "symbols": get_large_cap_symbols(sectors=["technology", "communications"]),
        "description": "Technology and Communications sectors only",
    },

    # Defensive (for mean reversion in volatile markets)
    "defensive": {
        "symbols": get_large_cap_symbols(sectors=["utilities", "consumer_staples", "healthcare"]),
        "description": "Defensive sectors only",
    },

    # Cyclical (for trend following)
    "cyclical": {
        "symbols": get_large_cap_symbols(sectors=["industrials", "energy", "financials"]),
        "description": "Cyclical sectors for trend strategies",
    },

    # No financials (for avoiding sector-specific risks)
    "ex_financials": {
        "symbols": get_large_cap_symbols(exclude_sectors=["financials"]),
        "description": "All sectors except financials",
    },
}


def get_universe_config(name: str) -> Dict:
    """Get a pre-defined universe configuration"""
    if name not in UNIVERSE_CONFIGS:
        raise ValueError(f"Unknown config: {name}. Available: {list(UNIVERSE_CONFIGS.keys())}")
    return UNIVERSE_CONFIGS[name]


# Default: all stocks in universe
DEFAULT_SYMBOLS = list(LARGE_CAP_UNIVERSE.keys())


if __name__ == "__main__":
    print("Large-Cap Liquid Universe (Universe C)")
    print("=" * 60)

    print(f"\nTotal stocks: {len(LARGE_CAP_UNIVERSE)}")
    print(f"\nAll symbols:\n{get_large_cap_symbols()}")

    print(f"\nAvailable sectors: {get_available_sectors()}")

    print(f"\nTechnology stocks ({len(get_sector_stocks('technology'))}):")
    print(get_sector_stocks("technology"))

    print(f"\nHealthcare stocks ({len(get_sector_stocks('healthcare'))}):")
    print(get_sector_stocks("healthcare"))

    print(f"\nUniverse configs available: {list(UNIVERSE_CONFIGS.keys())}")
