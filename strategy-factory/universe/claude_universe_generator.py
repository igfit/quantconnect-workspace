"""
Claude-Powered Universe Generator

Uses Claude AI to generate and validate stock universes with minimal hindsight bias.

Key Features:
1. FEATURE-BASED SELECTION: Identify stocks by characteristics, not returns
2. LLM GENERATION: Claude generates picks based on criteria
3. LLM VALIDATION: Claude validates for hindsight bias
4. QUANTITATIVE FILTERS: Apply hard constraints

Non-Hindsight Features for Momentum Candidates:
- High Beta (>1.0): Amplifies market moves
- High Volatility: More momentum opportunities
- Liquid: High daily volume enables trading
- Cyclical Sector: Tech, Consumer Disc, Energy have momentum
- Growth Characteristics: Revenue growth, high P/E
- Market Leadership: Leading position in growing industry
- Institutional Interest: Analyst coverage, fund ownership
- Mid-to-Large Cap: Liquid but can still move significantly

Usage:
    export ANTHROPIC_API_KEY="your-key"
    python claude_universe_generator.py --date 2020-01-01 --type high_beta
"""

import os
import json
import re
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any, Tuple
from enum import Enum
import anthropic


# =============================================================================
# CONFIGURATION
# =============================================================================

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"  # Fast and capable


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class UniverseType(str, Enum):
    HIGH_BETA_MOMENTUM = "high_beta_momentum"
    GROWTH_LEADERS = "growth_leaders"
    CYCLICAL_VALUE = "cyclical_value"
    SECTOR_BALANCED = "sector_balanced"
    LIQUID_VOLATILE = "liquid_volatile"


@dataclass
class StockFeatures:
    """
    Non-hindsight features that characterize good momentum candidates.
    These are observable BEFORE knowing future returns.
    """
    # Volatility & Beta
    high_beta: bool = False           # Beta > 1.2 vs SPY
    high_volatility: bool = False     # Above-average price swings

    # Liquidity
    highly_liquid: bool = False       # Top quartile daily volume
    tight_spreads: bool = False       # Low bid-ask spread

    # Growth Characteristics
    revenue_growth: bool = False      # Growing revenues
    expanding_margins: bool = False   # Improving profitability
    high_pe_ratio: bool = False       # Growth premium valuation

    # Market Position
    market_leader: bool = False       # #1-3 in industry
    growing_industry: bool = False    # Industry tailwinds
    disruptor: bool = False          # Disrupting incumbents

    # Institutional Interest
    high_analyst_coverage: bool = False   # Many analysts covering
    institutional_buying: bool = False    # Funds accumulating
    recent_upgrades: bool = False         # Positive sentiment shift

    # Sector
    sector: str = ""
    is_cyclical: bool = False        # Cyclical vs defensive

    # Other
    years_public: float = 0          # Years since IPO
    market_cap_tier: str = ""        # mega, large, mid, small


@dataclass
class UniverseCandidate:
    """A stock candidate with its features and selection rationale"""
    symbol: str
    name: str
    features: StockFeatures
    selection_rationale: str
    confidence_score: float  # 0-1, how confident we are this isn't hindsight


