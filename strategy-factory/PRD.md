# Strategy Factory - Product Requirements Document

## Vision

An **AI + Programmatic** system for generating, testing, and refining trading strategies at scale.

- **AI (Claude Code)**: Generates strategy ideas through first-principles thinking, research, and reasoning
- **Programmatic**: Infrastructure to compile, backtest, parse, validate, and rank strategies automatically

The key insight: **Claude Code IS the strategy generator.** Not templates. Not hardcoded rules. Claude Code reasons through each strategy proposal, explains why it might work, and designs the implementation.

---

## Problem Statement

Manual strategy development is slow and limited by human bandwidth:
- Researching edges takes time
- Coding each strategy is tedious
- Backtesting is manual and error-prone
- Iterating on parameters is labor-intensive

**Solution**: Claude Code proposes strategies through reasoning. Infrastructure handles the execution. Results feed back into the next iteration.

---

## How It Works

### Phase 1: Strategy Generation (AI)

Claude Code generates strategies by:

1. **Research**: What market inefficiencies exist? What edges have been documented?
2. **First Principles**: WHY would this strategy work? What behavioral or structural factor creates the edge?
3. **Hypothesis**: Clear, testable thesis (e.g., "Momentum persists because institutions buy slowly")
4. **Design**: Choose indicators, entry/exit rules, and universe that match the thesis
5. **KISS**: Keep it simple - max 3 indicators, clear logic

