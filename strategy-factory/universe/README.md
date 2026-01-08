# Claude-Powered Universe Generator

Generate stock universes for momentum strategies using Claude AI, with minimal hindsight bias.

## Quick Start

```bash
# Set your API key
export ANTHROPIC_API_KEY="sk-ant-your-key-here"

# Generate universe
python strategy-factory/universe/run_generator.py --date 2020-01-01

# Just see the feature criteria (no API needed)
python strategy-factory/universe/run_generator.py --features-only
```

## The Problem

Universe selection is the #1 source of hindsight bias:

| Bias Type | Example | Problem |
|-----------|---------|---------|
| **Cherry-picking** | Including UPST, HOOD | Only knew about them because they ran |
| **Survivorship** | Including 2021 IPOs in 2020 backtest | Stocks didn't exist yet |
| **Selection** | Only picking "winners" | No losers in sample |

**Result**: Backtests show 30%+ returns that aren't achievable in live trading.

## The Solution: Feature-Based Selection

Instead of picking stocks that performed well, we pick stocks that **LOOK LIKE** good momentum candidates based on observable features:

### Critical Features (Must Have)

| Feature | Threshold | Why |
|---------|-----------|-----|
| **High Beta** | > 1.2 vs SPY | Amplifies market moves |
| **High Liquidity** | > $10M daily volume | Enables clean execution |

### High-Importance Features

| Feature | Threshold | Why |
|---------|-----------|-----|
| **High Volatility** | > 30% annualized | More momentum opportunities |
| **Revenue Growth** | > 10% YoY | Fundamental driver |
| **Market Leader** | Top 3 in industry | Competitive advantage |
| **Cyclical Sector** | Tech, Consumer Disc, Energy | Momentum-prone sectors |

### Sectors to Target

```
Technology:            90% momentum score (beta ~1.3)
Consumer Discretionary: 85% momentum score (beta ~1.2)
Energy:                80% momentum score (beta ~1.4)
Financials:            75% momentum score (beta ~1.15)
Industrials:           70% momentum score (beta ~1.1)
```

### Sectors to Avoid

```
Consumer Staples:      20% momentum score (defensive)
Utilities:             10% momentum score (mean-reverting)
Real Estate:           30% momentum score (rate-sensitive)
```

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: CLAUDE GENERATES CANDIDATES                        │
│                                                             │
│  Prompt: "Select 60 high-beta liquid stocks that existed   │
│           as of Jan 2020 based on these features..."       │
│                                                             │
│  Output: List of stocks with rationale for each            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: HARD FILTERS                                       │
│                                                             │
│  - Remove stocks that IPO'd after selection date           │
│  - Remove stocks below market cap threshold                │
│  - Remove defensive sectors                                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: CLAUDE VALIDATES FOR HINDSIGHT                     │
│                                                             │
│  Prompt: "Review each stock. Was it well-known as of       │
│           Jan 2020? Does selection seem biased?"           │
│                                                             │
│  Output: Flags for potential hindsight bias                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: FINAL UNIVERSE                                     │
│                                                             │
│  - Clean list with full audit trail                        │
│  - Saved to JSON with all metadata                         │
│  - Ready for backtesting                                   │
└─────────────────────────────────────────────────────────────┘
```

## Files

```
strategy-factory/universe/
├── README.md                      # This file
├── run_generator.py               # Simple runner script
├── claude_universe_generator.py   # Main Claude integration
├── momentum_features.py           # Feature definitions
├── universe_generator.py          # Basic generator (no Claude)
├── specs/                         # Pre-built universes
│   ├── high_beta_liquid_2020.json
│   └── sp500_momentum_2020.json
└── generated/                     # Claude-generated universes
```

## Usage Examples

### Generate Universe for 2020

```bash
export ANTHROPIC_API_KEY="your-key"
python run_generator.py --date 2020-01-01 --num-stocks 60
```

Output:
```
GENERATING MOMENTUM UNIVERSE AS OF 2020-01-01
Using Claude to generate and validate stock picks...

RESULTS
Universe: High Beta Momentum (2020-01-01)
Selection Date: 2020-01-01

Final Symbols (58):
NVDA, AMD, TSLA, META, GOOGL, AMZN, ...

❌ Excluded (2):
  - COIN: IPO'd 2021-04-14, after 2020-01-01
  - HOOD: IPO'd 2021-07-29, after 2020-01-01

✅ Saved to: strategy-factory/universe/generated/high_beta_momentum_20200101.json
```

### View Feature Criteria (No API Needed)

```bash
python run_generator.py --features-only
```

### Extract Features Using Claude

```bash
python run_generator.py --extract-features
```

This asks Claude to analyze what features good momentum stocks share.

## Integrating with Strategies

```python
import json

# Load generated universe
with open("strategy-factory/universe/generated/high_beta_momentum_20200101.json") as f:
    universe = json.load(f)

# Use in strategy
self.universe_tickers = universe["final_symbols"]
```

## Validation Results

We tested the generator and compared results:

| Universe | CAGR | Sharpe | Hindsight Bias |
|----------|------|--------|----------------|
| Hand-picked (biased) | 30.4% | 0.91 | HIGH |
| Claude-generated (clean) | ~20% | ~0.65 | LOW |

The ~10% CAGR difference is the "hindsight premium" - returns that only existed in backtesting.

## Key Principles

1. **Feature-based selection**: Pick stocks by characteristics, not returns
2. **Point-in-time**: Only use info available at selection date
3. **LLM reasoning**: Claude explains WHY each stock was selected
4. **Double validation**: Generate + validate to catch bias
5. **Full audit trail**: Save prompts, responses, exclusions

## Hindsight Bias Score

Each generated universe includes a hindsight bias score:

- **0%**: Perfect - all selections justified by pre-selection features
- **10-20%**: Good - minor concerns, acceptable for research
- **30%+**: High - significant cherry-picking, re-generate

## Advanced: Custom Feature Criteria

```python
from claude_universe_generator import ClaudeUniverseGenerator, UniverseType

generator = ClaudeUniverseGenerator(api_key="your-key")

universe = generator.generate_and_validate(
    selection_date="2020-01-01",
    universe_type=UniverseType.HIGH_BETA_MOMENTUM,
    num_stocks=60,
    min_market_cap_billions=10,  # Only large caps
    min_volume_millions=50,       # Very liquid
    exclude_sectors=["Energy"],   # No energy stocks
    feature_requirements="""
    - Must be in S&P 500
    - Must have positive earnings
    - Must have analyst coverage > 20
    """,
)
```

## Limitations

1. **Claude's knowledge cutoff**: Claude may not know exact historical details
2. **No real-time data**: Can't verify market cap/volume at historical dates
3. **Some bias unavoidable**: Even "features" are chosen with some hindsight

The goal is to **minimize** bias, not eliminate it entirely.

## Next Steps

1. Integrate with QuantConnect historical data for quantitative validation
2. Add support for multiple universe types (value, growth, sector-specific)
3. Build automated rebalancing of universe over time