@dataclass
class GeneratedUniverse:
    """Complete generated universe with full documentation"""
    id: str
    name: str
    selection_date: str
    universe_type: UniverseType

    # The stocks
    candidates: List[UniverseCandidate]
    final_symbols: List[str]

    # Generation metadata
    generation_prompt: str
    generation_response: str
    validation_prompt: str
    validation_response: str

    # Criteria used
    feature_criteria: Dict[str, Any]
    quantitative_filters: Dict[str, Any]

    # Audit trail
    excluded_symbols: Dict[str, str]  # symbol -> reason
    hindsight_flags: Dict[str, str]   # symbol -> concern

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "selection_date": self.selection_date,
            "universe_type": self.universe_type.value,
            "final_symbols": self.final_symbols,
            "candidates": [
                {
                    "symbol": c.symbol,
                    "name": c.name,
                    "selection_rationale": c.selection_rationale,
                    "confidence_score": c.confidence_score,
                }
                for c in self.candidates
            ],
            "feature_criteria": self.feature_criteria,
            "quantitative_filters": self.quantitative_filters,
            "excluded_symbols": self.excluded_symbols,
            "hindsight_flags": self.hindsight_flags,
            "generation_prompt": self.generation_prompt,
            "validation_prompt": self.validation_prompt,
            "created_at": self.created_at,
        }

    def save(self, directory: str) -> str:
        filepath = os.path.join(directory, f"{self.id}.json")
        os.makedirs(directory, exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        return filepath


# =============================================================================
# KNOWN DATA (for validation)
# =============================================================================

# IPO dates for filtering
IPO_DATES = {
    # Post-2020 IPOs
    "COIN": "2021-04-14", "HOOD": "2021-07-29", "UPST": "2020-12-16",
    "AFRM": "2021-01-13", "SOFI": "2021-06-01", "DUOL": "2021-07-28",
    "CAVA": "2023-06-15", "TOST": "2021-09-22", "ABNB": "2020-12-10",
    "SNOW": "2020-09-16", "PLTR": "2020-09-30", "RBLX": "2021-03-10",
    "RIVN": "2021-11-10", "LCID": "2021-07-26", "DASH": "2020-12-09",
    "U": "2020-09-18", "AI": "2020-12-09", "PATH": "2021-04-21",
    "DKNG": "2020-04-24", "BILL": "2019-12-12",

    # 2019 IPOs (borderline for 2020 backtest)
    "CRWD": "2019-06-12", "DDOG": "2019-09-19", "NET": "2019-09-13",
    "PINS": "2019-04-18", "UBER": "2019-05-10", "LYFT": "2019-03-29",
    "ZM": "2019-04-18", "BYND": "2019-05-02", "PTON": "2019-09-26",

    # 2018 and earlier (safe for 2020)
    "ZS": "2018-03-16", "DOCU": "2018-04-27", "SPOT": "2018-04-03",
    "DBX": "2018-03-23", "ROKU": "2017-09-28", "TTD": "2016-09-21",
    "SNAP": "2017-03-02", "SQ": "2015-11-19", "SHOP": "2015-05-21",
    "TWLO": "2016-06-23", "OKTA": "2017-04-07", "MDB": "2017-10-19",
    "TSLA": "2010-06-29", "NVDA": "1999-01-22", "AMD": "1979-01-01",
}

# Sector classifications
SECTOR_MAP = {
    "Technology": ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMD", "INTC", "CRM",
                   "ADBE", "ORCL", "CSCO", "IBM", "NOW", "INTU", "AMAT", "LRCX",
                   "MU", "QCOM", "AVGO", "TXN", "ADI", "KLAC", "MRVL", "ON",
                   "CRWD", "DDOG", "NET", "ZS", "PANW", "SNOW", "OKTA", "TWLO"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD", "NKE", "SBUX", "TGT", "LOW",
                               "MCD", "BKNG", "CMG", "DPZ", "LULU", "DECK", "CROX",
                               "RCL", "CCL", "MAR", "HLT", "WYNN", "LVS", "MGM"],
    "Financials": ["JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP",
                   "V", "MA", "PYPL", "SQ", "COF", "USB", "PNC", "COIN", "HOOD"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY",
               "DVN", "FANG", "HAL", "BKR", "HES"],
    "Healthcare": ["UNH", "JNJ", "PFE", "ABBV", "MRK", "LLY", "TMO", "ABT", "DHR",
                   "BMY", "AMGN", "GILD", "ISRG", "VRTX", "REGN", "DXCM", "ALGN"],
    "Industrials": ["CAT", "DE", "HON", "UNP", "BA", "GE", "MMM", "LMT", "RTX",
                    "UPS", "FDX", "EMR", "ITW", "URI", "PWR", "EME", "AXON"],
    "Communication": ["GOOGL", "META", "NFLX", "DIS", "CMCSA", "VZ", "T", "TMUS"],
}

CYCLICAL_SECTORS = ["Technology", "Consumer Discretionary", "Financials", "Energy", "Industrials"]
DEFENSIVE_SECTORS = ["Utilities", "Consumer Staples", "Healthcare", "Real Estate"]


