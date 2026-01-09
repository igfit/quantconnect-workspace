# Scalping & Short-Term Systematic Trading Strategies

A systematic framework for developing, backtesting, and deploying short-term trading strategies focused on consistent small profits with controlled drawdowns.

## Goals

- **Consistent profitability**: Small trades that add up over time
- **Controlled drawdowns**: Target 15-25% max drawdown
- **Alpha from timing**: Entry/exit timing, not stock selection
- **No hindsight bias**: Rigorous walk-forward testing

## Strategy Families

| Family | Win Rate | Avg Hold | Alpha Source |
|--------|----------|----------|--------------|
| RSI Mean Reversion | 70-85% | 1-5 days | Oversold bounces |
| Bollinger Band Squeeze | 55-65% | 1-3 days | Volatility expansion |
| Gap Fade | 60-70% | Intraday | Opening gap reversion |
| VWAP Reversion | 65-75% | Intraday | Price-volume dislocation |
| Pairs Trading | 55-65% | 1-10 days | Spread mean reversion |

## Project Structure

```
scalping-strategies/
├── README.md              # This file
├── config.py              # Configuration and constants
├── run_backtest.py        # Main backtest runner
├── models/
│   ├── __init__.py
│   └── strategy_spec.py   # Strategy specification model
├── core/
│   ├── __init__.py
│   ├── compiler.py        # Compiles specs to QC code
│   └── runner.py          # Runs backtests via QC API
├── indicators/
│   ├── __init__.py
│   ├── connors_rsi.py     # Connors RSI implementation
│   ├── percent_rank.py    # Percent rank indicator
│   └── streak_rsi.py      # Streak RSI indicator
├── templates/
│   └── base_algorithm.py  # QC algorithm template
├── strategies/
│   ├── specs/             # Strategy specifications (JSON)
│   └── compiled/          # Generated QC code
├── backtests/
│   └── results/           # Backtest results and analysis
└── docs/
    └── LEARNINGS.md       # Captured learnings
```

## Supported Resolutions

Unlike the daily-only strategy-factory, this framework supports:

| Resolution | Use Case | Slippage Model |
|------------|----------|----------------|
| Minute | Intraday scalping | 0.02% (2 bps) |
| Hour | Swing scalping | 0.05% (5 bps) |
| Daily | Multi-day swings | 0.10% (10 bps) |

## Universe

**Primary (High-Beta)**:
- TSLA, NVDA, AMD

**Secondary (Mega-Cap)**:
- AAPL, MSFT, GOOGL

**Pairs**:
- NVDA/AMD (semiconductors)
- TSLA/RIVN (EVs)

## Backtesting Methodology

### Walk-Forward Analysis

```
Period 1 (Train):    2018-01-01 to 2020-12-31 (3 years)
Period 2 (Test):     2021-01-01 to 2022-12-31 (2 years)
Period 3 (Validate): 2023-01-01 to 2024-12-31 (2 years)
```

### Rules
1. Develop/tune parameters ONLY on Period 1
2. Test on Period 2 - ONE attempt, no re-optimization
3. Final validation on Period 3 - ZERO changes
4. Strategy passes if Sharpe > 0.8 on ALL periods

## Risk Management

| Parameter | Value |
|-----------|-------|
| Starting Capital | $100,000 |
| Risk per Trade | 1% ($1,000) |
| Max Concurrent Positions | 5 |
| Max Daily Loss | 3% ($3,000) |
| Max Drawdown Trigger | 15% → reduce size 50% |
| Max Drawdown Halt | 20% → stop trading |

## Quick Start

```bash
# Run a single strategy backtest
python run_backtest.py --strategy rsi2_pullback --period train

# Run walk-forward analysis
python run_backtest.py --strategy rsi2_pullback --walk-forward

# Compare all strategies
python run_backtest.py --compare-all
```

## Success Criteria

| Metric | Target | Stretch |
|--------|--------|---------|
| Sharpe Ratio | > 0.8 | > 1.2 |
| CAGR | > 15% | > 25% |
| Max Drawdown | < 25% | < 15% |
| Win Rate | > 55% | > 65% |
| Profit Factor | > 1.5 | > 2.0 |

## Academic Foundations

- **RSI(2)**: Larry Connors - "Short-Term Trading Strategies That Work"
- **Connors RSI**: Connors & Alvarez pullback framework
- **Pairs Trading**: Gatev, Goetzmann & Rouwenhorst (2006)
- **Mean Reversion**: Renaissance Technologies "low-hanging fruit"

---

*Last updated: January 2025*
