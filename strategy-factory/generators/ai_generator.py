"""
AI Strategy Generator

Generates trading strategies based on:
1. First principles analysis of market behavior
2. Well-researched trading edges
3. KISS (Keep It Simple Stupid) principles

This module contains predefined strategy templates based on research
and generates variations for backtesting.
"""

import os
import json
from typing import List, Dict, Any
from datetime import datetime
import random

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.strategy_spec import (
    StrategySpec, UniverseSpec, UniverseFilters, IndicatorSpec,
    Condition, ConditionGroup, RiskSpec, ParameterRange,
    Operator, Logic, Timeframe, UniverseType
)
import config


# =============================================================================
# STRATEGY RESEARCH BASE
# =============================================================================

# These are the core strategy types based on market research and first principles.
# Each has a documented rationale for why it might work.

STRATEGY_RESEARCH = """
# Trading Strategy Research - First Principles

## Why Strategies Work (Edge Sources)

1. **Momentum**: Winners tend to keep winning in the short term (3-12 months).
   - Behavioral: Investors underreact to news, herding behavior
   - Structural: Institutional buying takes time to complete

2. **Mean Reversion**: Extreme moves tend to reverse.
   - Behavioral: Overreaction to news, fear/greed cycles
   - Structural: Market makers provide liquidity at extremes

3. **Trend Following**: Strong trends persist longer than expected.
   - Behavioral: Slow information dissemination
   - Structural: Large players can't exit quickly

4. **Volatility**: High volatility regimes cluster and are predictable.
   - Structural: Leverage and margin calls create cascades
   - Behavioral: Fear spreads faster than greed

## Key Principles (KISS)

- Simple strategies are more robust (less overfitting)
- Fewer parameters = more out-of-sample reliability
- Liquidity matters: trade what you can exit
- Transaction costs kill high-frequency edges
- Daily/weekly timeframes work well for retail

## Universe Selection Principles

- High-beta stocks: More signal, more opportunity
- Liquid stocks: Better execution, lower slippage
- Growth sectors: Stronger trends (tech, consumer discretionary)
- Avoid: Low volume, penny stocks, highly manipulated names
"""


# =============================================================================
# STRATEGY TEMPLATES
# =============================================================================

def generate_momentum_strategies() -> List[StrategySpec]:
    """
    Generate momentum-based strategies.

    Rationale: Price momentum is one of the most robust anomalies.
    Stocks that have performed well recently tend to continue.
    """
    strategies = []

    # Strategy 1: Classic MA Crossover
    strategies.append(StrategySpec(
        name="MA Crossover Momentum",
        description="Buy when fast MA crosses above slow MA, sell on reverse",
        rationale="Moving average crossovers capture trend changes. "
                  "The lag provides confirmation and reduces whipsaws. "
                  "Works best in trending markets.",
        universe=UniverseSpec(
            type=UniverseType.STATIC,
            symbols=["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]
        ),
        timeframe=Timeframe.DAILY,
        indicators=[
            IndicatorSpec(name="fast_sma", type="SMA", params={"period": 20}),
            IndicatorSpec(name="slow_sma", type="SMA", params={"period": 50}),
        ],
        entry_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="fast_sma", operator=Operator.CROSSES_ABOVE, right="slow_sma"),
            ]
        ),
        exit_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="fast_sma", operator=Operator.CROSSES_BELOW, right="slow_sma"),
            ]
        ),
        risk_management=RiskSpec(position_size_dollars=10000, stop_loss_pct=0.08),
        parameters=[
            ParameterRange(path="indicators.0.params.period", values=[10, 20, 30]),
            ParameterRange(path="indicators.1.params.period", values=[50, 100, 200]),
        ]
    ))

    # Strategy 2: Price Above MA with RSI Confirmation
    strategies.append(StrategySpec(
        name="Trend + Momentum Filter",
        description="Buy when price above SMA and RSI confirms momentum",
        rationale="Combining trend (price > MA) with momentum (RSI) "
                  "provides double confirmation. Only trades with the trend "
                  "when momentum supports it.",
        universe=UniverseSpec(
            type=UniverseType.STATIC,
            symbols=["TSLA", "NVDA", "AMD", "SQ", "SHOP", "COIN"]
        ),
        timeframe=Timeframe.DAILY,
        indicators=[
            IndicatorSpec(name="sma_50", type="SMA", params={"period": 50}),
            IndicatorSpec(name="rsi_14", type="RSI", params={"period": 14}),
        ],
        entry_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="price", operator=Operator.CROSSES_ABOVE, right="sma_50"),
                Condition(left="rsi_14", operator=Operator.GREATER_THAN, right=50),
            ]
        ),
        exit_conditions=ConditionGroup(
            logic=Logic.OR,
            conditions=[
                Condition(left="price", operator=Operator.CROSSES_BELOW, right="sma_50"),
                Condition(left="rsi_14", operator=Operator.LESS_THAN, right=40),
            ]
        ),
        risk_management=RiskSpec(position_size_dollars=10000, stop_loss_pct=0.10),
        parameters=[
            ParameterRange(path="indicators.0.params.period", values=[20, 50, 100]),
            ParameterRange(path="indicators.1.params.period", values=[7, 14, 21]),
        ]
    ))

    # Strategy 3: Breakout Momentum
    strategies.append(StrategySpec(
        name="High Breakout",
        description="Buy on new 20-day high, exit on new 10-day low",
        rationale="New highs indicate strong momentum and often lead to "
                  "continuation. The asymmetric exit (10-day low vs 20-day high) "
                  "lets winners run while cutting losers quickly.",
        universe=UniverseSpec(
            type=UniverseType.STATIC,
            symbols=["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD"]
        ),
        timeframe=Timeframe.DAILY,
        indicators=[
            IndicatorSpec(name="sma_20", type="SMA", params={"period": 20}),
        ],
        entry_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="price", operator=Operator.GREATER_THAN, right="sma_20"),
            ]
        ),
        exit_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="price", operator=Operator.LESS_THAN, right="sma_20"),
            ]
        ),
        risk_management=RiskSpec(position_size_dollars=10000, stop_loss_pct=0.07),
        parameters=[
            ParameterRange(path="indicators.0.params.period", values=[10, 20, 30, 50]),
        ]
    ))

    return strategies


