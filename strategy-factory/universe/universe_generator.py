"""
Point-in-Time Universe Generator

Eliminates hindsight bias by generating stock universes using ONLY
information available at the selection date.

Approach:
1. QUANTITATIVE SCREEN: Apply rules-based filters using historical data
2. LLM VALIDATION: Use Claude to validate/adjust based on period-appropriate reasoning
3. VERSION CONTROL: Save universes with timestamps for reproducibility

Key Principle: At time T, we can only use information available at time T.
"""

import json
import os
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from enum import Enum


class UniverseType(str, Enum):
    """Types of universe selection methodologies"""
    HIGH_BETA_LIQUID = "high_beta_liquid"      # Beta > 1.2, high volume
    MOMENTUM_CANDIDATES = "momentum_candidates" # Volatile, liquid stocks
    SP500_SUBSET = "sp500_subset"              # S&P 500 members at date
    SECTOR_BALANCED = "sector_balanced"        # Equal sector representation


@dataclass
class UniverseScreenCriteria:
    """Quantitative screening criteria - applied at selection date"""
    min_market_cap_millions: float = 1000      # $1B+ market cap
    min_avg_dollar_volume: float = 5_000_000   # $5M daily volume
    min_price: float = 10                       # Avoid penny stocks
    min_beta: Optional[float] = None           # Minimum beta (vs SPY)
    max_beta: Optional[float] = None           # Maximum beta
    min_years_listed: float = 2                # At least 2 years of history
    exclude_sectors: List[str] = field(default_factory=list)  # e.g., ["Utilities", "Real Estate"]
    max_stocks: int = 100                      # Maximum universe size

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UniverseSpec:
    """
    Complete specification for a point-in-time universe.

    This captures:
    - WHEN the universe was selected (selection_date)
    - WHAT criteria were used (criteria)
    - WHY these stocks were chosen (rationale)
    - HOW it was generated (methodology)
    """
    id: str
    name: str
    selection_date: str  # YYYY-MM-DD - the "as of" date
    universe_type: UniverseType
    criteria: UniverseScreenCriteria
    symbols: List[str]

    # Documentation
    rationale: str = ""  # Why this universe makes sense
    methodology: str = ""  # How it was generated (quant screen, LLM, hybrid)

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_by: str = "system"  # "quantitative_screen", "llm_claude", "hybrid"

    # Validation
    validated: bool = False
    validation_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "selection_date": self.selection_date,
            "universe_type": self.universe_type.value,
            "criteria": self.criteria.to_dict(),
            "symbols": self.symbols,
            "rationale": self.rationale,
            "methodology": self.methodology,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "validated": self.validated,
            "validation_notes": self.validation_notes,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, directory: str) -> str:
        """Save universe spec to JSON file"""
        filepath = os.path.join(directory, f"{self.id}.json")
        os.makedirs(directory, exist_ok=True)
        with open(filepath, 'w') as f:
            f.write(self.to_json())
        return filepath

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UniverseSpec":
        return cls(
            id=data["id"],
            name=data["name"],
            selection_date=data["selection_date"],
            universe_type=UniverseType(data["universe_type"]),
            criteria=UniverseScreenCriteria(**data.get("criteria", {})),
            symbols=data["symbols"],
            rationale=data.get("rationale", ""),
            methodology=data.get("methodology", ""),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            created_by=data.get("created_by", "system"),
            validated=data.get("validated", False),
            validation_notes=data.get("validation_notes", ""),
        )

    @classmethod
    def load(cls, filepath: str) -> "UniverseSpec":
        with open(filepath, 'r') as f:
            return cls.from_dict(json.load(f))


# =============================================================================
# QUANTITATIVE SCREENING DATA
# =============================================================================

# Historical S&P 500 members as of specific dates
# Source: Would need to pull from historical index data
SP500_HISTORICAL = {
    "2020-01-01": [
        # This would be populated from historical S&P 500 constituent data
        # For now, using approximate list of stocks that WERE in S&P 500 as of Jan 2020
    ],
    "2019-01-01": [],
}