# =============================================================================
# PROMPTS
# =============================================================================

UNIVERSE_GENERATION_PROMPT = """You are a quantitative analyst selecting stocks for a momentum trading strategy.

CRITICAL CONSTRAINT: You are selecting stocks AS OF {selection_date}. You must ONLY use information that was publicly available before this date. Do NOT use any knowledge of how stocks performed AFTER this date.

TASK: Generate a list of {num_stocks} stocks that match these criteria:

UNIVERSE TYPE: {universe_type}

FEATURE REQUIREMENTS:
{feature_requirements}

QUANTITATIVE FILTERS:
- Minimum market cap: ${min_market_cap}B
- Minimum daily dollar volume: ${min_volume}M
- Must have been publicly traded for at least {min_years_listed} years as of {selection_date}
- Exclude sectors: {exclude_sectors}

SELECTION METHODOLOGY:
Think about what stocks LOOKED LIKE good momentum candidates as of {selection_date}, based on:

1. BETA & VOLATILITY: Which stocks historically moved more than the market?
2. LIQUIDITY: Which stocks had high trading volume and tight spreads?
3. GROWTH CHARACTERISTICS: Which companies were growing revenues and had growth valuations?
4. MARKET POSITION: Which companies were leaders in growing industries?
5. INSTITUTIONAL INTEREST: Which stocks had high analyst coverage and fund ownership?
6. SECTOR: Focus on cyclical sectors that exhibit momentum (tech, consumer disc, energy, industrials)

DO NOT SELECT BASED ON:
- How the stock performed after {selection_date}
- Knowledge of events that happened after {selection_date}
- Stocks that IPO'd after {selection_date}

For each stock, explain WHY it would have been selected based on information available AS OF {selection_date}.

OUTPUT FORMAT (JSON):
{{
    "stocks": [
        {{
            "symbol": "NVDA",
            "name": "NVIDIA Corporation",
            "sector": "Technology",
            "selection_rationale": "As of Jan 2020, NVIDIA was the dominant GPU maker with 80%+ market share in gaming and data center. High beta (~1.5), highly liquid ($5B+ daily volume), strong revenue growth from gaming and data center. Well-covered by analysts with mostly buy ratings.",
            "features": {{
                "high_beta": true,
                "high_volatility": true,
                "highly_liquid": true,
                "revenue_growth": true,
                "market_leader": true,
                "growing_industry": true,
                "is_cyclical": true
            }},
            "confidence_no_hindsight": 0.95
        }},
        ...
    ],
    "methodology_notes": "Explanation of overall selection approach",
    "potential_biases": "Any concerns about hindsight that crept in"
}}
"""

UNIVERSE_VALIDATION_PROMPT = """You are auditing a stock universe for hindsight bias.

SELECTION DATE: {selection_date}
UNIVERSE TO VALIDATE: {symbols}

For EACH stock, evaluate:

1. IPO CHECK: Was this stock publicly traded as of {selection_date}?
2. NOTORIETY CHECK: Was this stock well-known to institutional investors as of {selection_date}?
3. HINDSIGHT CHECK: Does this selection seem influenced by knowledge of post-{selection_date} performance?
4. FEATURE CHECK: Did this stock actually have the claimed features (high beta, liquid, etc.) as of {selection_date}?

RED FLAGS to look for:
- Stocks that IPO'd after {selection_date}
- Obscure small-caps that only became known due to later performance
- Stocks selected primarily because they "turned out to be good"
- Missing obvious candidates that would have fit criteria but didn't perform well

OUTPUT FORMAT (JSON):
{{
    "validated_stocks": [
        {{
            "symbol": "NVDA",
            "ipo_check": "PASS - IPO'd 1999",
            "notoriety_check": "PASS - Major semiconductor, widely covered",
            "hindsight_check": "PASS - Would have been selected based on 2019 fundamentals",
            "feature_check": "PASS - High beta, liquid, market leader confirmed",
            "overall": "PASS",
            "confidence": 0.95
        }},
        {{
            "symbol": "UPST",
            "ipo_check": "FAIL - IPO'd December 2020",
            "notoriety_check": "FAIL - Unknown before IPO",
            "hindsight_check": "FAIL - Only known due to 2021 performance",
            "feature_check": "N/A",
            "overall": "REJECT",
            "confidence": 0.99
        }},
        ...
    ],
    "missing_candidates": ["Stocks that should have been included but weren't"],
    "overall_bias_score": 0.15,
    "recommendations": "Summary of changes needed"
}}
"""

