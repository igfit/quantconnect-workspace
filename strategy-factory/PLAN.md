# Strategy Factory - Implementation Plan

## Overview

An AI-driven strategy generation and backtesting system for US equities. The system generates trading strategies using first principles thinking, backtests them via QuantConnect API, and refines winners through parameter sweeps and combinatorial optimization.

**Goal:** Generate strategies suitable for paper trading and eventual live deployment on IBKR.

---

## Key Requirements

| Requirement | Specification |
|-------------|---------------|
| Asset class | US equities (primary), other major exchanges |
| Timeframe | Daily or slower (daily/weekly/monthly candles) |
| Direction | Long-only (initial phase) |
| Position sizing | Fixed dollar per trade |
| Holding period | Strategy-determined |
| Broker target | Interactive Brokers (IBKR) |
| Validation | Moderate (walk-forward, realistic costs) |

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  AI Generator   │────▶│    Compiler     │────▶│   QC Runner     │
│  (strategies)   │     │  (spec→code)    │     │  (backtest)     │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
┌─────────────────┐     ┌─────────────────┐     ┌────────▼────────┐
│     Ranker      │◀────│    Validator    │◀────│     Parser      │
│   (scoring)     │     │ (walk-forward)  │     │   (metrics)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## File Structure

```
strategy-factory/
├── PLAN.md                   # This file - implementation plan
├── TODOS.md                  # Progress tracking (always updated)
├── NOTES.md                  # Learnings during implementation
├── config.py                 # Constants, thresholds, API settings
├── models/
│   └── strategy_spec.py      # Strategy dataclass/schema
├── core/
│   ├── compiler.py           # Spec → QC Python code
│   ├── runner.py             # QC API orchestration
│   ├── parser.py             # Extract metrics from results
│   ├── validator.py          # Walk-forward, regime analysis
│   └── ranker.py             # Score and rank strategies
├── generators/
│   ├── ai_generator.py       # AI-driven strategy proposals
│   ├── param_sweeper.py      # Parameter grid search
│   └── combiner.py           # Combinatorial signal mixing
├── templates/
│   └── base_algorithm.py     # QC template with safety guards
├── strategies/               # VERSION CONTROLLED STRATEGIES
│   ├── specs/                # Strategy specs (JSON)
│   │   └── {id}.json
│   ├── compiled/             # Generated QC code
│   │   └── {id}.py
│   └── registry.json         # Index of all strategies
├── results/                  # Backtest results
│   ├── {strategy_id}/
│   │   ├── metrics.json
│   │   ├── trades.csv
│   │   └── equity_curve.csv
│   └── summary.csv           # All strategies comparison
├── run_pipeline.py           # Main orchestration script
└── README.md                 # Usage instructions
```

---

## Strategy Version Control

Every strategy is saved and tracked:

1. **Spec saved**: `strategies/specs/{id}.json`
2. **Code saved**: `strategies/compiled/{id}.py`
3. **Registry updated**: `strategies/registry.json`
4. **Git commit**: After each generation batch

```json
// strategies/registry.json
{
  "strategies": [
    {
      "id": "abc123",
      "name": "Simple Momentum",
      "created": "2024-01-15T10:30:00Z",
      "status": "validated",
      "best_sharpe": 1.25,
      "parent_id": null,
      "children": ["def456", "ghi789"]
    }
  ]
}
```

---

## Strategy Spec Schema