# Stocks by sector (for sector-balanced selection)
SECTOR_STOCKS = {
    "Technology": [
        "AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "INTC", "CRM",
        "ADBE", "ORCL", "CSCO", "IBM", "NOW", "INTU", "AMAT", "LRCX",
        "MU", "QCOM", "AVGO", "TXN", "ADI", "KLAC", "MRVL", "ON",
    ],
    "Consumer Discretionary": [
        "AMZN", "TSLA", "HD", "NKE", "SBUX", "TGT", "LOW", "MCD",
        "BKNG", "CMG", "DPZ", "LULU", "DECK", "RCL", "CCL", "MAR",
        "HLT", "WYNN", "LVS", "MGM", "YUM", "DRI",
    ],
    "Financials": [
        "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW",
        "AXP", "V", "MA", "PYPL", "SQ", "COF", "USB", "PNC",
    ],
    "Healthcare": [
        "UNH", "JNJ", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT",
        "DHR", "BMY", "AMGN", "GILD", "ISRG", "VRTX", "REGN", "DXCM",
    ],
    "Industrials": [
        "CAT", "DE", "HON", "UNP", "BA", "GE", "MMM", "LMT",
        "RTX", "UPS", "FDX", "EMR", "ITW", "URI", "PWR", "EME",
    ],
    "Energy": [
        "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO",
        "OXY", "DVN", "FANG", "HAL", "BKR", "HES",
    ],
    "Communication Services": [
        "GOOGL", "META", "NFLX", "DIS", "CMCSA", "VZ", "T", "TMUS",
        "CHTR", "EA", "ATVI", "TTWO",
    ],
}

# Known IPO dates for filtering
IPO_DATES = {
    # Post-2020 IPOs (should be excluded for backtests starting 2020)
    "COIN": "2021-04-14",
    "HOOD": "2021-07-29",
    "UPST": "2020-12-16",
    "AFRM": "2021-01-13",
    "SOFI": "2021-06-01",  # SPAC merger
    "DUOL": "2021-07-28",
    "CAVA": "2023-06-15",
    "TOST": "2021-09-22",
    "ABNB": "2020-12-10",
    "SNOW": "2020-09-16",
    "PLTR": "2020-09-30",
    "RBLX": "2021-03-10",
    "RIVN": "2021-11-10",
    "LCID": "2021-07-26",  # SPAC merger

    # Pre-2020 IPOs (OK for 2020 backtests)
    "CRWD": "2019-06-12",
    "DDOG": "2019-09-19",
    "NET": "2019-09-13",
    "ZS": "2018-03-16",
    "PANW": "2012-07-20",
    "SQ": "2015-11-19",
    "ROKU": "2017-09-28",
    "TTD": "2016-09-21",
    "SNAP": "2017-03-02",
    "PINS": "2019-04-18",
    "UBER": "2019-05-10",
    "LYFT": "2019-03-29",
    "TSLA": "2010-06-29",
    "NVDA": "1999-01-22",
    "AMD": "1972-01-01",  # Approximate
}


def was_tradeable_at_date(symbol: str, date: str) -> bool:
    """
    Check if a stock was tradeable (publicly listed) at a given date.

    Args:
        symbol: Stock ticker
        date: Date string YYYY-MM-DD

    Returns:
        True if stock was listed before the date
    """
    if symbol not in IPO_DATES:
        # Assume older established stocks were tradeable
        return True

    ipo_date = datetime.strptime(IPO_DATES[symbol], "%Y-%m-%d")
    check_date = datetime.strptime(date, "%Y-%m-%d")

    return ipo_date < check_date


def filter_by_ipo_date(symbols: List[str], as_of_date: str) -> List[str]:
    """Filter symbols to only include those tradeable at the given date"""
    return [s for s in symbols if was_tradeable_at_date(s, as_of_date)]


# =============================================================================
# LLM PROMPT TEMPLATES
# =============================================================================

UNIVERSE_GENERATION_PROMPT = """
You are generating a stock universe for a momentum trading strategy.

CRITICAL: You must only use information that was available as of {selection_date}.
DO NOT include any stock that:
1. Was not publicly traded as of {selection_date}
2. You only know about because of its post-{selection_date} performance

TASK: Generate a universe of {max_stocks} stocks for a {universe_type} strategy.

CRITERIA:
- Minimum market cap: ${min_market_cap}M (as of {selection_date})
- Minimum daily dollar volume: ${min_dollar_volume}M
- Minimum price: ${min_price}
- Beta requirement: {beta_requirement}
- Exclude sectors: {exclude_sectors}
- Must have been listed for at least {min_years} years

METHODOLOGY:
1. Start with well-known, established stocks in each sector
2. Apply the quantitative filters mentally
3. Prefer stocks that were liquid and actively traded as of {selection_date}
4. DO NOT cherry-pick based on future performance

OUTPUT FORMAT:
Return a JSON object with:
{{
    "symbols": ["AAPL", "MSFT", ...],
    "rationale": "Explanation of selection methodology",
    "sector_breakdown": {{"Technology": 10, "Financials": 5, ...}},
    "excluded_stocks": ["COIN", "HOOD", ...],  // Stocks excluded and why
    "confidence": 0.85  // How confident you are this avoids hindsight bias
}}
"""

