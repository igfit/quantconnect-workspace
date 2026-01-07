# CLAUDE.md

This repository is a QuantConnect algorithmic trading development workspace. Claude Code assists with writing, testing, and deploying trading algorithms.

## Setup

### Required Environment Variables

```bash
# Add to ~/.bashrc or ~/.zshrc
export QC_USER_ID="your-user-id"         # From quantconnect.com/account
export QC_API_TOKEN="your-api-token"     # From quantconnect.com/account

# For GitHub operations (Claude Code web)
export GITHUB_PERSONAL_ACCESS_TOKEN="your-pat"
```

### Local Development (Optional)

For faster local backtesting, install LEAN CLI:
```bash
pip install lean
lean init
```

## Repository Structure

```
algorithms/           # Trading algorithm source code
  examples/           # Reference implementations
  strategies/         # Your custom strategies
strategy-factory/     # AI + Programmatic strategy generation system
  PRD.md              # Product requirements (read first)
  PLAN.md             # Technical implementation plan
  TODOS.md            # Progress tracker
  NOTES.md            # Implementation learnings
  strategies/         # Generated strategies (version controlled)
scripts/              # Helper scripts (qc-api.sh)
tools/                # CLI tools (context7)
backtests/            # Backtest results and analysis
docs/                 # Documentation and learnings
  LEARNINGS.md        # Comprehensive strategy & platform learnings
.claude/commands/     # Custom slash commands
```

### Key Documentation

**READ FIRST**: `docs/LEARNINGS.md` contains critical knowledge about:
- QuantConnect API gotchas and authentication
- BX Trender indicator implementation (including buffer size bug fix)
- **Wave-EWO strategy** (best performer: 858% return, 1.50 Sharpe on TSLA)
- High-beta stock testing results (AMD, COIN, META, MSTR, SMCI)
- Complete performance comparison (active vs passive strategies)
- Multi-timeframe analysis findings
- Common pitfalls with code examples
- Strategy development best practices

## Strategy Factory

An **AI + Programmatic** strategy generation and backtesting system.

**Read `strategy-factory/PRD.md` for full product requirements.**

### Key Principle: Claude IS the Strategy Generator

**Claude generates strategies through reasoning, not templates.**

When asked to generate strategies, Claude must:
1. **Research**: What market inefficiency exists?
2. **First Principles**: WHY would this work? What creates the edge?
3. **Design**: Choose indicators & universe that match the thesis
4. **KISS**: Keep it simple (max 3 indicators, clear logic)

The infrastructure (compiler, runner, parser) handles execution automatically.

### Quick Reference

| File | Purpose |
|------|---------|
| `strategy-factory/PRD.md` | **Product requirements (read first)** |
| `strategy-factory/PLAN.md` | Technical implementation plan |
| `strategy-factory/TODOS.md` | Progress tracker |
| `strategy-factory/NOTES.md` | Learnings during implementation |

### Architecture Overview

```
Claude (AI)  → Compiler → QC Runner → Parser → Validator → Ranker
    ↓             ↓           ↓          ↓          ↓         ↓
Reasoning    QC Code    Backtests   Metrics   Validated   Top 5
 + Specs
```

### Strategy Generation Process

1. **Claude proposes** strategies with clear rationale (the WHY)
2. **Infrastructure compiles** spec → QuantConnect code
3. **Infrastructure backtests** via QC cloud API
4. **Infrastructure parses** results (Sharpe, CAGR, drawdown)
5. **Claude reviews** results and proposes refinements
6. **Iterate** until strategies beat benchmarks

### Key Constraints

- **Long-only** (initial phase)
- **Daily or slower** timeframe
- **KISS**: Max 3 indicators, max 2 entry/exit conditions
- **Fixed dollar** position sizing
- **IBKR** as target broker

### Safety Guards (Every Strategy)

1. Trade on next-day open (no look-ahead)
2. 0.1% slippage model
3. IBKR commission model
4. Min $5 price, 500k daily dollar volume
5. Indicator warmup period
6. Data existence checks

### Benchmarks to Beat

| Benchmark | CAGR | Sharpe | Max DD |
|-----------|------|--------|--------|
| Buy & Hold SPY/QQQ | 17.07% | 0.57 | 30.2% |
| Monthly DCA SPY/QQQ | 7.45% | 0.37 | 13.4% |

