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
        # ... setup

    def on_data(self, data):
        # ... trading logic
        pass
```

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

Push to main:
```bash
git remote set-url origin "https://${GITHUB_PERSONAL_ACCESS_TOKEN}@github.com/igfit/quantconnect-workspace.git"
git push origin main
```

## API Reference

### QuantConnect REST API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/authenticate` | GET | Test credentials |
| `/projects/read` | GET | List projects |
| `/projects/create` | POST | Create project |
| `/files/read` | POST | Get project files |
| `/files/update` | POST | Update/create file |
| `/compile/create` | POST | Compile project |
| `/backtests/create` | POST | Start backtest |
| `/backtests/read` | POST | Get backtest results |
| `/live/read` | POST | Get live algo status |

### Rate Limits
- 30 requests/minute
- Batch operations when possible

## Resources

- [QuantConnect Documentation](https://www.quantconnect.com/docs)
- [LEAN Algorithm Framework](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework)
- [API Documentation](https://www.quantconnect.com/docs/v2/cloud-platform/api-reference)
- [LEAN CLI](https://www.quantconnect.com/docs/v2/lean-cli)