**Output**: Strategy specification (JSON) with:
- Name & description
- Rationale (the WHY)
- Universe (stocks that fit the thesis)
- Indicators (only what's needed)
- Entry/exit conditions
- Risk management
- Parameter ranges for sweeping

### Phase 2: Backtesting (Programmatic)

Infrastructure automatically:

1. **Compiles** spec → QuantConnect Python code
2. **Runs** backtest via QC cloud API
3. **Parses** results (Sharpe, CAGR, drawdown, etc.)
4. **Validates** across market regimes
5. **Ranks** strategies by composite score

### Phase 3: Refinement (AI + Programmatic)

For winning strategies:

1. **Parameter Sweep**: Test variations programmatically
2. **Analysis**: Claude Code reviews results, identifies patterns
3. **Iteration**: Claude Code proposes improvements based on data
4. **Combination**: Mix signals from different strategies

---

## Strategy Generation Guidelines

When Claude Code generates strategies, follow these principles:

### 1. Start with the Edge

Before designing any strategy, answer:
- **What market inefficiency am I exploiting?**
- **Why does this inefficiency exist?** (behavioral bias, structural constraint, information asymmetry)
- **Why hasn't it been arbitraged away?** (capacity limits, execution costs, behavioral persistence)

### 2. Match Universe to Thesis

Stock selection IS part of the strategy:
- Momentum strategies → high-beta, growth stocks (TSLA, NVDA, AMD)
- Mean reversion → liquid, range-bound stocks (SPY, QQQ, large caps)
- Volatility strategies → stocks with regime changes
- Sector rotation → sector ETFs

### 3. Keep It Simple (KISS)

- Max 3 indicators
- Max 2 entry conditions
- Max 2 exit conditions
- Clear, unambiguous logic
- Simple > complex (less overfitting)

### 4. Document the Why

Every strategy must have a clear rationale:
- Not: "Buy when RSI < 30"
- But: "RSI < 30 indicates oversold conditions. Combined with price above 200 SMA (uptrend filter), we catch quality dips that tend to revert. This works because fear-driven selling overshoots fair value."

### 5. Think About Failure Modes

- When would this strategy fail?
- What market regime is worst for it?
- How do we detect when to stop using it?

---

## Infrastructure Components

### Compiler (`core/compiler.py`)
- Converts strategy spec → QC Python code
- Injects safety guards (slippage, commissions, data checks)
- Handles all supported indicator types

### Runner (`core/runner.py`)
- Orchestrates QC cloud API calls
- Rate limiting (30 req/min)
- Retry logic with backoff
- Polls for completion

### Parser (`core/parser.py`)
- Extracts metrics from backtest results
- Handles QC API response format
- Returns structured metrics object

### Validator (`core/validator.py`)
- Walk-forward validation
- Regime analysis (bull/bear/sideways)
- Consistency checks

### Ranker (`core/ranker.py`)
- Composite scoring (Sharpe, CAGR, drawdown, etc.)
- Penalty system (high turnover, few trades, etc.)
- Ranking and selection

---

## Strategy Spec Schema

```json
{
  "id": "uuid",
  "name": "Strategy Name",
  "description": "What it does",
  "rationale": "WHY it works - the edge being exploited",

  "universe": {
    "type": "static",
    "symbols": ["TSLA", "NVDA", "AMD"]
  },

  "timeframe": "daily",

  "indicators": [
    {"name": "fast_ema", "type": "EMA", "params": {"period": 12}},
    {"name": "slow_ema", "type": "EMA", "params": {"period": 26}}
  ],

  "entry_conditions": {
    "logic": "AND",
    "conditions": [
      {"left": "fast_ema", "operator": "crosses_above", "right": "slow_ema"}
    ]
  },

  "exit_conditions": {
    "logic": "AND",
    "conditions": [
      {"left": "fast_ema", "operator": "crosses_below", "right": "slow_ema"}
    ]
  },

  "risk_management": {
    "position_size_dollars": 10000,
    "stop_loss_pct": 0.08
  },

  "parameters": [
    {"path": "indicators.0.params.period", "values": [8, 12, 21]}
  ]
}
```

---

## Supported Indicators

### Trend
- SMA (Simple Moving Average)
- EMA (Exponential Moving Average)
- ADX (Average Directional Index)

### Momentum
- RSI (Relative Strength Index)
- ROC (Rate of Change)

### Volatility
- ATR (Average True Range)
- Bollinger Bands (use with caution - complex)

### Custom
Claude Code can propose custom indicators if they serve the thesis. The infrastructure can be extended to support them.

---

## Workflow

### Daily/Weekly Strategy Development

```
1. Claude Code researches edges and proposes 5-10 new strategies
   └── Each with clear rationale and thesis

2. Infrastructure backtests all strategies
   └── Automatic: compile → run → parse → validate

3. Claude Code reviews results
   └── What worked? What didn't? Why?

4. Winners go to parameter sweep
   └── Automatic: generate variations → backtest all

5. Claude Code analyzes sweep results
   └── Optimal parameters? Overfitting concerns?

6. Top strategies ranked and documented
   └── Ready for paper trading
```

### Command to Run

```bash
# Generate and test strategies
python strategy-factory/run_pipeline.py --batch-size 10

# The pipeline will:
# 1. Ask Claude Code to generate strategies (or use existing specs)
# 2. Backtest all of them
# 3. Filter, validate, rank
# 4. Output report
```

---

## Success Criteria

### Minimum Viable Strategy
- Sharpe Ratio > 0.5
- CAGR > 10%
- Max Drawdown < 30%
- At least 30 trades
- Passes walk-forward validation

### Target Performance (beat benchmarks)
- Sharpe > 0.8 (vs 0.57 for buy-hold)
- CAGR > 15% (vs 17% for buy-hold, but with better risk-adjusted)
- Max Drawdown < 25% (vs 30% for buy-hold)

### Quality Metrics
- Clear, documented rationale for every strategy
- Universe matches the thesis
- No overfitting (out-of-sample validation)
- Realistic execution assumptions

---

## Constraints

- **Long-only** (initial phase)
- **Daily timeframe** minimum
- **US equities** primary focus
- **IBKR** as target broker
- **$100k** starting capital assumption
- **No leverage** initially

---

## Future Enhancements

- Short selling support
- Options strategies
- Multi-asset (crypto, forex)
- Portfolio-level optimization
- Live paper trading integration
- ML-based pattern discovery

---

## Key Principle

**Claude Code doesn't just execute templates. Claude Code thinks.**

Every strategy should reflect genuine reasoning about:
- What edge exists
- Why it exists
- How to capture it
- When it might fail

This is what separates this system from a simple parameter grid search.