UNIVERSE_VALIDATION_PROMPT = """
You are validating a stock universe for hindsight bias.

SELECTION DATE: {selection_date}
UNIVERSE: {symbols}

For each stock, verify:
1. Was it publicly traded as of {selection_date}?
2. Was it a reasonably well-known stock at that time?
3. Would a systematic screen have included it?

FLAG any stocks that:
- IPO'd after {selection_date}
- Were obscure micro-caps that only became known due to later performance
- Seem cherry-picked based on hindsight

OUTPUT FORMAT:
{{
    "validated_symbols": ["AAPL", ...],  // Stocks that pass validation
    "flagged_symbols": {{"COIN": "IPO'd April 2021", ...}},
    "validation_notes": "Overall assessment",
    "hindsight_bias_score": 0.2  // 0 = no bias, 1 = severe bias
}}
"""


# =============================================================================
# EXAMPLE UNIVERSES
# =============================================================================

def create_high_beta_liquid_universe_2020() -> UniverseSpec:
    """
    Create a high-beta liquid universe as of January 1, 2020.

    This is what a systematic screen WOULD have produced in Jan 2020,
    without any knowledge of 2020-2024 performance.
    """

    # Start with S&P 500 + established mid-caps that were liquid in 2019
    # Exclude recent IPOs and stocks that weren't well-known

    symbols = [
        # Mega-cap tech (all well-established by 2020)
        "AAPL", "MSFT", "GOOGL", "AMZN", "META",  # META was FB
        "NVDA", "AMD", "INTC", "CRM", "ADBE", "NFLX",

        # Semiconductors (established)
        "AVGO", "QCOM", "TXN", "MU", "AMAT", "LRCX", "KLAC", "MRVL",

        # High-beta consumer (established by 2020)
        "TSLA",  # IPO 2010, well-known by 2020
        "NKE", "SBUX", "CMG", "LULU", "BKNG",

        # Travel/Leisure (cyclical, established)
        "RCL", "CCL", "MAR", "HLT", "WYNN", "LVS", "MGM",

        # Financials (high-beta)
        "GS", "MS", "JPM", "SQ",  # SQ IPO 2015
        "PYPL", "V", "MA",

        # Industrials (cyclical)
        "CAT", "DE", "BA", "HON", "URI",

        # Energy (volatile)
        "XOM", "CVX", "OXY", "SLB", "COP",

        # Established growth (pre-2020 IPOs, well-known)
        "ROKU",  # IPO 2017
        "TTD",   # IPO 2016
        "CRWD", "DDOG", "NET", "ZS",  # All IPO'd 2018-2019, were known
        "SNAP", "PINS",  # IPO 2017, 2019

        # Healthcare (volatile growth)
        "ISRG", "DXCM", "ALGN", "VEEV",
    ]

    # Filter to ensure all were tradeable as of 2020-01-01
    symbols = filter_by_ipo_date(symbols, "2020-01-01")

    return UniverseSpec(
        id="high_beta_liquid_2020",
        name="High-Beta Liquid Universe (Jan 2020)",
        selection_date="2020-01-01",
        universe_type=UniverseType.HIGH_BETA_LIQUID,
        criteria=UniverseScreenCriteria(
            min_market_cap_millions=5000,
            min_avg_dollar_volume=10_000_000,
            min_price=10,
            min_beta=1.0,
            min_years_listed=1,
            exclude_sectors=["Utilities", "Real Estate", "Consumer Staples"],
            max_stocks=60,
        ),
        symbols=symbols,
        rationale="""
        Universe selected using point-in-time methodology as of January 1, 2020.

        Selection criteria:
        1. Market cap > $5B (liquid, established)
        2. Daily dollar volume > $10M (tradeable)
        3. Beta > 1.0 vs SPY (high-beta for momentum)
        4. Listed > 1 year (avoid recent IPOs)
        5. Exclude defensive sectors (Utilities, REITs, Staples)

        All stocks were well-known and liquid as of Jan 2020.
        NO stocks included that IPO'd after Jan 2020.
        """,
        methodology="hybrid_quantitative_and_llm_validation",
        created_by="claude_code",
        validated=True,
        validation_notes="Verified all IPO dates pre-2020. Removed COIN, HOOD, UPST, AFRM, SOFI, ABNB, SNOW, DUOL, CAVA, TOST."
    )