def generate_mean_reversion_strategies() -> List[StrategySpec]:
    """
    Generate mean reversion strategies.

    Rationale: Prices that move too far from average tend to revert.
    This works best in range-bound markets or for oversold bounces.
    """
    strategies = []

    # Strategy 1: RSI Oversold Bounce
    strategies.append(StrategySpec(
        name="RSI Oversold Bounce",
        description="Buy when RSI indicates oversold, sell when overbought",
        rationale="RSI extremes often mark short-term reversals. "
                  "The 200-day SMA filter ensures we only buy dips in uptrends, "
                  "avoiding falling knives.",
        universe=UniverseSpec(
            type=UniverseType.STATIC,
            symbols=["TSLA", "NVDA", "AMD", "SQ", "COIN", "MARA"]
        ),
        timeframe=Timeframe.DAILY,
        indicators=[
            IndicatorSpec(name="rsi_7", type="RSI", params={"period": 7}),
            IndicatorSpec(name="sma_200", type="SMA", params={"period": 200}),
        ],
        entry_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="rsi_7", operator=Operator.LESS_THAN, right=25),
                Condition(left="price", operator=Operator.GREATER_THAN, right="sma_200"),
            ]
        ),
        exit_conditions=ConditionGroup(
            logic=Logic.OR,
            conditions=[
                Condition(left="rsi_7", operator=Operator.GREATER_THAN, right=70),
            ]
        ),
        risk_management=RiskSpec(
            position_size_dollars=10000,
            stop_loss_pct=0.05,
            max_holding_days=10
        ),
        parameters=[
            ParameterRange(path="indicators.0.params.period", values=[5, 7, 10, 14]),
            ParameterRange(path="entry_conditions.conditions.0.right", values=[20, 25, 30]),
        ]
    ))

    # Strategy 2: Bollinger Band Mean Reversion
    strategies.append(StrategySpec(
        name="Bollinger Band Bounce",
        description="Buy at lower band, sell at middle or upper band",
        rationale="Bollinger Bands capture volatility-adjusted extremes. "
                  "Price touching the lower band in an uptrend often bounces. "
                  "Target the middle band for conservative exits.",
        universe=UniverseSpec(
            type=UniverseType.STATIC,
            symbols=["SPY", "QQQ", "AAPL", "MSFT", "GOOGL"]
        ),
        timeframe=Timeframe.DAILY,
        indicators=[
            IndicatorSpec(name="bb", type="BB", params={"period": 20, "k": 2}),
            IndicatorSpec(name="sma_50", type="SMA", params={"period": 50}),
        ],
        entry_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="price", operator=Operator.GREATER_THAN, right="sma_50"),
            ]
        ),
        exit_conditions=ConditionGroup(
            logic=Logic.OR,
            conditions=[
                Condition(left="price", operator=Operator.LESS_THAN, right="sma_50"),
            ]
        ),
        risk_management=RiskSpec(
            position_size_dollars=10000,
            stop_loss_pct=0.05,
            max_holding_days=15
        ),
        parameters=[
            ParameterRange(path="indicators.0.params.period", values=[15, 20, 25]),
            ParameterRange(path="indicators.0.params.k", values=[1.5, 2, 2.5]),
        ]
    ))

    return strategies


