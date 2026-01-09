"""
Strategy Specification Model

Defines the data structures for scalping strategy specifications.
Supports multiple resolutions (minute, hour, daily) unlike daily-only strategy-factory.
"""

import uuid
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Resolution, HIGH_BETA_UNIVERSE


class StrategyType(Enum):
    """Type of trading strategy"""
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    BREAKOUT = "breakout"
    PAIRS = "pairs"
    GAP_FADE = "gap_fade"
    VWAP_REVERSION = "vwap_reversion"


class Operator(Enum):
    """Comparison operators for conditions"""
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="
    EQUAL = "=="
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"


class Logic(Enum):
    """Logic for combining conditions"""
    AND = "and"
    OR = "or"


@dataclass
class IndicatorSpec:
    """Specification for a technical indicator"""
    name: str                          # Unique identifier (e.g., "rsi_2")
    type: str                          # Indicator type (RSI, SMA, BB, etc.)
    params: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    def get_period(self) -> int:
        """Get the lookback period for this indicator"""
        if "period" in self.params:
            return self.params["period"]
        elif "slow_period" in self.params:
            return self.params["slow_period"]
        elif "lookback" in self.params:
            return self.params["lookback"]
        return 14  # Default

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "IndicatorSpec":
        return cls(**data)


@dataclass
class Condition:
    """A single condition (e.g., RSI < 10)"""
    left: str                          # Left operand (indicator name or "price")
    operator: Operator                 # Comparison operator
    right: Any                         # Right operand (value or indicator name)
    description: str = ""

    def to_dict(self) -> Dict:
        return {
            "left": self.left,
            "operator": self.operator.value,
            "right": self.right,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Condition":
        return cls(
            left=data["left"],
            operator=Operator(data["operator"]),
            right=data["right"],
            description=data.get("description", ""),
        )


@dataclass
class ConditionGroup:
    """Group of conditions combined with AND/OR"""
    conditions: List[Condition] = field(default_factory=list)
    logic: Logic = Logic.AND

    def to_dict(self) -> Dict:
        return {
            "conditions": [c.to_dict() for c in self.conditions],
            "logic": self.logic.value,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ConditionGroup":
        return cls(
            conditions=[Condition.from_dict(c) for c in data["conditions"]],
            logic=Logic(data["logic"]),
        )


@dataclass
class RiskManagement:
    """Risk management parameters"""
    position_size_dollars: float = 10000      # Fixed dollar amount per position
    position_size_pct: Optional[float] = None # OR percentage of capital
    risk_per_trade_pct: float = 0.01          # 1% risk per trade for ATR-based sizing
    stop_loss_pct: Optional[float] = None     # Hard stop loss percentage
    take_profit_pct: Optional[float] = None   # Take profit percentage
    trailing_stop_atr: Optional[float] = None # Trailing stop in ATR multiples
    max_holding_days: Optional[int] = None    # Time-based exit
    max_positions: int = 5                    # Max concurrent positions

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "RiskManagement":
        return cls(**data)


@dataclass
class StrategySpec:
    """
    Complete specification for a scalping strategy.

    This is the core data structure that gets compiled into QuantConnect code.
    Unlike the daily-only strategy-factory, this supports minute/hour/daily resolution.
    """
    # Identity
    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    version: str = "1.0"

    # Strategy metadata
    strategy_type: StrategyType = StrategyType.MEAN_REVERSION
    description: str = ""
    rationale: str = ""                       # WHY this strategy works

    # Resolution - KEY DIFFERENCE from strategy-factory
    resolution: Resolution = Resolution.DAILY

    # Universe
    symbols: List[str] = field(default_factory=lambda: HIGH_BETA_UNIVERSE.copy())

    # Indicators
    indicators: List[IndicatorSpec] = field(default_factory=list)

    # Entry/Exit conditions
    entry_conditions: ConditionGroup = field(default_factory=ConditionGroup)
    exit_conditions: ConditionGroup = field(default_factory=ConditionGroup)

    # Risk management
    risk_management: RiskManagement = field(default_factory=RiskManagement)

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    tags: List[str] = field(default_factory=list)

    def validate(self) -> List[str]:
        """Validate the strategy specification"""
        errors = []

        if not self.name:
            errors.append("Strategy name is required")

        if not self.symbols:
            errors.append("At least one symbol is required")

        if not self.indicators:
            errors.append("At least one indicator is required")

        if not self.entry_conditions.conditions:
            errors.append("At least one entry condition is required")

        if not self.exit_conditions.conditions:
            errors.append("At least one exit condition is required")

        # Validate indicator references in conditions
        indicator_names = {ind.name for ind in self.indicators}
        indicator_names.add("price")  # price is always available
        indicator_names.add("sma_200")  # trend filter often implicit

        for cond in self.entry_conditions.conditions + self.exit_conditions.conditions:
            if cond.left not in indicator_names and not cond.left.startswith("price"):
                errors.append(f"Unknown indicator in condition: {cond.left}")
            if isinstance(cond.right, str) and cond.right not in indicator_names:
                if not cond.right.replace(".", "").replace("-", "").isdigit():
                    errors.append(f"Unknown indicator in condition: {cond.right}")

        return errors

    def get_max_indicator_period(self) -> int:
        """Get the maximum lookback period across all indicators"""
        if not self.indicators:
            return 14
        return max(ind.get_period() for ind in self.indicators)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "name": self.name,
            "id": self.id,
            "version": self.version,
            "strategy_type": self.strategy_type.value,
            "description": self.description,
            "rationale": self.rationale,
            "resolution": self.resolution.value,
            "symbols": self.symbols,
            "indicators": [ind.to_dict() for ind in self.indicators],
            "entry_conditions": self.entry_conditions.to_dict(),
            "exit_conditions": self.exit_conditions.to_dict(),
            "risk_management": self.risk_management.to_dict(),
            "created_at": self.created_at,
            "tags": self.tags,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Dict) -> "StrategySpec":
        """Create from dictionary"""
        return cls(
            name=data["name"],
            id=data.get("id", str(uuid.uuid4())[:8]),
            version=data.get("version", "1.0"),
            strategy_type=StrategyType(data.get("strategy_type", "mean_reversion")),
            description=data.get("description", ""),
            rationale=data.get("rationale", ""),
            resolution=Resolution(data.get("resolution", "Resolution.DAILY")),
            symbols=data.get("symbols", HIGH_BETA_UNIVERSE.copy()),
            indicators=[IndicatorSpec.from_dict(i) for i in data.get("indicators", [])],
            entry_conditions=ConditionGroup.from_dict(data["entry_conditions"]) if "entry_conditions" in data else ConditionGroup(),
            exit_conditions=ConditionGroup.from_dict(data["exit_conditions"]) if "exit_conditions" in data else ConditionGroup(),
            risk_management=RiskManagement.from_dict(data["risk_management"]) if "risk_management" in data else RiskManagement(),
            created_at=data.get("created_at", datetime.now().isoformat()),
            tags=data.get("tags", []),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "StrategySpec":
        """Create from JSON string"""
        return cls.from_dict(json.loads(json_str))


# =============================================================================
# PRE-DEFINED STRATEGY SPECS
# =============================================================================

def create_rsi2_pullback_spec() -> StrategySpec:
    """
    RSI(2) Pullback Strategy

    Thesis: Extreme short-term oversold conditions in trending stocks create
    bounce opportunities. RSI(2) < 10 indicates capitulation selling that
    typically reverses within 1-5 days.

    Academic basis: Larry Connors - "Short-Term Trading Strategies That Work"
    """
    return StrategySpec(
        name="RSI(2) Pullback",
        strategy_type=StrategyType.MEAN_REVERSION,
        description="Buy extreme oversold (RSI(2) < 10) in uptrending stocks",
        rationale=(
            "Extreme short-term oversold conditions in trending stocks create "
            "bounce opportunities. RSI(2) < 10 indicates capitulation selling "
            "that typically reverses within 1-5 days. The 200 SMA filter ensures "
            "we only buy pullbacks in uptrends, not falling knives in downtrends."
        ),
        resolution=Resolution.DAILY,
        symbols=HIGH_BETA_UNIVERSE.copy(),
        indicators=[
            IndicatorSpec(
                name="rsi_2",
                type="RSI",
                params={"period": 2},
                description="RSI with 2-period lookback for extreme oversold"
            ),
            IndicatorSpec(
                name="sma_200",
                type="SMA",
                params={"period": 200},
                description="Long-term trend filter"
            ),
        ],
        entry_conditions=ConditionGroup(
            conditions=[
                Condition(
                    left="price",
                    operator=Operator.GREATER_THAN,
                    right="sma_200",
                    description="Price above 200 SMA (uptrend)"
                ),
                Condition(
                    left="rsi_2",
                    operator=Operator.LESS_THAN,
                    right=10,
                    description="RSI(2) < 10 (extreme oversold)"
                ),
            ],
            logic=Logic.AND
        ),
        exit_conditions=ConditionGroup(
            conditions=[
                Condition(
                    left="rsi_2",
                    operator=Operator.GREATER_THAN,
                    right=70,
                    description="RSI(2) > 70 (mean reverted)"
                ),
            ],
            logic=Logic.OR
        ),
        risk_management=RiskManagement(
            position_size_dollars=20000,
            risk_per_trade_pct=0.01,
            stop_loss_pct=0.03,        # 3% hard stop
            max_holding_days=5,         # Time stop after 5 days
            max_positions=5,
        ),
        tags=["mean_reversion", "rsi", "pullback", "connors"],
    )


def create_connors_rsi_spec() -> StrategySpec:
    """
    Connors RSI Strategy

    Thesis: Multi-factor approach combining short-term RSI, streak behavior,
    and percentile rank provides more robust signals than single indicators.

    Academic basis: Connors & Alvarez pullback framework
    """
    return StrategySpec(
        name="Connors RSI",
        strategy_type=StrategyType.MEAN_REVERSION,
        description="Multi-factor mean reversion using Connors RSI composite",
        rationale=(
            "Connors RSI combines three factors: RSI(3) for short-term momentum, "
            "StreakRSI for consecutive up/down day behavior, and PercentRank for "
            "position within recent range. This multi-factor approach is more "
            "robust than single indicators and has been extensively backtested "
            "by Connors Research."
        ),
        resolution=Resolution.DAILY,
        symbols=HIGH_BETA_UNIVERSE.copy(),
        indicators=[
            IndicatorSpec(
                name="connors_rsi",
                type="CONNORS_RSI",
                params={
                    "rsi_period": 3,
                    "streak_period": 2,
                    "rank_period": 100
                },
                description="Connors RSI composite indicator"
            ),
            IndicatorSpec(
                name="sma_200",
                type="SMA",
                params={"period": 200},
                description="Long-term trend filter"
            ),
        ],
        entry_conditions=ConditionGroup(
            conditions=[
                Condition(
                    left="price",
                    operator=Operator.GREATER_THAN,
                    right="sma_200",
                    description="Price above 200 SMA (uptrend)"
                ),
                Condition(
                    left="connors_rsi",
                    operator=Operator.LESS_THAN,
                    right=15,
                    description="Connors RSI < 15 (composite oversold)"
                ),
            ],
            logic=Logic.AND
        ),
        exit_conditions=ConditionGroup(
            conditions=[
                Condition(
                    left="connors_rsi",
                    operator=Operator.GREATER_THAN,
                    right=70,
                    description="Connors RSI > 70 (mean reverted)"
                ),
            ],
            logic=Logic.OR
        ),
        risk_management=RiskManagement(
            position_size_dollars=20000,
            risk_per_trade_pct=0.01,
            stop_loss_pct=0.04,        # 4% hard stop (slightly wider)
            max_holding_days=5,
            max_positions=5,
        ),
        tags=["mean_reversion", "connors_rsi", "multi_factor"],
    )


def create_bollinger_mean_reversion_spec() -> StrategySpec:
    """
    Bollinger Band Mean Reversion Strategy

    Thesis: When price touches or exceeds the lower Bollinger Band with RSI
    confirmation, the probability of a bounce to the middle band is high.
    """
    return StrategySpec(
        name="Bollinger Band Mean Reversion",
        strategy_type=StrategyType.MEAN_REVERSION,
        description="Buy at lower BB with RSI confirmation, exit at middle band",
        rationale=(
            "Bollinger Bands capture 95% of price action within 2 standard deviations. "
            "When price touches the lower band AND RSI confirms oversold, we have "
            "a high-probability mean reversion setup. Exit at middle band captures "
            "the reversion without waiting for overbought conditions."
        ),
        resolution=Resolution.DAILY,
        symbols=HIGH_BETA_UNIVERSE.copy(),
        indicators=[
            IndicatorSpec(
                name="bb",
                type="BB",
                params={"period": 20, "k": 2},
                description="Bollinger Bands (20, 2)"
            ),
            IndicatorSpec(
                name="rsi_14",
                type="RSI",
                params={"period": 14},
                description="Standard RSI for confirmation"
            ),
            IndicatorSpec(
                name="sma_200",
                type="SMA",
                params={"period": 200},
                description="Long-term trend filter"
            ),
        ],
        entry_conditions=ConditionGroup(
            conditions=[
                Condition(
                    left="price",
                    operator=Operator.GREATER_THAN,
                    right="sma_200",
                    description="Price above 200 SMA (uptrend)"
                ),
                Condition(
                    left="price",
                    operator=Operator.LESS_EQUAL,
                    right="bb_lower",
                    description="Price at or below lower BB"
                ),
                Condition(
                    left="rsi_14",
                    operator=Operator.LESS_THAN,
                    right=35,
                    description="RSI < 35 (confirming oversold)"
                ),
            ],
            logic=Logic.AND
        ),
        exit_conditions=ConditionGroup(
            conditions=[
                Condition(
                    left="price",
                    operator=Operator.GREATER_EQUAL,
                    right="bb_middle",
                    description="Price at or above middle BB"
                ),
            ],
            logic=Logic.OR
        ),
        risk_management=RiskManagement(
            position_size_dollars=20000,
            risk_per_trade_pct=0.01,
            stop_loss_pct=0.03,
            max_holding_days=7,
            max_positions=5,
        ),
        tags=["mean_reversion", "bollinger", "volatility"],
    )


def create_pairs_trading_spec(
    long_symbol: str = "AMD",
    short_symbol: str = "NVDA"
) -> StrategySpec:
    """
    Pairs Trading Strategy

    Thesis: Highly correlated stocks (NVDA/AMD) tend to move together. When the
    spread between them deviates significantly, mean reversion creates a
    market-neutral opportunity.
    """
    return StrategySpec(
        name=f"Pairs: {long_symbol}/{short_symbol}",
        strategy_type=StrategyType.PAIRS,
        description=f"Mean reversion on {long_symbol}/{short_symbol} spread",
        rationale=(
            f"{long_symbol} and {short_symbol} are highly correlated stocks in the "
            "semiconductor sector. When the spread between them deviates beyond "
            "2 standard deviations from the 60-day mean, we expect mean reversion. "
            "This is market-neutral - we're long one and short the other."
        ),
        resolution=Resolution.DAILY,
        symbols=[long_symbol, short_symbol],
        indicators=[
            IndicatorSpec(
                name="spread_zscore",
                type="SPREAD_ZSCORE",
                params={
                    "lookback": 60,
                    "long_symbol": long_symbol,
                    "short_symbol": short_symbol,
                },
                description="Z-score of price spread"
            ),
        ],
        entry_conditions=ConditionGroup(
            conditions=[
                # Entry when Z-score > 2 (long spread) or < -2 (short spread)
                Condition(
                    left="spread_zscore",
                    operator=Operator.GREATER_THAN,
                    right=2.0,
                    description="Z-score > 2 (spread too wide, expect reversion)"
                ),
            ],
            logic=Logic.OR
        ),
        exit_conditions=ConditionGroup(
            conditions=[
                Condition(
                    left="spread_zscore",
                    operator=Operator.LESS_THAN,
                    right=0.5,
                    description="Z-score < 0.5 (spread reverted)"
                ),
            ],
            logic=Logic.OR
        ),
        risk_management=RiskManagement(
            position_size_dollars=25000,  # Per leg
            risk_per_trade_pct=0.02,
            stop_loss_pct=None,           # Use Z-score stop instead
            max_holding_days=20,
            max_positions=2,              # Just the pair
        ),
        tags=["pairs", "market_neutral", "spread", "semiconductor"],
    )


def create_gap_fade_spec() -> StrategySpec:
    """
    Gap Fade Strategy

    Thesis: Large overnight gaps (>2%) in liquid stocks tend to partially fill
    within the first few hours of trading. This is especially true for gaps
    without fundamental news catalysts.
    """
    return StrategySpec(
        name="Gap Fade",
        strategy_type=StrategyType.GAP_FADE,
        description="Fade overnight gaps > 2% expecting partial fill",
        rationale=(
            "Large overnight gaps often overshoot fair value due to after-hours "
            "illiquidity. Without fundamental news, these gaps tend to partially "
            "fill as regular market hours bring more liquidity. We fade the gap "
            "direction and exit at partial fill or end of day."
        ),
        resolution=Resolution.MINUTE,  # Intraday strategy
        symbols=HIGH_BETA_UNIVERSE.copy(),
        indicators=[
            IndicatorSpec(
                name="gap_pct",
                type="GAP",
                params={"threshold": 0.02},
                description="Overnight gap percentage"
            ),
            IndicatorSpec(
                name="vwap",
                type="VWAP",
                params={},
                description="Volume-weighted average price"
            ),
        ],
        entry_conditions=ConditionGroup(
            conditions=[
                Condition(
                    left="gap_pct",
                    operator=Operator.GREATER_THAN,
                    right=0.02,
                    description="Gap > 2%"
                ),
            ],
            logic=Logic.AND
        ),
        exit_conditions=ConditionGroup(
            conditions=[
                Condition(
                    left="price",
                    operator=Operator.CROSSES_BELOW,
                    right="vwap",
                    description="Price crosses below VWAP (gap filling)"
                ),
            ],
            logic=Logic.OR
        ),
        risk_management=RiskManagement(
            position_size_dollars=15000,
            risk_per_trade_pct=0.005,      # Tighter risk for intraday
            stop_loss_pct=0.015,           # 1.5% stop
            max_holding_days=1,            # Intraday only
            max_positions=3,
        ),
        tags=["gap_fade", "intraday", "mean_reversion"],
    )


def create_vwap_reversion_spec() -> StrategySpec:
    """
    VWAP Reversion Strategy

    Thesis: When price deviates significantly below VWAP with RSI confirmation,
    there's a high probability of reversion to VWAP. VWAP acts as an
    institutional "fair value" anchor.
    """
    return StrategySpec(
        name="VWAP Reversion",
        strategy_type=StrategyType.VWAP_REVERSION,
        description="Buy below VWAP with RSI confirmation, exit at VWAP",
        rationale=(
            "VWAP represents the average price weighted by volume - essentially "
            "where institutional money traded. When price falls significantly "
            "below VWAP (1.5%+) with oversold RSI, institutions often step in "
            "to buy, pushing price back to VWAP."
        ),
        resolution=Resolution.MINUTE,
        symbols=HIGH_BETA_UNIVERSE.copy(),
        indicators=[
            IndicatorSpec(
                name="vwap",
                type="VWAP",
                params={},
                description="Volume-weighted average price"
            ),
            IndicatorSpec(
                name="vwap_dev",
                type="VWAP_DEVIATION",
                params={"threshold": 0.015},
                description="Deviation from VWAP"
            ),
            IndicatorSpec(
                name="rsi_7",
                type="RSI",
                params={"period": 7},
                description="Short-term RSI"
            ),
        ],
        entry_conditions=ConditionGroup(
            conditions=[
                Condition(
                    left="vwap_dev",
                    operator=Operator.LESS_THAN,
                    right=-0.015,
                    description="Price > 1.5% below VWAP"
                ),
                Condition(
                    left="rsi_7",
                    operator=Operator.LESS_THAN,
                    right=30,
                    description="RSI(7) < 30 (oversold)"
                ),
            ],
            logic=Logic.AND
        ),
        exit_conditions=ConditionGroup(
            conditions=[
                Condition(
                    left="price",
                    operator=Operator.GREATER_EQUAL,
                    right="vwap",
                    description="Price at or above VWAP"
                ),
            ],
            logic=Logic.OR
        ),
        risk_management=RiskManagement(
            position_size_dollars=15000,
            risk_per_trade_pct=0.005,
            stop_loss_pct=0.02,            # 2% stop
            max_holding_days=1,
            max_positions=3,
        ),
        tags=["vwap", "intraday", "mean_reversion", "institutional"],
    )


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test all strategy specs
    specs = [
        create_rsi2_pullback_spec(),
        create_connors_rsi_spec(),
        create_bollinger_mean_reversion_spec(),
        create_pairs_trading_spec(),
        create_gap_fade_spec(),
        create_vwap_reversion_spec(),
    ]

    for spec in specs:
        print(f"\n{'='*60}")
        print(f"Strategy: {spec.name}")
        print(f"Type: {spec.strategy_type.value}")
        print(f"Resolution: {spec.resolution.value}")
        print(f"Symbols: {spec.symbols}")
        print(f"Indicators: {[i.name for i in spec.indicators]}")
        print(f"Entry conditions: {len(spec.entry_conditions.conditions)}")
        print(f"Exit conditions: {len(spec.exit_conditions.conditions)}")

        errors = spec.validate()
        if errors:
            print(f"Validation errors: {errors}")
        else:
            print("Validation: PASSED")

        # Test JSON serialization
        json_str = spec.to_json()
        loaded = StrategySpec.from_json(json_str)
        assert loaded.name == spec.name, "JSON round-trip failed"
        print("JSON round-trip: PASSED")
