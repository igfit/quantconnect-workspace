"""
Momentum Stock Feature Analysis

Identifies NON-HINDSIGHT features that characterize good momentum candidates.
These features are observable BEFORE knowing future returns.

Key Insight: We want to find stocks that LOOK LIKE good momentum candidates,
not stocks that TURNED OUT to be good momentum candidates.

The difference:
- HINDSIGHT: "NVDA returned 500% so it was a good pick" (useless for future)
- NON-HINDSIGHT: "NVDA had high beta, high volume, market leadership" (useful for future)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import json


class FeatureImportance(str, Enum):
    CRITICAL = "critical"      # Must have
    HIGH = "high"              # Strongly predictive
    MEDIUM = "medium"          # Helpful
    LOW = "low"                # Nice to have


@dataclass
class MomentumFeature:
    """A feature that predicts momentum suitability"""
    name: str
    description: str
    importance: FeatureImportance
    measurement: str           # How to measure it
    threshold: Optional[str]   # Threshold for selection
    rationale: str            # WHY this feature matters


# =============================================================================
# EMPIRICALLY-DERIVED MOMENTUM FEATURES
# =============================================================================

# These features are derived from academic research and practitioner experience,
# NOT from backtesting our specific strategy.

MOMENTUM_FEATURES = {
    # ---------------------------------------------------------------------
    # VOLATILITY & BETA (Critical)
    # ---------------------------------------------------------------------
    "high_beta": MomentumFeature(
        name="High Beta",
        description="Stock moves more than the market",
        importance=FeatureImportance.CRITICAL,
        measurement="60-day beta vs SPY",
        threshold="> 1.2",
        rationale="""
        High-beta stocks amplify market moves. In a momentum strategy, we want
        stocks that move significantly when trends develop. A stock with beta 1.5
        will gain 15% when the market gains 10% - this amplification is key to
        momentum returns.

        Academic support: Jegadeesh & Titman (1993) found momentum is stronger
        in high-beta stocks.
        """
    ),

    "high_volatility": MomentumFeature(
        name="High Historical Volatility",
        description="Stock has above-average price swings",
        importance=FeatureImportance.HIGH,
        measurement="60-day annualized volatility",
        threshold="> 30% annualized",
        rationale="""
        Volatile stocks have more momentum opportunities. A stock that moves 2%
        daily has more momentum potential than one moving 0.5% daily. Volatility
        creates the price trends that momentum strategies capture.
        """
    ),

    # ---------------------------------------------------------------------
    # LIQUIDITY (Critical)
    # ---------------------------------------------------------------------
    "high_liquidity": MomentumFeature(
        name="High Liquidity",
        description="High daily trading volume",
        importance=FeatureImportance.CRITICAL,
        measurement="20-day average dollar volume",
        threshold="> $10M daily",
        rationale="""
        Liquid stocks can be traded without moving the market. Illiquid stocks
        have high transaction costs that eat into momentum returns. We need
        stocks where we can enter/exit positions cleanly.
        """
    ),

    "tight_spreads": MomentumFeature(
        name="Tight Bid-Ask Spreads",
        description="Low transaction costs",
        importance=FeatureImportance.MEDIUM,
        measurement="Average bid-ask spread as % of price",
        threshold="< 0.1%",
        rationale="""
        Wide spreads increase trading costs. For monthly rebalancing with 15
        positions, even small spread differences compound significantly.
        """
    ),

    # ---------------------------------------------------------------------
    # GROWTH CHARACTERISTICS (High)
    # ---------------------------------------------------------------------
    "revenue_growth": MomentumFeature(
        name="Revenue Growth",
        description="Company is growing revenues",
        importance=FeatureImportance.HIGH,
        measurement="YoY revenue growth rate",
        threshold="> 10% YoY",
        rationale="""
        Growing companies tend to have price momentum. Revenue growth is a
        fundamental driver of stock appreciation. Momentum strategies implicitly
        select for growth by picking recent winners.
        """
    ),

    "expanding_tam": MomentumFeature(
        name="Expanding Total Addressable Market",
        description="Industry is growing",
        importance=FeatureImportance.HIGH,
        measurement="Industry growth rate",
        threshold="Industry growth > GDP growth",
        rationale="""
        Companies in growing industries have tailwinds. A rising tide lifts all
        boats - momentum is easier when the industry is expanding.
        """
    ),

    # ---------------------------------------------------------------------
    # MARKET POSITION (High)
    # ---------------------------------------------------------------------
    "market_leader": MomentumFeature(
        name="Market Leadership",
        description="Top 3 position in industry",
        importance=FeatureImportance.HIGH,
        measurement="Market share rank in primary business",
        threshold="Top 3 in industry",
        rationale="""
        Market leaders have competitive moats and pricing power. They tend to
        outperform during industry upswings and are more resilient in downturns.
        Leadership position is observable before performance.
        """
    ),

    "category_creator": MomentumFeature(
        name="Category Creator/Disruptor",
        description="Creating or disrupting a market",
        importance=FeatureImportance.MEDIUM,
        measurement="Qualitative assessment",
        threshold="Clear disruption narrative",
        rationale="""
        Disruptors can have explosive growth. Companies creating new categories
        (Tesla in EVs, NVIDIA in AI accelerators) often have strong momentum.
        The disruption thesis is observable before the stock performance.
        """
    ),

    # ---------------------------------------------------------------------
    # INSTITUTIONAL INTEREST (Medium)
    # ---------------------------------------------------------------------
    "analyst_coverage": MomentumFeature(
        name="High Analyst Coverage",
        description="Many analysts covering the stock",
        importance=FeatureImportance.MEDIUM,
        measurement="Number of analysts with ratings",
        threshold="> 15 analysts",
        rationale="""
        Well-covered stocks have more information flow. Analyst upgrades/downgrades
        can catalyze momentum. Stocks with no coverage are harder to trade.
        """
    ),

    "institutional_ownership": MomentumFeature(
        name="Institutional Ownership",
        description="Funds own significant stake",
        importance=FeatureImportance.MEDIUM,
        measurement="% owned by institutions",
        threshold="> 60% institutional",
        rationale="""
        Institutional buying creates momentum. When funds accumulate positions,
        they create sustained buying pressure. High institutional ownership
        also indicates the stock is "investable" for large players.
        """
    ),

    # ---------------------------------------------------------------------
    # SECTOR/CYCLICALITY (High)
    # ---------------------------------------------------------------------
    "cyclical_sector": MomentumFeature(
        name="Cyclical Sector",
        description="Sector that exhibits momentum",
        importance=FeatureImportance.HIGH,
        measurement="Sector classification",
        threshold="Technology, Consumer Discretionary, Financials, Energy, Industrials",
        rationale="""
        Cyclical sectors have more momentum than defensive sectors. When the
        economy/market is strong, cyclical sectors outperform. Momentum strategies
        benefit from this cyclicality.

        Avoid: Utilities, Consumer Staples, Real Estate (low beta, mean-reverting)
        """
    ),

    # ---------------------------------------------------------------------
    # SIZE (Medium)
    # ---------------------------------------------------------------------
    "mid_to_large_cap": MomentumFeature(
        name="Mid-to-Large Cap",
        description="Sweet spot for momentum",
        importance=FeatureImportance.MEDIUM,
        measurement="Market capitalization",
        threshold="$5B - $500B",
        rationale="""
        Mid-to-large caps offer the best momentum tradeoff:
        - Large enough to be liquid and well-covered
        - Small enough to still have significant upside
        - Mega-caps (>$500B) are too efficient for momentum
        - Small-caps (<$5B) are too illiquid
        """
    ),

    # ---------------------------------------------------------------------
    # PRICE CHARACTERISTICS (Medium)
    # ---------------------------------------------------------------------
    "price_above_sma": MomentumFeature(
        name="Price Above 200-day SMA",
        description="Stock in uptrend",
        importance=FeatureImportance.MEDIUM,
        measurement="Price relative to 200-day SMA",
        threshold="Price > 200 SMA",
        rationale="""
        Stocks above their 200-day SMA are in uptrends. This is the simplest
        momentum signal - we want stocks that are already trending up.
        """
    ),

    "not_overbought": MomentumFeature(
        name="Not Extremely Overbought",
        description="Room for continued momentum",
        importance=FeatureImportance.LOW,
        measurement="RSI or other overbought indicator",
        threshold="RSI < 80",
        rationale="""
        Extremely overbought stocks may be due for reversal. We want momentum
        candidates with room to run, not ones that have already exhausted
        their near-term upside.
        """
    ),
}


# =============================================================================
# FEATURE SCORING
# =============================================================================

def score_stock_features(features: Dict[str, bool]) -> float:
    """
    Score a stock based on its momentum features.

    Args:
        features: Dict mapping feature names to True/False

    Returns:
        Score from 0 to 1 (1 = perfect momentum candidate)
    """
    weights = {
        FeatureImportance.CRITICAL: 3.0,
        FeatureImportance.HIGH: 2.0,
        FeatureImportance.MEDIUM: 1.0,
        FeatureImportance.LOW: 0.5,
    }

    total_weight = 0
    weighted_score = 0

    for feature_name, has_feature in features.items():
        if feature_name in MOMENTUM_FEATURES:
            feature = MOMENTUM_FEATURES[feature_name]
            weight = weights[feature.importance]
            total_weight += weight
            if has_feature:
                weighted_score += weight

    return weighted_score / total_weight if total_weight > 0 else 0


def get_selection_rules() -> List[str]:
    """
    Get human-readable selection rules based on features.
    """
    rules = []

    critical_features = [f for f in MOMENTUM_FEATURES.values()
                         if f.importance == FeatureImportance.CRITICAL]
    high_features = [f for f in MOMENTUM_FEATURES.values()
                     if f.importance == FeatureImportance.HIGH]

    rules.append("=== MUST HAVE (Critical) ===")
    for f in critical_features:
        rules.append(f"- {f.name}: {f.threshold}")

    rules.append("\n=== SHOULD HAVE (High Importance) ===")
    for f in high_features:
        rules.append(f"- {f.name}: {f.threshold}")

    return rules


def get_anti_patterns() -> List[str]:
    """
    Get patterns to AVOID when selecting momentum stocks.
    """
    return [
        "Defensive sectors (Utilities, Consumer Staples, Real Estate)",
        "Low beta stocks (< 0.8)",
        "Illiquid stocks (< $5M daily volume)",
        "Recent IPOs (< 1 year public)",
        "Penny stocks (< $5 price)",
        "Declining revenues",
        "No analyst coverage",
        "Extreme overbought conditions (RSI > 90)",
        "Stocks below 200-day SMA (unless mean-reversion strategy)",
    ]


# =============================================================================
# SECTOR ANALYSIS
# =============================================================================

SECTOR_MOMENTUM_SCORES = {
    # Sectors ranked by historical momentum characteristics
    "Technology": {
        "momentum_score": 0.9,
        "typical_beta": 1.3,
        "rationale": "High growth, high volatility, institutional favorites"
    },
    "Consumer Discretionary": {
        "momentum_score": 0.85,
        "typical_beta": 1.2,
        "rationale": "Cyclical, benefits from economic expansion"
    },
    "Financials": {
        "momentum_score": 0.75,
        "typical_beta": 1.15,
        "rationale": "Cyclical, rate-sensitive, can have strong trends"
    },
    "Energy": {
        "momentum_score": 0.8,
        "typical_beta": 1.4,
        "rationale": "Commodity-driven, very volatile, strong trends"
    },
    "Industrials": {
        "momentum_score": 0.7,
        "typical_beta": 1.1,
        "rationale": "Cyclical, benefits from capex cycles"
    },
    "Communication Services": {
        "momentum_score": 0.65,
        "typical_beta": 1.0,
        "rationale": "Mixed - growth names have momentum, telcos don't"
    },
    "Healthcare": {
        "momentum_score": 0.5,
        "typical_beta": 0.9,
        "rationale": "Defensive, but biotech/medtech can have momentum"
    },
    "Consumer Staples": {
        "momentum_score": 0.2,
        "typical_beta": 0.7,
        "rationale": "Defensive, low volatility, avoid"
    },
    "Utilities": {
        "momentum_score": 0.1,
        "typical_beta": 0.5,
        "rationale": "Defensive, low beta, mean-reverting, avoid"
    },
    "Real Estate": {
        "momentum_score": 0.3,
        "typical_beta": 0.8,
        "rationale": "Rate-sensitive, moderate momentum"
    },
}


def get_preferred_sectors() -> List[str]:
    """Get sectors ranked by momentum suitability"""
    sorted_sectors = sorted(
        SECTOR_MOMENTUM_SCORES.items(),
        key=lambda x: x[1]["momentum_score"],
        reverse=True
    )
    return [s[0] for s in sorted_sectors if s[1]["momentum_score"] >= 0.6]


def get_avoid_sectors() -> List[str]:
    """Get sectors to avoid for momentum"""
    return [s for s, data in SECTOR_MOMENTUM_SCORES.items()
            if data["momentum_score"] < 0.4]


# =============================================================================
# FEATURE CRITERIA FOR CLAUDE
# =============================================================================

def get_feature_criteria_prompt() -> str:
    """
    Generate a prompt section describing the features Claude should look for.
    """
    lines = ["Select stocks that have these characteristics:\n"]

    for name, feature in MOMENTUM_FEATURES.items():
        if feature.importance in [FeatureImportance.CRITICAL, FeatureImportance.HIGH]:
            lines.append(f"**{feature.name}** ({feature.importance.value})")
            lines.append(f"  - Measurement: {feature.measurement}")
            lines.append(f"  - Threshold: {feature.threshold}")
            lines.append(f"  - Why: {feature.rationale.strip()[:200]}...")
            lines.append("")

    lines.append("\nPreferred Sectors: " + ", ".join(get_preferred_sectors()))
    lines.append("Avoid Sectors: " + ", ".join(get_avoid_sectors()))

    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("MOMENTUM STOCK FEATURES")
    print("=" * 60)

    print("\n=== Selection Rules ===")
    for rule in get_selection_rules():
        print(rule)

    print("\n=== Anti-Patterns (Avoid) ===")
    for pattern in get_anti_patterns():
        print(f"  - {pattern}")

    print("\n=== Sector Rankings ===")
    for sector in get_preferred_sectors():
        data = SECTOR_MOMENTUM_SCORES[sector]
        print(f"  {sector}: {data['momentum_score']:.0%} (beta ~{data['typical_beta']})")

    print("\n=== Feature Criteria for Claude ===")
    print(get_feature_criteria_prompt()[:1000] + "...")

    # Test scoring
    print("\n=== Example Scoring ===")
    nvda_features = {
        "high_beta": True,
        "high_volatility": True,
        "high_liquidity": True,
        "revenue_growth": True,
        "market_leader": True,
        "cyclical_sector": True,
        "analyst_coverage": True,
    }
    print(f"NVDA-like stock score: {score_stock_features(nvda_features):.2%}")

    low_beta_features = {
        "high_beta": False,
        "high_volatility": False,
        "high_liquidity": True,
        "revenue_growth": False,
        "market_leader": True,
        "cyclical_sector": False,
    }
    print(f"Low-beta utility stock score: {score_stock_features(low_beta_features):.2%}")