```python
@dataclass
class StrategySpec:
    # Metadata
    id: str                     # UUID
    name: str                   # Human-readable
    description: str            # What it does
    rationale: str              # Why it might work
    parent_id: Optional[str]    # If derived from another strategy

    # Universe Selection
    universe: UniverseSpec
      type: Literal["static", "dynamic"]
      symbols: List[str]        # If static
      filters: UniverseFilters  # If dynamic
        min_price: float = 5.0
        min_dollar_volume: float = 500_000
        sector: Optional[str]
        index: Optional[str]    # "SP500", "NASDAQ100"
        max_symbols: int = 50

    # Timeframe
    timeframe: Literal["daily", "weekly", "monthly"]

    # Indicators (max 3 for KISS)
    indicators: List[IndicatorSpec]
      name: str                 # Reference name
      type: str                 # "SMA", "EMA", "RSI", etc.
      params: Dict[str, Any]    # {"period": 20}
      source: str = "close"     # Price field to use

    # Entry Conditions (max 2)
    entry_conditions: ConditionGroup
      logic: Literal["AND", "OR"]
      conditions: List[Condition]
        left: str               # Indicator name or "price"
        operator: str           # ">", "<", "crosses_above", "crosses_below"
        right: Union[str, float]

    # Exit Conditions (max 2)
    exit_conditions: ConditionGroup

    # Risk Management
    risk_management: RiskSpec
      position_size_dollars: float
      stop_loss_pct: Optional[float]
      take_profit_pct: Optional[float]
      max_holding_days: Optional[int]

    # Parameter Ranges (for sweeping)
    parameters: List[ParameterRange]
      path: str                 # e.g., "indicators.0.params.period"
      values: List[Any]         # [10, 20, 30, 50]
```

---

## Live-Safety Guards

**Non-negotiable rules baked into every generated strategy:**

| Guard | Implementation | Why |
|-------|----------------|-----|
| No look-ahead | Signal day T → trade day T+1 open | Can't trade on close you just saw |
| Realistic fills | `MarketOnOpenOrder` + 0.1% slippage | Market orders slip |
| Commissions | IBKR: $0.005/share, $1 min | Real costs matter |
| Liquidity filter | Min 500k daily dollar volume | Must be able to exit |
| Price filter | Min $5 stock price | Avoid penny stocks |
| Warmup period | `SetWarmup(indicator_period + 10)` | Indicators need data |
| Data checks | `data.ContainsKey(symbol)` | Handle missing data |
| Single position | One position per symbol max | No pyramiding initially |

---

## Date Range Configuration

**Flexible date ranges** to support both 5-year and 10-year backtests:

```python
# config.py
DATE_RANGES = {
    "5_year": {
        "full": ("2020-01-01", "2024-12-31"),
        "train": ("2020-01-01", "2022-06-30"),
        "validate": ("2022-07-01", "2023-06-30"),
        "test": ("2023-07-01", "2024-12-31"),
    },
    "10_year": {
        "full": ("2015-01-01", "2024-12-31"),
        "train": ("2015-01-01", "2020-06-30"),
        "validate": ("2020-07-01", "2022-06-30"),
        "test": ("2022-07-01", "2024-12-31"),
    },
}

# User can select which range to use
ACTIVE_DATE_RANGE = "5_year"  # or "10_year"
```

---

## Evaluation Framework

### Primary Metrics

| Metric | Min Threshold | Weight |
|--------|---------------|--------|
| Sharpe Ratio | > 0.8 | 30% |
| CAGR | > 10% | 25% |
| Max Drawdown | < 25% | 20% |
| Profit Factor | > 1.3 | 15% |
| Win Rate | > 45% | 10% |

### Disqualifiers

- Negative returns in 2+ years
- Fewer than 30 trades
- Max drawdown > 40%
- Only profitable in bull market

### Scoring Formula

```python
score = (
    0.30 * normalize(sharpe, 0, 3) +
    0.25 * normalize(cagr, 0, 0.5) +
    0.20 * normalize(1 - abs(max_dd), 0, 1) +
    0.15 * normalize(profit_factor, 1, 3) +
    0.10 * normalize(win_rate, 0.3, 0.7)
)

# Penalties
if turnover > 50:  # trades per year
    score *= 0.9
if trade_count < 30:
    score *= 0.8
if not profitable_in_bear_market:
    score *= 0.7
```

---

## Pipeline Phases

### Phase 1: AI Generation
- Research market edges and known strategies
- Apply first principles thinking
- Generate 15-20 StrategySpecs
- Save all specs to `strategies/specs/`
- Git commit: "Generate batch {n} strategies"