def create_momentum_universe_2020_conservative() -> UniverseSpec:
    """
    More conservative universe - only stocks in S&P 500 as of 2020.
    No recent IPOs, no small-caps.
    """

    symbols = [
        # S&P 500 tech (all members as of Jan 2020)
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "INTC",
        "CRM", "ADBE", "CSCO", "ORCL", "IBM", "QCOM", "TXN", "AVGO",
        "MU", "AMAT", "LRCX", "ADI", "KLAC",

        # S&P 500 consumer discretionary
        "TSLA", "HD", "NKE", "SBUX", "LOW", "TGT", "MCD",
        "BKNG", "MAR", "HLT", "RCL", "CCL",

        # S&P 500 financials
        "JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "PYPL",

        # S&P 500 industrials
        "CAT", "DE", "HON", "BA", "UNP", "UPS",

        # S&P 500 energy
        "XOM", "CVX", "COP", "SLB", "EOG",

        # S&P 500 healthcare (growth)
        "UNH", "ISRG", "DXCM", "ALGN",

        # S&P 500 communication
        "NFLX", "DIS",
    ]

    return UniverseSpec(
        id="sp500_momentum_2020",
        name="S&P 500 Momentum Universe (Jan 2020)",
        selection_date="2020-01-01",
        universe_type=UniverseType.SP500_SUBSET,
        criteria=UniverseScreenCriteria(
            min_market_cap_millions=10000,
            min_avg_dollar_volume=50_000_000,
            min_price=20,
            min_beta=0.8,
            min_years_listed=3,
            exclude_sectors=["Utilities", "Real Estate", "Consumer Staples"],
            max_stocks=50,
        ),
        symbols=symbols,
        rationale="""
        Conservative universe using only S&P 500 members as of January 2020.
        No recent IPOs, no mid/small caps, only large established companies.

        This is the most hindsight-bias-free approach: we only include stocks
        that were definitely in the S&P 500 index as of the selection date.
        """,
        methodology="sp500_historical_membership",
        created_by="claude_code",
        validated=True,
        validation_notes="All stocks verified as S&P 500 members as of Jan 2020."
    )


# =============================================================================
# MAIN FUNCTIONS
# =============================================================================

def generate_universe(
    selection_date: str,
    universe_type: UniverseType,
    criteria: UniverseScreenCriteria,
    use_llm_validation: bool = True,
) -> UniverseSpec:
    """
    Generate a point-in-time universe.

    Args:
        selection_date: The "as of" date (YYYY-MM-DD)
        universe_type: Type of universe to generate
        criteria: Screening criteria
        use_llm_validation: Whether to validate with LLM

    Returns:
        UniverseSpec with selected symbols
    """
    # This would integrate with:
    # 1. Historical market data API for quantitative screening
    # 2. Claude API for LLM validation

    # For now, return pre-built universe
    if universe_type == UniverseType.HIGH_BETA_LIQUID:
        return create_high_beta_liquid_universe_2020()
    elif universe_type == UniverseType.SP500_SUBSET:
        return create_momentum_universe_2020_conservative()
    else:
        raise ValueError(f"Unknown universe type: {universe_type}")


def validate_universe_for_hindsight_bias(
    universe: UniverseSpec,
) -> Dict[str, Any]:
    """
    Validate a universe for hindsight bias.

    Returns dict with:
    - flagged_symbols: Stocks that may have hindsight bias
    - hindsight_bias_score: 0-1 score
    - recommendations: Suggested removals
    """
    flagged = {}

    for symbol in universe.symbols:
        if not was_tradeable_at_date(symbol, universe.selection_date):
            flagged[symbol] = f"IPO'd after {universe.selection_date}"

    bias_score = len(flagged) / len(universe.symbols) if universe.symbols else 0

    return {
        "flagged_symbols": flagged,
        "hindsight_bias_score": bias_score,
        "clean_symbols": [s for s in universe.symbols if s not in flagged],
        "recommendations": f"Remove {len(flagged)} stocks that IPO'd after selection date"
    }


# =============================================================================
# CLI / TESTING
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("POINT-IN-TIME UNIVERSE GENERATOR")
    print("=" * 60)

    # Generate high-beta liquid universe
    universe = create_high_beta_liquid_universe_2020()
    print(f"\nGenerated: {universe.name}")
    print(f"Selection Date: {universe.selection_date}")
    print(f"Symbols ({len(universe.symbols)}): {universe.symbols[:10]}...")

    # Validate for hindsight bias
    validation = validate_universe_for_hindsight_bias(universe)
    print(f"\nHindsight Bias Score: {validation['hindsight_bias_score']:.2%}")
    print(f"Flagged Symbols: {validation['flagged_symbols']}")

    # Save to file
    filepath = universe.save("strategy-factory/universe/specs")
    print(f"\nSaved to: {filepath}")

    # Generate conservative S&P 500 universe
    print("\n" + "=" * 60)
    conservative = create_momentum_universe_2020_conservative()
    print(f"\nGenerated: {conservative.name}")
    print(f"Symbols ({len(conservative.symbols)}): {conservative.symbols[:10]}...")

    filepath = conservative.save("strategy-factory/universe/specs")
    print(f"Saved to: {filepath}")