FEATURE_EXTRACTION_PROMPT = """You are analyzing what characteristics made certain stocks good momentum candidates.

CONTEXT: We're trying to identify NON-HINDSIGHT features that predict which stocks are good for momentum strategies.

TASK: For the following well-established momentum stocks, identify what features they had IN COMMON that were observable BEFORE their strong performance:

STOCKS TO ANALYZE (known good momentum stocks historically):
- NVDA, AMD, TSLA (tech/growth)
- GS, MS (financials)
- CAT, DE (industrials)
- XOM, OXY (energy)
- RCL, WYNN (consumer cyclical)

For each category, identify:
1. What BETA characteristics did they share?
2. What VOLATILITY patterns were common?
3. What LIQUIDITY features?
4. What GROWTH characteristics?
5. What MARKET POSITION attributes?
6. What SECTOR/CYCLICALITY patterns?

The goal is to find features we can use to SELECT future momentum candidates WITHOUT knowing their future returns.

OUTPUT FORMAT (JSON):
{{
    "common_features": {{
        "beta": {{
            "pattern": "Description of beta pattern",
            "threshold": "Specific threshold if applicable",
            "importance": "high/medium/low"
        }},
        "volatility": {{...}},
        "liquidity": {{...}},
        "growth": {{...}},
        "market_position": {{...}},
        "sector": {{...}}
    }},
    "feature_importance_ranking": [
        "Most predictive feature",
        "Second most predictive",
        ...
    ],
    "selection_rules": [
        "Rule 1: Select stocks with beta > X",
        "Rule 2: ...",
        ...
    ],
    "anti_patterns": [
        "Avoid stocks with characteristic X",
        ...
    ]
}}
"""


# =============================================================================
# CLAUDE API CLIENT
# =============================================================================