### Phase 2: Initial Backtest
- Compile each spec to QC code
- Save code to `strategies/compiled/`
- Run backtests via QC API (sandbox project)
- Parse and save results
- Filter to strategies meeting thresholds
- Expected output: ~5-8 passing strategies

### Phase 3: Parameter Sweep
- For each passing strategy, generate parameter variations
- Run all variations
- Save all results
- Expected output: ~50-100 variants

### Phase 4: Validation
- Walk-forward testing on all variants
- Regime analysis (bull/bear/sideways)
- Filter to consistent performers
- Expected output: ~10-15 validated strategies

### Phase 5: Ranking
- Calculate composite scores
- Apply penalties
- Rank strategies
- Select top 5 for paper trading

### Phase 6: Report
- Generate summary report
- Strategy descriptions with rationale
- Performance metrics and charts
- Paper trading recommendations
- Git commit: "Complete pipeline run {date}"

---

## QC API Usage

### Sandbox Project
- Single project for all backtests
- Overwrite `main.py` each time
- Backtest naming: `{strategy_id}_{timestamp}`

### Rate Limiting
- 30 requests/minute limit
- ~6 API calls per backtest
- Built-in delays and retry logic
- Expected throughput: ~40-50 backtests/hour

### API Workflow
```
1. Push code      → POST /files/update
2. Compile        → POST /compile/create
3. Start backtest → POST /backtests/create
4. Poll status    → POST /backtests/read (repeat until done)
5. Get results    → POST /backtests/read (final)
```

---

## Universe Options

### Static Universes
- High-beta tech: TSLA, NVDA, AMD, COIN, SQ, SHOP
- FAANG+: AAPL, AMZN, GOOGL, META, MSFT, NFLX
- Sector ETFs: XLK, XLF, XLE, XLV, etc.

### Dynamic Universe Filters
- S&P 500 constituents
- NASDAQ 100 constituents
- Top N by dollar volume
- Top N by 6-month momentum
- Sector + market cap filters

---

## Indicator Library

### Trend
- SMA (Simple Moving Average)
- EMA (Exponential Moving Average)
- ADX (Average Directional Index)

### Momentum
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- ROC (Rate of Change)

### Volatility
- ATR (Average True Range)
- Bollinger Bands

### Volume
- OBV (On-Balance Volume)
- Volume SMA

---

## Implementation Order

### Week 1: Foundation
- [ ] `config.py` - Constants, settings, date ranges
- [ ] `models/strategy_spec.py` - Data structures
- [ ] `templates/base_algorithm.py` - QC template with safety guards
- [ ] `strategies/registry.json` - Initialize registry

### Week 2: Core Pipeline
- [ ] `core/compiler.py` - Spec to QC code
- [ ] `core/runner.py` - API orchestration with rate limiting
- [ ] `core/parser.py` - Results extraction

### Week 3: Generators
- [ ] `generators/ai_generator.py` - Strategy proposals
- [ ] `generators/param_sweeper.py` - Parameter variations

### Week 4: Validation & Orchestration
- [ ] `core/validator.py` - Walk-forward testing
- [ ] `core/ranker.py` - Scoring system
- [ ] `run_pipeline.py` - Main script

### Week 5: Testing & Refinement
- [ ] End-to-end testing
- [ ] Bug fixes
- [ ] Documentation
- [ ] First production run

---

## Success Criteria

1. **Pipeline completes** without manual intervention
2. **Strategies are live-safe** (no look-ahead, realistic costs)
3. **Top strategies** show Sharpe > 1.0 on out-of-sample data
4. **Version control** tracks all strategies and results
5. **Documentation** is complete and accurate

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Overfitting | Walk-forward validation, multiple market regimes |
| API rate limits | Batching, caching, smart prioritization |
| Strategy complexity | KISS constraint (max 3 indicators) |
| Data issues | Warmup periods, data checks, adjusted prices |
| Live vs backtest gap | Safety guards, realistic execution model |

---

## Next Steps

1. Get user approval on this plan
2. Begin implementation (Week 1: Foundation)
3. Update TODOS.md after each work session
4. Document learnings in NOTES.md