**Target**: Sharpe > 0.8, CAGR > 15%, Max DD < 25%

### Running the Pipeline

```bash
# Full pipeline
python strategy-factory/run_pipeline.py --date-range 5_year

# Options
--date-range   5_year | 10_year
--batch-size   Number of strategies to generate (default: 15)
--skip-sweep   Skip parameter sweep phase
```

### Strategy Version Control

All strategies are saved and git-tracked:
- Specs: `strategy-factory/strategies/specs/{id}.json`
- Code: `strategy-factory/strategies/compiled/{id}.py`
- Registry: `strategy-factory/strategies/registry.json`

## Knowledge Capture Workflow

**IMPORTANT**: As you develop strategies, continuously update `docs/LEARNINGS.md` with new insights.

### When to Update LEARNINGS.md

1. **Bug discoveries** - Document the bug, why it happened, and the fix
2. **API gotchas** - Any QuantConnect quirks or unexpected behavior
3. **Performance findings** - Strategy results that inform future development
4. **Code patterns** - Reusable patterns that work well (or don't)
5. **Parameter insights** - What parameter ranges work for different scenarios

### How to Update

```markdown
# In docs/LEARNINGS.md, add to the appropriate section:

## [Section Name]

### [New Finding Title]

**Problem**: [What went wrong or was discovered]

**Solution**: [How to fix or handle it]

```python
# Code example if applicable
```

**Result**: [Outcome or performance impact]
```

### Update Checklist

Before finishing a session that involved strategy development:

- [ ] Did you encounter any bugs? → Add to "Common Pitfalls"
- [ ] Did you learn something about QuantConnect API? → Add to "QuantConnect Platform"
- [ ] Did you test a new indicator or strategy? → Add results to relevant section
- [ ] Did you find optimal parameters? → Document in strategy-specific section
- [ ] Did you discover a useful code pattern? → Add to "Best Practices"

### Example Updates

**After finding a bug:**
```markdown
### 6. Consolidator Calendar Type
```python
# WRONG
self.consolidate(symbol, CalendarType.WEEK, handler)

# RIGHT
self.consolidate(symbol, Calendar.Weekly, handler)
```
```

**After testing a strategy:**
```markdown
### BX on Crypto Assets

Tested BX Trender on BTC/ETH (2021-2024):
| Asset | Return | Sharpe | Notes |
|-------|--------|--------|-------|
| BTC   | 45%    | 0.65   | Works in trending periods |
| ETH   | 38%    | 0.55   | Higher volatility hurts |

**Conclusion**: BX works but needs volatility adjustment for crypto.
```

### Existing Strategies

| Strategy | File | Description |
|----------|------|-------------|
| Momentum | `algorithms/examples/momentum_strategy.py` | Top N momentum stocks, monthly rebalance |
| MA Crossover | `algorithms/strategies/ma_crossover.py` | 50/200 SMA crossover on SPY, QQQ, AAPL, MSFT, GOOGL |
| Buy & Hold Benchmark | `algorithms/strategies/benchmark_buyhold.py` | Simple buy-and-hold for benchmarking |
| **BX Daily TSLA** | `algorithms/strategies/bx_daily_tsla.py` | BX Trender on TSLA (293% return, 0.90 Sharpe) |
| **BX Daily HighBeta** | `algorithms/strategies/bx_daily_highbeta.py` | BX on TSLA/NVDA/AMD/COIN portfolio |
| BX MTF Debug | `algorithms/strategies/bx_mtf_debug.py` | Multi-timeframe BX with fixed buffer |
| BX MTF EMA | `algorithms/strategies/bx_mtf_ema.py` | BX with weekly EMA crossover filter |
| **Wave-EWO TSLA** | `algorithms/strategies/wave_ewo.py` | **Best performer**: 858% return, 1.50 Sharpe |
| Wave-EWO AMD | `algorithms/strategies/wave_ewo_amd.py` | 145% return, 0.67 Sharpe |
| Wave-EWO META | `algorithms/strategies/wave_ewo_meta.py` | 139% return, 0.72 Sharpe |
| Wave-EWO MSTR | `algorithms/strategies/wave_ewo_mstr.py` | 365% return, 0.91 Sharpe (high DD) |
| Wave-EWO SMCI | `algorithms/strategies/wave_ewo_smci.py` | 159% return, 0.65 Sharpe |
| Wave-EWO COIN | `algorithms/strategies/wave_ewo_coin.py` | 41% return (avoid - crypto correlation) |
| Beta Screener | `algorithms/strategies/beta_screener.py` | Screens for high-beta stocks (beta > 1.5) |
| DCA Strategies | `algorithms/strategies/dca_*.py` | Monthly DCA for TSLA, SPY, QQQ |
| Benchmarks | `algorithms/strategies/benchmark_*_bh.py` | SPY/QQQ buy-hold benchmarks |

### QC Project IDs

| Project | ID | Description |
|---------|-----|-------------|
| MA Crossover Strategy | 27311581 | 50/200 SMA crossover |
| Benchmark SPY Buy-Hold | 27311779 | SPY buy-and-hold benchmark |
| Benchmark QQQ Buy-Hold | 27311785 | QQQ buy-and-hold benchmark |
| Wave-EWO AMD | 27315748 | Wave-EWO on AMD (145% return) |
| Wave-EWO COIN | 27315752 | Wave-EWO on COIN (41% return) |
| Wave-EWO META | 27315754 | Wave-EWO on META (139% return) |
| Wave-EWO MSTR | 27315755 | Wave-EWO on MSTR (365% return) |
| Wave-EWO SMCI | 27315756 | Wave-EWO on SMCI (159% return) |
| Beta Screener | 27315463 | High-beta stock screener utility |
| Benchmark Buy-Hold SPY/QQQ | 27316754 | 50/50 buy-hold (17.07% CAGR, 0.57 Sharpe) |
| Benchmark DCA SPY/QQQ | 27316758 | Monthly DCA $1667 (7.45% CAGR, 0.37 Sharpe) |

## QuantConnect API Workflow

### Authentication Test
```bash
./scripts/qc-api.sh auth
```

### Development Loop

1. **Write algorithm** in `algorithms/` directory
2. **Push to QC**: `./scripts/qc-api.sh push <projectId> <filename>`
3. **Run backtest**: `./scripts/qc-api.sh backtest <projectId> "test-name"`
4. **Get results**: `./scripts/qc-api.sh results <projectId> <backtestId>`

### Full Deployment Example

```bash
# 1. Create project (returns projectId)
./scripts/qc-api.sh project-create "My Strategy" Py

# 2. Upload algorithm as main.py
./scripts/qc-api.sh push 27311581 algorithms/strategies/ma_crossover.py main.py

# 3. Compile (returns compileId)
./scripts/qc-api.sh compile 27311581

# 4. Run backtest with compileId
./scripts/qc-api.sh backtest 27311581 "Test Run" "compile-id-here"

# 5. Get results (wait ~15-30s for completion)
./scripts/qc-api.sh results 27311581 "backtest-id-here"

# 6. Parse key metrics
./scripts/qc-api.sh results 27311581 "backtest-id" | jq '.backtest.statistics'
```

### Common Commands

| Command | Description |
|---------|-------------|
| `./scripts/qc-api.sh auth` | Test API authentication |
| `./scripts/qc-api.sh projects` | List all projects |
| `./scripts/qc-api.sh files <projectId>` | List files in project |
| `./scripts/qc-api.sh push <projectId> <file>` | Upload algorithm file |
| `./scripts/qc-api.sh compile <projectId>` | Compile project |
| `./scripts/qc-api.sh backtest <projectId> <name>` | Run backtest |
| `./scripts/qc-api.sh results <projectId> <backtestId>` | Get backtest results |
| `./scripts/qc-api.sh live-list` | List live deployments |

## Algorithm Conventions

### File Naming
- Main algorithm: `main.py`
- Supporting modules: `alpha.py`, `risk.py`, `execution.py`
- Use snake_case for files

### Code Style
- Follow PEP 8
- Document strategy logic with docstrings
- Include parameter descriptions in class docstring

### Standard Algorithm Template
```python
from AlgorithmImports import *

class MyStrategy(QCAlgorithm):
    """
    Strategy: [Brief description]

    Parameters:
        - param1: [description]
        - param2: [description]

    Universe: [What assets]
    Rebalance: [Frequency]
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        # Add equities
        self.add_equity("SPY", Resolution.DAILY)

        # Set benchmark for performance comparison
        self.set_benchmark("SPY")

    def on_data(self, data):
        # ... trading logic
        pass
```

### Benchmarking

Always add a benchmark to strategies for performance comparison:
```python
# In initialize(), after adding the benchmark security:
self.set_benchmark("SPY")
```

This enables:
- Benchmark chart overlay in backtest results
- Alpha/Beta calculations relative to benchmark
- Proper risk-adjusted performance metrics

## Backtest Documentation

When running backtests, document results in `backtests/results.md`:

```markdown
## [Strategy Name] - [Date]

**Parameters**: ...
**Period**: YYYY-MM-DD to YYYY-MM-DD
**Initial Capital**: $X

### Results
- Sharpe Ratio: X.XX
- Total Return: XX.X%
- Max Drawdown: XX.X%
- Win Rate: XX.X%

### Notes
[Observations and next steps]
```

## Git Workflow

**CRITICAL: Author commits only as IG Fit:**
```bash
git config user.name "IG Fit"
git config user.email "ig.fitbody@gmail.com"
```

**Never include co-authorship or Claude attribution in commits.**

**ALWAYS push to main using the GitHub token:**
```bash
git remote set-url origin "https://${GITHUB_PERSONAL_ACCESS_TOKEN}@github.com/igfit/quantconnect-workspace.git"
git push origin main
```

Note: Direct push without the token will fail with 403. Always set the remote URL with the token first.

## API Reference

### Authentication

The QC API uses **SHA-256 timestamped authentication** (not simple basic auth):

1. Combine `{API_TOKEN}:{unix_timestamp}`
2. SHA-256 hash → hex digest
3. Base64 encode `{USER_ID}:{hash}`
4. Send as `Authorization: Basic {encoded}` header with `Timestamp: {unix_timestamp}` header

The `qc-api.sh` script handles this automatically.

### QuantConnect REST API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/authenticate` | GET | Test credentials |
| `/projects/read` | GET | List projects |
| `/projects/create` | POST | Create project (language: "Py" or "C#") |
| `/files/read` | POST | Get project files |
| `/files/update` | POST | Update/create file |
| `/compile/create` | POST | Compile project |
| `/backtests/create` | POST | Start backtest (uses `backtestName` param) |
| `/backtests/read` | POST | Get backtest results |
| `/live/read` | POST | Get live algo status |

### API Gotchas

- **Project language**: Use `"Py"` not `"Python"` when creating projects
- **Backtest name**: API parameter is `backtestName`, not `name`
- **Compile first**: Get `compileId` from compile before running backtest

### Rate Limits
- 30 requests/minute
- Batch operations when possible

## Context7 Documentation Lookup

Use the `context7` CLI tool to fetch up-to-date documentation for any library or framework. This is especially useful for QuantConnect APIs, Python libraries, and trading frameworks.

### Usage

```bash
# 1. Find a library's Context7 ID
./tools/context7 resolve "quantconnect"
./tools/context7 resolve "pandas"

# 2. Fetch documentation (use ID from resolve)
./tools/context7 docs "/QuantConnect/Lean" --topic "indicators"
./tools/context7 docs "/pandas-dev/pandas" --topic "dataframe"

# 3. Get library metadata
./tools/context7 info "/QuantConnect/Lean"
```

### Common Library IDs

| Library | Context7 ID | Use For |
|---------|-------------|---------|
| QuantConnect LEAN | `/QuantConnect/Lean` | Algorithm framework, indicators, universe selection |
| Pandas | `/pandas-dev/pandas` | Data manipulation, dataframes |
| NumPy | `/numpy/numpy` | Numerical computing |

### When to Use Context7

- **Before writing algorithms**: Look up QuantConnect API for indicators, universe filters, etc.
- **Debugging errors**: Get current documentation for correct method signatures
- **Learning new features**: Explore available functionality with `--topic` filtering

### Options

| Option | Description |
|--------|-------------|
| `--topic`, `-t` | Focus documentation on specific topic |
| `--tokens`, `-n` | Max tokens to return (default: 10000) |
| `--json` | Output raw JSON |

### Environment Variables

```bash
# Optional: For higher rate limits
export CONTEXT7_API_KEY="your-api-key"
```

## Resources

- [QuantConnect Documentation](https://www.quantconnect.com/docs)
- [LEAN Algorithm Framework](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework)
- [API Documentation](https://www.quantconnect.com/docs/v2/cloud-platform/api-reference)
- [LEAN CLI](https://www.quantconnect.com/docs/v2/lean-cli)
- [Context7](https://context7.com) - Documentation lookup service