class ClaudeUniverseGenerator:
    """Uses Claude to generate and validate stock universes"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or ANTHROPIC_API_KEY
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set. Export it or pass to constructor.")
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def _call_claude(self, prompt: str, max_tokens: int = 4096) -> str:
        """Make a call to Claude API"""
        message = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return message.content[0].text

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Extract JSON from Claude's response"""
        # Try to find JSON block
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))

        # Try to find raw JSON
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))

        raise ValueError(f"Could not parse JSON from response: {response[:500]}")

    def extract_momentum_features(self) -> Dict[str, Any]:
        """
        Use Claude to identify common features of good momentum stocks.
        This helps us build selection criteria without hindsight.
        """
        print("Extracting common momentum stock features...")

        response = self._call_claude(FEATURE_EXTRACTION_PROMPT, max_tokens=2048)

        try:
            features = self._parse_json_response(response)
            return features
        except Exception as e:
            print(f"Warning: Could not parse features response: {e}")
            return {"raw_response": response}

    def generate_universe(
        self,
        selection_date: str,
        universe_type: UniverseType,
        num_stocks: int = 60,
        min_market_cap_billions: float = 5,
        min_volume_millions: float = 10,
        min_years_listed: float = 1,
        exclude_sectors: List[str] = None,
        feature_requirements: str = None,
    ) -> Tuple[List[Dict], str, str]:
        """
        Generate a stock universe using Claude.

        Returns:
            Tuple of (list of stock dicts, prompt used, raw response)
        """
        if exclude_sectors is None:
            exclude_sectors = ["Utilities", "Real Estate", "Consumer Staples"]

        if feature_requirements is None:
            feature_requirements = """
- High Beta (>1.0 vs SPY): Stocks that move more than the market
- High Liquidity: Daily dollar volume > $10M, actively traded
- Growth Characteristics: Revenue growth, market expansion
- Cyclical Sector: Technology, Consumer Discretionary, Financials, Energy, Industrials
- Market Leadership: Top 3 position in their industry/niche
- Institutional Interest: Covered by multiple analysts
"""

        prompt = UNIVERSE_GENERATION_PROMPT.format(
            selection_date=selection_date,
            universe_type=universe_type.value,
            num_stocks=num_stocks,
            min_market_cap=min_market_cap_billions,
            min_volume=min_volume_millions,
            min_years_listed=min_years_listed,
            exclude_sectors=", ".join(exclude_sectors),
            feature_requirements=feature_requirements,
        )

        print(f"Generating {universe_type.value} universe as of {selection_date}...")
        response = self._call_claude(prompt, max_tokens=8192)

        try:
            parsed = self._parse_json_response(response)
            stocks = parsed.get("stocks", [])
            return stocks, prompt, response
        except Exception as e:
            print(f"Warning: Could not parse generation response: {e}")
            return [], prompt, response

    def validate_universe(
        self,
        symbols: List[str],
        selection_date: str,
    ) -> Tuple[Dict[str, Any], str, str]:
        """
        Validate a universe for hindsight bias using Claude.

        Returns:
            Tuple of (validation results dict, prompt used, raw response)
        """
        prompt = UNIVERSE_VALIDATION_PROMPT.format(
            selection_date=selection_date,
            symbols=", ".join(symbols),
        )

        print(f"Validating {len(symbols)} stocks for hindsight bias...")
        response = self._call_claude(prompt, max_tokens=8192)

        try:
            parsed = self._parse_json_response(response)
            return parsed, prompt, response
        except Exception as e:
            print(f"Warning: Could not parse validation response: {e}")
            return {"raw_response": response}, prompt, response

    def generate_and_validate(
        self,
        selection_date: str,
        universe_type: UniverseType,
        num_stocks: int = 60,
        **kwargs
    ) -> GeneratedUniverse:
        """
        Full pipeline: generate universe, validate it, filter results.
        """
        universe_id = f"{universe_type.value}_{selection_date.replace('-', '')}"

        # Step 1: Generate initial universe
        stocks, gen_prompt, gen_response = self.generate_universe(
            selection_date=selection_date,
            universe_type=universe_type,
            num_stocks=num_stocks,
            **kwargs
        )

        if not stocks:
            raise ValueError("Failed to generate stocks")

        symbols = [s["symbol"] for s in stocks]
        print(f"Generated {len(symbols)} candidates: {symbols[:10]}...")

        # Step 2: Apply hard IPO filter
        symbols_filtered = []
        excluded = {}
        for symbol in symbols:
            if symbol in IPO_DATES:
                ipo_date = datetime.strptime(IPO_DATES[symbol], "%Y-%m-%d")
                sel_date = datetime.strptime(selection_date, "%Y-%m-%d")
                if ipo_date >= sel_date:
                    excluded[symbol] = f"IPO'd {IPO_DATES[symbol]}, after {selection_date}"
                    continue
            symbols_filtered.append(symbol)

        print(f"After IPO filter: {len(symbols_filtered)} stocks ({len(excluded)} excluded)")

        # Step 3: Validate with Claude
        validation, val_prompt, val_response = self.validate_universe(
            symbols=symbols_filtered,
            selection_date=selection_date,
        )

        # Step 4: Process validation results
        hindsight_flags = {}
        final_symbols = []

        validated_stocks = validation.get("validated_stocks", [])
        for vs in validated_stocks:
            symbol = vs.get("symbol", "")
            overall = vs.get("overall", "UNKNOWN")
            if overall == "PASS":
                final_symbols.append(symbol)
            else:
                reason = vs.get("hindsight_check", vs.get("ipo_check", "Failed validation"))
                hindsight_flags[symbol] = reason

        # If validation didn't return structured results, use filtered list
        if not final_symbols:
            final_symbols = symbols_filtered

        print(f"Final universe: {len(final_symbols)} stocks")

        # Step 5: Build candidates list
        candidates = []
        for s in stocks:
            if s["symbol"] in final_symbols:
                candidates.append(UniverseCandidate(
                    symbol=s["symbol"],
                    name=s.get("name", ""),
                    features=StockFeatures(**s.get("features", {})) if isinstance(s.get("features"), dict) else StockFeatures(),
                    selection_rationale=s.get("selection_rationale", ""),
                    confidence_score=s.get("confidence_no_hindsight", 0.5),
                ))

        # Step 6: Create final universe object
        return GeneratedUniverse(
            id=universe_id,
            name=f"{universe_type.value.replace('_', ' ').title()} ({selection_date})",
            selection_date=selection_date,
            universe_type=universe_type,
            candidates=candidates,
            final_symbols=final_symbols,
            generation_prompt=gen_prompt,
            generation_response=gen_response,
            validation_prompt=val_prompt,
            validation_response=val_response,
            feature_criteria=kwargs.get("feature_requirements", {}),
            quantitative_filters={
                "min_market_cap_billions": kwargs.get("min_market_cap_billions", 5),
                "min_volume_millions": kwargs.get("min_volume_millions", 10),
                "min_years_listed": kwargs.get("min_years_listed", 1),
                "exclude_sectors": kwargs.get("exclude_sectors", []),
            },
            excluded_symbols=excluded,
            hindsight_flags=hindsight_flags,
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def generate_momentum_universe(
    selection_date: str = "2020-01-01",
    api_key: str = None,
) -> GeneratedUniverse:
    """
    Generate a high-beta momentum universe with full validation.
    """
    generator = ClaudeUniverseGenerator(api_key=api_key)

    return generator.generate_and_validate(
        selection_date=selection_date,
        universe_type=UniverseType.HIGH_BETA_MOMENTUM,
        num_stocks=60,
        min_market_cap_billions=5,
        min_volume_millions=10,
        min_years_listed=1,
        exclude_sectors=["Utilities", "Real Estate", "Consumer Staples"],
    )


def analyze_momentum_features(api_key: str = None) -> Dict[str, Any]:
    """
    Use Claude to extract common features of momentum stocks.
    """
    generator = ClaudeUniverseGenerator(api_key=api_key)
    return generator.extract_momentum_features()


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate stock universes using Claude")
    parser.add_argument("--date", default="2020-01-01", help="Selection date (YYYY-MM-DD)")
    parser.add_argument("--type", default="high_beta_momentum",
                        choices=[t.value for t in UniverseType],
                        help="Universe type")
    parser.add_argument("--num-stocks", type=int, default=60, help="Number of stocks")
    parser.add_argument("--output-dir", default="strategy-factory/universe/generated",
                        help="Output directory")
    parser.add_argument("--extract-features", action="store_true",
                        help="Extract common momentum features")
    parser.add_argument("--api-key", help="Anthropic API key (or set ANTHROPIC_API_KEY)")

    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: Set ANTHROPIC_API_KEY environment variable or pass --api-key")
        return 1

    if args.extract_features:
        print("=" * 60)
        print("EXTRACTING MOMENTUM STOCK FEATURES")
        print("=" * 60)
        features = analyze_momentum_features(api_key=api_key)
        print(json.dumps(features, indent=2))
        return 0

    print("=" * 60)
    print(f"GENERATING {args.type.upper()} UNIVERSE")
    print(f"Selection Date: {args.date}")
    print("=" * 60)

    generator = ClaudeUniverseGenerator(api_key=api_key)

    universe = generator.generate_and_validate(
        selection_date=args.date,
        universe_type=UniverseType(args.type),
        num_stocks=args.num_stocks,
    )

    # Save results
    filepath = universe.save(args.output_dir)
    print(f"\nSaved to: {filepath}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Universe: {universe.name}")
    print(f"Final stocks ({len(universe.final_symbols)}): {universe.final_symbols}")
    print(f"\nExcluded ({len(universe.excluded_symbols)}):")
    for sym, reason in universe.excluded_symbols.items():
        print(f"  - {sym}: {reason}")
    print(f"\nHindsight flags ({len(universe.hindsight_flags)}):")
    for sym, flag in universe.hindsight_flags.items():
        print(f"  - {sym}: {flag}")

    return 0


if __name__ == "__main__":
    exit(main())