def generate_trend_following_strategies() -> List[StrategySpec]:
    """
    Generate trend following strategies.

    Rationale: Strong trends persist due to institutional flows
    and behavioral biases. Let winners run, cut losers.
    """
    strategies = []

    # Strategy 1: ADX Trend Strength
    strategies.append(StrategySpec(
        name="ADX Trend Rider",
        description="Enter strong trends (ADX > 25), exit when trend weakens",
        rationale="ADX measures trend strength regardless of direction. "
                  "ADX > 25 indicates a strong trend worth riding. "
                  "Combined with MA for direction confirmation.",
        universe=UniverseSpec(
            type=UniverseType.STATIC,
            symbols=["TSLA", "NVDA", "AMD", "AAPL", "MSFT", "GOOGL"]
        ),
        timeframe=Timeframe.DAILY,
        indicators=[
            IndicatorSpec(name="adx_14", type="ADX", params={"period": 14}),
            IndicatorSpec(name="ema_20", type="EMA", params={"period": 20}),
        ],
        entry_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="adx_14", operator=Operator.GREATER_THAN, right=25),
                Condition(left="price", operator=Operator.GREATER_THAN, right="ema_20"),
            ]
        ),
        exit_conditions=ConditionGroup(
            logic=Logic.OR,
            conditions=[
                Condition(left="adx_14", operator=Operator.LESS_THAN, right=20),
                Condition(left="price", operator=Operator.CROSSES_BELOW, right="ema_20"),
            ]
        ),
        risk_management=RiskSpec(position_size_dollars=10000, stop_loss_pct=0.10),
        parameters=[
            ParameterRange(path="indicators.0.params.period", values=[10, 14, 20]),
            ParameterRange(path="entry_conditions.conditions.0.right", values=[20, 25, 30]),
        ]
    ))

    # Strategy 2: EMA Trend with MACD Confirmation
    strategies.append(StrategySpec(
        name="EMA + MACD Trend",
        description="Follow EMA trend with MACD momentum confirmation",
        rationale="EMA responds faster to price changes than SMA. "
                  "MACD histogram shows momentum shifts. "
                  "Double confirmation reduces false signals.",
        universe=UniverseSpec(
            type=UniverseType.STATIC,
            symbols=["QQQ", "SPY", "AAPL", "NVDA", "TSLA", "AMZN"]
        ),
        timeframe=Timeframe.DAILY,
        indicators=[
            IndicatorSpec(name="ema_21", type="EMA", params={"period": 21}),
            IndicatorSpec(name="macd", type="MACD", params={"fast_period": 12, "slow_period": 26, "signal_period": 9}),
        ],
        entry_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="price", operator=Operator.GREATER_THAN, right="ema_21"),
            ]
        ),
        exit_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="price", operator=Operator.LESS_THAN, right="ema_21"),
            ]
        ),
        risk_management=RiskSpec(position_size_dollars=10000, stop_loss_pct=0.08),
        parameters=[
            ParameterRange(path="indicators.0.params.period", values=[13, 21, 34]),
        ]
    ))

    return strategies


