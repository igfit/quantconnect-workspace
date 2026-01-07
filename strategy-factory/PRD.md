# Strategy Factory - Product Requirements Document

## Vision

An **AI + Programmatic** system for generating, testing, and refining trading strategies at scale.

- **AI (Claude Code)**: Generates strategy ideas through first-principles thinking, research, and reasoning
- **Programmatic**: Infrastructure to compile, backtest, parse, validate, and rank strategies automatically

The key insight: **Claude Code IS the strategy generator.** Not templates. Not hardcoded rules. Claude Code reasons through each strategy proposal, explains why it might work, and designs the implementation.

**Claude Code owns the entire ideation loop** - from deciding what to explore, to designing strategies, to analyzing results, to proposing next steps.

---

## Problem Statement

Manual strategy development is slow and limited by human bandwidth:
- Researching edges takes time
- Coding each strategy is tedious
- Backtesting is manual and error-prone
- Iterating on parameters is labor-intensive

**Solution**: Claude Code proposes strategies through reasoning. Infrastructure handles the execution. Results feed back into the next iteration. The user just says "generate strategies" and reviews the output.

---

## How It Works

### Phase 0: Meta-Reasoning (AI Decides What to Explore)

Before generating any strategies, Claude Code must decide what to explore:

1. **Survey existing work**:
   - Read `strategies/specs/` - what strategies exist?
   - Read `results/summary.csv` - what performed well/poorly?
   - Read `NOTES.md` - what learnings have accumulated?

2. **Identify gaps and opportunities**:
   - What strategy types are underrepresented?
   - What worked that we should explore more?
   - What failed that we should avoid?
   - What edges haven't we tested yet?

3. **Form a thesis for this round**:
   - "Momentum on high-beta stocks looks promising because..."
   - "Mean reversion failed last round, but oversold bounces in uptrends might work..."
   - "We haven't tested sector rotation yet..."

4. **Document the decision**:
   - Log reasoning in NOTES.md
   - Explain why this direction was chosen

**Output**: A clear direction for strategy generation this round.

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

### Phase 3: Analysis & Iteration (AI)

Claude Code analyzes results and decides next steps:

1. **Review results**: What worked? What didn't? Why?
2. **Validate thesis**: Did the hypothesis hold?
3. **Identify patterns**: What do winning strategies have in common?
4. **Propose refinements**: Parameter tweaks, universe changes, new variations
5. **Decide next direction**: Double down on winners or explore new areas?

**Output**: Updated NOTES.md with learnings, new strategy specs for next round.

### Phase 4: Parameter Sweep (Programmatic)

For promising strategies:

1. **Generate variations**: Test parameter combinations programmatically
2. **Backtest all**: Run through infrastructure
3. **Analyze**: Claude Code reviews sweep results for optimal parameters

---

## The Full Autonomous Loop

```
User: "Generate strategies" (or scheduled trigger)
                ↓
┌─────────────────────────────────────────────────────────────┐
│  PHASE 0: META-REASONING                                     │
│  Claude Code asks: "What should I explore?"                  │
│  - Reads existing specs and results                          │
│  - Identifies gaps and opportunities                         │
│  - Forms thesis: "I'll explore X because Y"                  │
│  - Documents decision in NOTES.md                            │
└─────────────────────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1: STRATEGY GENERATION                                │
│  Claude Code designs 5-10 strategies:                        │
│  - Each with clear rationale (the WHY)                       │
│  - Universe matched to thesis                                │
│  - Simple indicators and conditions                          │
│  - Outputs JSON specs to strategies/specs/                   │
└─────────────────────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────────────────────┐
│  PHASE 2: BACKTESTING (Automatic)                            │
│  Infrastructure runs:                                        │
│  - Compile specs → QC code                                   │
│  - Run backtests via API                                     │
│  - Parse results                                             │
│  - Validate and rank                                         │
└─────────────────────────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────────────────────────┐
│  PHASE 3: ANALYSIS & ITERATION                               │
│  Claude Code reviews:                                        │
│  - What worked? What failed? Why?                            │
│  - Did the thesis hold?                                      │
│  - What to try next?                                         │
│  - Updates NOTES.md with learnings                           │
└─────────────────────────────────────────────────────────────┘
                ↓
         [Repeat loop]
```

**The user doesn't need to provide direction.** Claude Code decides what to explore based on accumulated knowledge and results.

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

### How to Trigger Strategy Generation

The user simply asks Claude Code to generate strategies:

```
User: "Generate new strategies"
User: "Find winning trading strategies"
User: "Run the strategy factory"
```

Claude Code then autonomously:
1. Decides what to explore (meta-reasoning)
2. Generates strategy specs
3. Runs backtests via infrastructure
4. Analyzes results
5. Proposes next steps

### Example Session

```
User: "Generate new strategies"

Claude Code:
1. [Meta-reasoning] Let me check what we've tried so far...
   - Reading existing specs... found 15 strategies
   - Reading results... momentum strategies performed best (Sharpe 0.8)
   - Gap identified: Haven't tested mean reversion on large caps

2. [Thesis] I'll explore oversold bounces on liquid large caps because:
   - Fear-driven selling often overshoots fair value
   - Large caps mean-revert faster due to institutional buying
   - RSI + uptrend filter should catch quality dips

3. [Generation] Creating 5 strategies:
   - RSI Oversold Bounce (SPY, QQQ)
   - RSI + Volume Spike (AAPL, MSFT, GOOGL)
   - Oversold in Uptrend (large cap tech)
   - ...

4. [Backtest] Running infrastructure...
   - Strategy 1: Sharpe 0.65, CAGR 12%
   - Strategy 2: Sharpe 0.45, CAGR 8%
   - ...

5. [Analysis] Results show:
   - RSI works better with shorter periods (5 vs 14)
   - Volume confirmation helps avoid false signals
   - Thesis partially validated - works in uptrends only

6. [Next steps] Recommend:
   - Parameter sweep on Strategy 1 (promising)
   - Try combining with momentum filter
   - Document learnings in NOTES.md
```

### Running Backtests

After Claude Code generates specs, run the infrastructure:

```bash
# Backtest all specs in the directory
python strategy-factory/run_pipeline.py

# Backtest specific specs
python strategy-factory/run_pipeline.py --spec-ids abc123,def456

# Skip parameter sweep
python strategy-factory/run_pipeline.py --skip-sweep
```

### Files Claude Code Should Read/Write

| Action | Files |
|--------|-------|
| Check existing strategies | `strategies/specs/*.json` |
| Check past results | `results/summary.csv` |
| Check learnings | `NOTES.md` |
| Write new specs | `strategies/specs/{id}.json` |
| Document learnings | `NOTES.md` |

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
