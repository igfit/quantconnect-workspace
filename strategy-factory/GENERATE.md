# Strategy Generation Protocol

This document describes how Claude Code should generate trading strategies.

---

## The Golden Rule

**Claude Code thinks, then designs, then documents.**

Not: "Here's a template"
But: "Here's WHY this strategy might work, and here's how to capture that edge"

---

## Phase 0: Meta-Reasoning

Before generating ANY strategies, Claude Code must first decide what to explore.

### Step 1: Survey Existing Work

```bash
# Check existing strategies
ls strategy-factory/strategies/specs/

# Check past results
cat strategy-factory/results/summary.csv

# Check accumulated learnings
cat strategy-factory/NOTES.md
```

Ask yourself:
- What strategies have we already tried?
- What performed well? What performed poorly?
- What patterns emerge from the results?

### Step 2: Identify Gaps and Opportunities

Consider:
- **Underexplored strategy types**: Have we tested mean reversion? Sector rotation? Breakouts?
- **Underexplored universes**: Only tested tech? Try financials, healthcare, ETFs?
- **Underexplored indicators**: Only used SMA? Try EMA, RSI, ADX?
- **What worked**: If momentum worked, try variations (different periods, different stocks)
- **What failed**: Why did it fail? Can we fix it or should we avoid that direction?

### Step 3: Form a Thesis

Before designing strategies, articulate:

```
I will explore [STRATEGY TYPE] because:
1. [EDGE]: What market inefficiency does this exploit?
2. [WHY]: Why does this inefficiency exist? (behavioral, structural, informational)
3. [WHY NOT ARBITRAGED]: Why hasn't it been eliminated?
4. [UNIVERSE FIT]: Which stocks best match this thesis?
```

Example:
```
I will explore RSI oversold bounces on large-cap stocks because:
1. EDGE: Oversold conditions often precede reversals
2. WHY: Fear-driven selling overshoots fair value; retail panic-sells
3. WHY NOT ARBITRAGED: Behavioral biases persist; timing is hard
4. UNIVERSE FIT: Large caps mean-revert faster (institutional buying)
```

### Step 4: Document the Decision

Add to `NOTES.md`:

```markdown
## Generation Round [N] - [Date]

### Thesis
[What you decided to explore and why]

### Based On
- Previous results showing X
- Gap identified: Y
- Hypothesis: Z
```

---

## Phase 1: Strategy Design

Now design 5-10 strategies within your chosen direction.

### For Each Strategy

#### 1. Name and Description
- Clear, descriptive name
- One-sentence description of what it does

#### 2. Rationale (THE WHY)
This is the most important part. Explain:
- What edge are you capturing?
- Why would this work?
- What behavioral or structural factor creates the opportunity?

**Bad rationale**: "Buy when RSI < 30"
**Good rationale**: "RSI < 30 indicates oversold conditions where fear-driven selling has pushed price below fair value. Combined with an uptrend filter (price > 200 SMA), we avoid falling knives and catch quality dips that tend to revert as institutional buyers step in."

#### 3. Universe Selection
Choose stocks that FIT the thesis:
- Momentum strategies → high-beta, growth stocks
- Mean reversion → liquid, range-bound stocks
- Trend following → stocks with clear trends
- Sector rotation → sector ETFs

#### 4. Indicators (Max 3)
Only include indicators you actually USE in conditions.
Keep it simple - more indicators = more overfitting risk.

#### 5. Entry Conditions (Max 2)
Clear, unambiguous rules for when to buy.

#### 6. Exit Conditions (Max 2)
Clear, unambiguous rules for when to sell.

#### 7. Risk Management
- Position size (fixed dollars)
- Stop loss (optional)
- Max holding period (optional)

---

## Strategy Spec Format

Output each strategy as a JSON file in `strategy-factory/strategies/specs/`:

```json
{
  "id": "[8-char-hex]",
  "name": "Strategy Name",
  "description": "One-sentence description",
  "rationale": "WHY this works - the edge being exploited. Be specific about behavioral/structural factors.",

  "universe": {
    "type": "static",
    "symbols": ["AAPL", "MSFT", "GOOGL"]
  },

  "timeframe": "daily",

  "indicators": [
    {
      "name": "indicator_name",
      "type": "SMA|EMA|RSI|ADX|ROC|ATR",
      "params": {"period": 20}
    }
  ],

  "entry_conditions": {
    "logic": "AND|OR",
    "conditions": [
      {
        "left": "indicator_name|price",
        "operator": "greater_than|less_than|crosses_above|crosses_below",
        "right": "indicator_name|number"
      }
    ]
  },

  "exit_conditions": {
    "logic": "AND|OR",
    "conditions": [
      {
        "left": "indicator_name|price",
        "operator": "greater_than|less_than|crosses_above|crosses_below",
        "right": "indicator_name|number"
      }
    ]
  },

  "risk_management": {
    "position_size_dollars": 10000,
    "stop_loss_pct": 0.08,
    "max_holding_days": null
  },

  "parameters": [
    {
      "path": "indicators.0.params.period",
      "values": [10, 20, 30]
    }
  ]
}
```

---

## Supported Indicators

| Type | Description | Params |
|------|-------------|--------|
| SMA | Simple Moving Average | period |
| EMA | Exponential Moving Average | period |
| RSI | Relative Strength Index | period |
| ADX | Average Directional Index | period |
| ROC | Rate of Change | period |
| ATR | Average True Range | period |

---

## Supported Operators

| Operator | Description |
|----------|-------------|
| `greater_than` | Left > Right |
| `less_than` | Left < Right |
| `crosses_above` | Left crosses above Right (was below, now above) |
| `crosses_below` | Left crosses below Right (was above, now below) |

---

## Common Universes

| Name | Symbols | Best For |
|------|---------|----------|
| High-Beta Tech | TSLA, NVDA, AMD, COIN, SQ, SHOP | Momentum, trend following |
| Large Cap Tech | AAPL, MSFT, GOOGL, AMZN, META | Mean reversion, quality dips |
| Broad Market | SPY, QQQ, IWM | Sector rotation, macro trends |
| Sector ETFs | XLK, XLF, XLE, XLV | Sector rotation |

---

## Benchmarks to Beat

| Benchmark | CAGR | Sharpe | Max DD |
|-----------|------|--------|--------|
| Buy & Hold SPY/QQQ | 17.07% | 0.57 | 30.2% |
| Monthly DCA SPY/QQQ | 7.45% | 0.37 | 13.4% |

**Target**: Sharpe > 0.8, CAGR > 15%, Max DD < 25%

---

## Anti-Patterns (What NOT to Do)

### Don't: Use indicators you don't understand
If you can't explain WHY the indicator would help, don't use it.

### Don't: Over-complicate
3 indicators max. 2 conditions max. Simple > complex.

### Don't: Skip the rationale
Every strategy needs a clear WHY. "It backtests well" is not a rationale.

### Don't: Ignore universe fit
A momentum strategy on low-beta stocks won't work. Match universe to thesis.

### Don't: Copy without thinking
Don't just tweak parameters on existing strategies. Think about what edge you're capturing.

---

## Example: Good Strategy Generation

```
THESIS: I'll explore momentum on high-beta tech stocks because:
- Momentum persists due to institutional flows and herding behavior
- High-beta stocks amplify this effect
- Works best in trending markets (which we've been in)

STRATEGY 1: Dual EMA Momentum
- Rationale: EMA crossovers capture trend changes. Fast EMA (12) reacts to
  recent price action, slow EMA (26) filters noise. Crossover signals trend
  shift. Works on volatile stocks that trend well.
- Universe: TSLA, NVDA, AMD (high beta, strong trends)
- Entry: Fast EMA crosses above Slow EMA
- Exit: Fast EMA crosses below Slow EMA
- Risk: $10k per position, 10% stop loss

STRATEGY 2: Price Breakout
- Rationale: New highs indicate strong momentum. Stocks making new highs
  often continue higher as breakout buyers pile in. Using SMA as dynamic
  support for exits.
- Universe: AAPL, MSFT, GOOGL (liquid, trend well)
- Entry: Price crosses above 20-day SMA
- Exit: Price crosses below 20-day SMA
- Risk: $10k per position, 8% stop loss

[Continue for 3-5 more strategies...]
```

---

## After Generating

1. Save specs to `strategy-factory/strategies/specs/`
2. Run infrastructure: `python strategy-factory/run_pipeline.py`
3. Analyze results (see Phase 6 in PRD.md)
4. Update NOTES.md with learnings
5. Iterate