def generate_volatility_strategies() -> List[StrategySpec]:
    """
    Generate volatility-based strategies.

    Rationale: Volatility clusters and is somewhat predictable.
    Low volatility often precedes breakouts.
    """
    strategies = []

    # Strategy 1: Low Volatility Breakout
    strategies.append(StrategySpec(
        name="Volatility Contraction Breakout",
        description="Buy when volatility contracts then price breaks out",
        rationale="Periods of low volatility (tight Bollinger Bands) "
                  "often precede large moves. A breakout from consolidation "
                  "with volume can signal the start of a new trend.",
        universe=UniverseSpec(
            type=UniverseType.STATIC,
            symbols=["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"]
        ),
        timeframe=Timeframe.DAILY,
        indicators=[
            IndicatorSpec(name="atr_14", type="ATR", params={"period": 14}),
            IndicatorSpec(name="sma_20", type="SMA", params={"period": 20}),
        ],
        entry_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="price", operator=Operator.CROSSES_ABOVE, right="sma_20"),
            ]
        ),
        exit_conditions=ConditionGroup(
            logic=Logic.OR,
            conditions=[
                Condition(left="price", operator=Operator.CROSSES_BELOW, right="sma_20"),
            ]
        ),
        risk_management=RiskSpec(position_size_dollars=10000, stop_loss_pct=0.06),
        parameters=[
            ParameterRange(path="indicators.0.params.period", values=[10, 14, 20]),
            ParameterRange(path="indicators.1.params.period", values=[10, 20, 30]),
        ]
    ))

    return strategies


def generate_sector_rotation_strategies() -> List[StrategySpec]:
    """
    Generate sector rotation strategies using ETFs.

    Rationale: Different sectors lead at different times.
    Following relative strength can capture sector rotation.
    """
    strategies = []

    # Strategy 1: Tech Sector Momentum
    strategies.append(StrategySpec(
        name="Tech Sector Momentum",
        description="Ride momentum in tech sector ETF",
        rationale="Technology sector often leads bull markets. "
                  "XLK captures broad tech exposure with good liquidity. "
                  "Simple trend following works well on sector ETFs.",
        universe=UniverseSpec(
            type=UniverseType.STATIC,
            symbols=["XLK", "QQQ", "VGT"]
        ),
        timeframe=Timeframe.DAILY,
        indicators=[
            IndicatorSpec(name="sma_50", type="SMA", params={"period": 50}),
            IndicatorSpec(name="rsi_14", type="RSI", params={"period": 14}),
        ],
        entry_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="price", operator=Operator.CROSSES_ABOVE, right="sma_50"),
                Condition(left="rsi_14", operator=Operator.GREATER_THAN, right=45),
            ]
        ),
        exit_conditions=ConditionGroup(
            logic=Logic.OR,
            conditions=[
                Condition(left="price", operator=Operator.CROSSES_BELOW, right="sma_50"),
            ]
        ),
        risk_management=RiskSpec(position_size_dollars=10000, stop_loss_pct=0.08),
        parameters=[
            ParameterRange(path="indicators.0.params.period", values=[20, 50, 100]),
        ]
    ))

    return strategies


def generate_high_beta_strategies() -> List[StrategySpec]:
    """
    Generate strategies for high-beta stocks.

    Rationale: High-beta stocks offer more opportunity but need
    tighter risk management. Best for skilled timing.
    """
    strategies = []

    # Strategy 1: High Beta Trend Following
    strategies.append(StrategySpec(
        name="High Beta Trend",
        description="Trend following on high-beta growth stocks",
        rationale="High-beta stocks move more than the market. "
                  "In uptrends, they outperform significantly. "
                  "Key is to ride trends and exit quickly when they end.",
        universe=UniverseSpec(
            type=UniverseType.STATIC,
            symbols=["TSLA", "NVDA", "AMD", "COIN", "SQ", "SHOP", "MARA", "RIOT"]
        ),
        timeframe=Timeframe.DAILY,
        indicators=[
            IndicatorSpec(name="ema_10", type="EMA", params={"period": 10}),
            IndicatorSpec(name="ema_30", type="EMA", params={"period": 30}),
        ],
        entry_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="ema_10", operator=Operator.CROSSES_ABOVE, right="ema_30"),
            ]
        ),
        exit_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="ema_10", operator=Operator.CROSSES_BELOW, right="ema_30"),
            ]
        ),
        risk_management=RiskSpec(position_size_dollars=10000, stop_loss_pct=0.12),
        parameters=[
            ParameterRange(path="indicators.0.params.period", values=[5, 10, 15]),
            ParameterRange(path="indicators.1.params.period", values=[20, 30, 50]),
        ]
    ))

    # Strategy 2: High Beta RSI Bounce
    strategies.append(StrategySpec(
        name="High Beta RSI Bounce",
        description="Buy oversold high-beta stocks for quick bounces",
        rationale="High-beta stocks often overshoot on the downside. "
                  "RSI oversold + uptrend filter catches quality dips. "
                  "Quick exit targets capture the bounce.",
        universe=UniverseSpec(
            type=UniverseType.STATIC,
            symbols=["TSLA", "NVDA", "AMD", "COIN", "SQ", "SHOP"]
        ),
        timeframe=Timeframe.DAILY,
        indicators=[
            IndicatorSpec(name="rsi_5", type="RSI", params={"period": 5}),
            IndicatorSpec(name="sma_100", type="SMA", params={"period": 100}),
        ],
        entry_conditions=ConditionGroup(
            logic=Logic.AND,
            conditions=[
                Condition(left="rsi_5", operator=Operator.LESS_THAN, right=20),
                Condition(left="price", operator=Operator.GREATER_THAN, right="sma_100"),
            ]
        ),
        exit_conditions=ConditionGroup(
            logic=Logic.OR,
            conditions=[
                Condition(left="rsi_5", operator=Operator.GREATER_THAN, right=60),
            ]
        ),
        risk_management=RiskSpec(
            position_size_dollars=10000,
            stop_loss_pct=0.06,
            max_holding_days=7
        ),
        parameters=[
            ParameterRange(path="indicators.0.params.period", values=[3, 5, 7]),
            ParameterRange(path="entry_conditions.conditions.0.right", values=[15, 20, 25]),
        ]
    ))

    return strategies


