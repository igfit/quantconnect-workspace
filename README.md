# QuantConnect Workspace

Algorithmic trading development workspace for QuantConnect.

## Quick Start

1. **Set environment variables:**
   ```bash
   export QC_USER_ID="your-user-id"
   export QC_API_TOKEN="your-api-token"
   ```

2. **Test authentication:**
   ```bash
   ./scripts/qc-api.sh auth
   ```

3. **List your projects:**
   ```bash
   ./scripts/qc-api.sh projects
   ```

4. **Push an algorithm:**
   ```bash
   ./scripts/qc-api.sh push <projectId> algorithms/examples/momentum_strategy.py main.py
   ```

5. **Run backtest:**
   ```bash
   ./scripts/qc-api.sh backtest <projectId> "My Test"
   ```

## Structure

```
algorithms/        # Trading algorithm source code
  examples/        # Reference implementations
  strategies/      # Your custom strategies
scripts/           # Helper scripts
backtests/         # Results and analysis
```

## Resources

- [QuantConnect Docs](https://www.quantconnect.com/docs)
- [LEAN Framework](https://www.quantconnect.com/docs/v2/writing-algorithms)
- [API Reference](https://www.quantconnect.com/docs/v2/cloud-platform/api-reference)

## Development with Claude Code

This repo includes `CLAUDE.md` with instructions for AI-assisted algorithm development. Open in Claude Code for the best experience.
