# Point-in-Time Universe Generation

## The Problem

Universe selection is the #1 source of hindsight bias in backtesting:

1. **Cherry-picking winners**: Selecting stocks you know performed well
2. **Survivorship bias**: Including stocks that IPO'd after backtest start
3. **Knowledge leakage**: Using sector/theme knowledge from the future

## The Solution: Point-in-Time Methodology

### Core Principle

> At time T, we can only use information available at time T.

### Three-Layer Approach

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: QUANTITATIVE SCREEN (Automated)                   │
│  - Historical market cap data                               │
│  - Historical volume data                                   │
│  - Historical beta calculations                             │
│  - IPO date filtering                                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: LLM VALIDATION (Claude Code)                      │
│  - "Would this stock have been selected in Jan 2020?"       │
│  - Flag obscure picks that only became known later          │
│  - Validate against period-appropriate knowledge            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: VERSION CONTROL & AUDIT                           │
│  - Save universe specs with timestamps                      │
│  - Document selection rationale                             │
│  - Enable reproducibility                                   │
└─────────────────────────────────────────────────────────────┘
```

## Implementation

### 1. Quantitative Screen

```python
criteria = UniverseScreenCriteria(
    min_market_cap_millions=5000,    # $5B+ (established)
    min_avg_dollar_volume=10_000_000, # $10M/day (liquid)
    min_price=10,                     # No penny stocks
    min_beta=1.0,                     # High-beta for momentum
    min_years_listed=1,               # Avoid recent IPOs
    exclude_sectors=["Utilities", "Real Estate", "Consumer Staples"],
)
```

### 2. IPO Date Validation

```python
# Filter out stocks that IPO'd after selection date
def was_tradeable_at_date(symbol: str, date: str) -> bool:
    if symbol not in IPO_DATES:
        return True  # Assume established stocks are OK
    return IPO_DATES[symbol] < date
```

### 3. LLM Validation Prompt

```
You are validating a stock universe for hindsight bias.

SELECTION DATE: 2020-01-01
UNIVERSE: [list of stocks]

For each stock, verify:
1. Was it publicly traded as of the selection date?
2. Was it a reasonably well-known stock at that time?
3. Would a systematic screen have included it?

FLAG any stocks that seem cherry-picked based on hindsight.
```

## Results: Impact of Hindsight Bias

| Universe Type | CAGR | Sharpe | Hindsight Score |
|---------------|------|--------|-----------------|
| Hand-picked (biased) | 30.4% | 0.91 | HIGH |
| Point-in-time (clean) | 19.4% | 0.62 | 0% |

**The biased universe inflated returns by 57%.**

## Usage

```python
from universe_generator import (
    generate_universe,
    UniverseType,
    UniverseScreenCriteria,
    validate_universe_for_hindsight_bias,
)

# Generate point-in-time universe
universe = generate_universe(
    selection_date="2020-01-01",
    universe_type=UniverseType.HIGH_BETA_LIQUID,
    criteria=UniverseScreenCriteria(min_market_cap_millions=5000),
)

# Validate for bias
validation = validate_universe_for_hindsight_bias(universe)
print(f"Hindsight bias score: {validation['hindsight_bias_score']:.2%}")
```

## Key Takeaways

1. **Always document selection date** - "As of when was this universe created?"
2. **Check IPO dates** - Remove stocks that IPO'd after selection date
3. **Use LLM for sanity check** - "Would I have known about this stock in 2020?"
4. **Version control universes** - Save specs for reproducibility
5. **Report both results** - Show biased vs. unbiased performance

## Files

- `universe_generator.py` - Main generation logic
- `specs/` - Saved universe specifications (JSON)
- `data/` - Historical IPO dates, index constituents