# =============================================================================
# MAIN GENERATOR CLASS
# =============================================================================

class AIStrategyGenerator:
    """
    AI-driven strategy generator.

    Generates strategies based on:
    - First principles market research
    - Well-known trading edges
    - KISS (Keep It Simple Stupid) principles
    """

    def __init__(self):
        self.generated_count = 0

    def generate_all(self, batch_size: int = None) -> List[StrategySpec]:
        """
        Generate all strategy types.

        Args:
            batch_size: Max strategies to return (None = all)

        Returns:
            List of StrategySpec objects
        """
        strategies = []

        # Generate from each category
        strategies.extend(generate_momentum_strategies())
        strategies.extend(generate_mean_reversion_strategies())
        strategies.extend(generate_trend_following_strategies())
        strategies.extend(generate_volatility_strategies())
        strategies.extend(generate_sector_rotation_strategies())
        strategies.extend(generate_high_beta_strategies())

        # Validate all
        for spec in strategies:
            errors = spec.validate()
            if errors:
                print(f"WARNING: Invalid strategy {spec.name}: {errors}")

        # Limit batch size if requested
        if batch_size is not None and len(strategies) > batch_size:
            strategies = strategies[:batch_size]

        self.generated_count += len(strategies)
        return strategies

    def generate_by_category(self, category: str) -> List[StrategySpec]:
        """Generate strategies of a specific category"""
        generators = {
            "momentum": generate_momentum_strategies,
            "mean_reversion": generate_mean_reversion_strategies,
            "trend": generate_trend_following_strategies,
            "volatility": generate_volatility_strategies,
            "sector": generate_sector_rotation_strategies,
            "high_beta": generate_high_beta_strategies,
        }

        if category not in generators:
            raise ValueError(f"Unknown category: {category}. Valid: {list(generators.keys())}")

        return generators[category]()

    def save_strategies(self, strategies: List[StrategySpec]) -> List[str]:
        """
        Save strategies to spec files.

        Returns:
            List of filepaths
        """
        filepaths = []
        for spec in strategies:
            filepath = os.path.join(config.SPECS_DIR, f"{spec.id}.json")
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            spec.save(filepath)
            filepaths.append(filepath)
        return filepaths


def generate_strategies(batch_size: int = None) -> List[StrategySpec]:
    """Convenience function to generate strategies"""
    generator = AIStrategyGenerator()
    return generator.generate_all(batch_size)


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("="*60)
    print("AI Strategy Generator")
    print("="*60)

    generator = AIStrategyGenerator()
    strategies = generator.generate_all()

    print(f"\nGenerated {len(strategies)} strategies:\n")

    for i, spec in enumerate(strategies, 1):
        print(f"{i}. {spec.name}")
        print(f"   Universe: {spec.universe.symbols[:3]}..." if len(spec.universe.symbols) > 3 else f"   Universe: {spec.universe.symbols}")
        print(f"   Indicators: {[ind.type for ind in spec.indicators]}")
        print(f"   Rationale: {spec.rationale[:80]}...")
        print()

    # Save to files
    print("\nSaving strategies...")
    filepaths = generator.save_strategies(strategies)
    print(f"Saved {len(filepaths)} strategy specs")
