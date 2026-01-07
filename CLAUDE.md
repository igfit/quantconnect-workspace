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
scripts/              # Helper scripts (qc-api.sh)
backtests/            # Backtest results and analysis
.claude/commands/     # Custom slash commands
```

### Existing Strategies

| Strategy | File | Description |
|----------|------|-------------|
| Momentum | `algorithms/examples/momentum_strategy.py` | Top N momentum stocks, monthly rebalance |
| MA Crossover | `algorithms/strategies/ma_crossover.py` | 50/200 SMA crossover on SPY, QQQ, AAPL, MSFT, GOOGL |
| Buy & Hold Benchmark | `algorithms/strategies/benchmark_buyhold.py` | Simple buy-and-hold for benchmarking |

### QC Project IDs

| Project | ID | Description |
|---------|-----|-------------|
| MA Crossover Strategy | 27311581 | 50/200 SMA crossover |
| Benchmark SPY Buy-Hold | 27311779 | SPY buy-and-hold benchmark |
| Benchmark QQQ Buy-Hold | 27311785 | QQQ buy-and-hold benchmark |

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

## Resources

- [QuantConnect Documentation](https://www.quantconnect.com/docs)
- [LEAN Algorithm Framework](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework)
- [API Documentation](https://www.quantconnect.com/docs/v2/cloud-platform/api-reference)
- [LEAN CLI](https://www.quantconnect.com/docs/v2/lean-cli)
