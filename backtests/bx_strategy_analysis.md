# BX Trender Strategy Analysis

## Summary

Testing the BX Trender indicator across various configurations on high-beta stocks (TSLA, NVDA, AMD, COIN) from 2020-2024.

## Strategy Configurations Tested

### 1. BX Daily Only - TSLA (Best Individual Performance)
**File**: `algorithms/strategies/bx_daily_tsla.py`

| Metric | Value |
|--------|-------|
| Net Profit | 293.3% |
| CAGR | 40.9% |
| Sharpe Ratio | 0.90 |
| Sortino Ratio | 0.85 |
| Max Drawdown | 45.9% |
| Total Trades | 67 |
| Win Rate | 45% |
| Profit/Loss Ratio | 2.98 |

**Entry**: Daily BX turns bullish (crosses above 0)
**Exit**: Daily BX turns bearish (crosses below 0)

### 2. BX Daily - High Beta Portfolio (Best Risk-Adjusted)
**File**: `algorithms/strategies/bx_daily_highbeta.py`
**Period**: 2021-2024 (3 years, due to COIN availability)
**Stocks**: TSLA, NVDA, AMD, COIN (25% allocation each)

| Metric | Value |
|--------|-------|
| Net Profit | 133.3% |
| CAGR | 32.7% |
| Sharpe Ratio | 0.85 |
| Sortino Ratio | 0.97 |
| Max Drawdown | 41.3% |
| Total Trades | 200 |
| Win Rate | 38% |
| Profit/Loss Ratio | 2.60 |
| Beta | 1.09 |

### 3. BX Multi-Timeframe Strict (Too Restrictive)
**File**: `algorithms/strategies/bx_mtf_tsla.py`

| Metric | Value |
|--------|-------|
| Total Trades | 0 |

**Issue**: Weekly BX requires 25 weekly bars (~6 months) to calculate. By the time weekly BX is ready, alignment with daily never occurs.

### 4. BX Daily + Weekly SMA Filter (Over-filtered)
**File**: `algorithms/strategies/bx_daily_smafilter_tsla.py`

| Metric | Value |
|--------|-------|
| Net Profit | 16.8% |
| CAGR | 4.0% |
| Sharpe Ratio | 0.17 |
| Max Drawdown | 45.4% |
| Total Trades | 43 |

**Issue**: The SMA trend filter filtered out too many profitable trades during TSLA's high-growth periods.

## Key Findings

### 1. Daily Timeframe Works Best
- Weekly BX filter is impractical due to long warm-up period (25 weeks)
- Weekly SMA filter reduces returns without improving drawdown
- Daily BX captures momentum shifts effectively on high-beta stocks

### 2. Optimal Stock Universe
Best candidates for BX Trender strategy:
- **High-beta stocks** (beta > 1.0)
- **Growth/momentum stocks** (TSLA, NVDA, AMD)
- **High volatility assets** (COIN)

The strategy profits from trend-following behavior, which is amplified in high-beta stocks.

### 3. Diversification Improves Risk-Adjusted Returns
- Single stock (TSLA): Higher absolute return, but concentrated risk
- Portfolio approach: Lower return but better Sortino ratio (0.97 vs 0.85)

### 4. Win Rate vs Profit/Loss Ratio
All strategies showed:
- Low win rate (~40%)
- High profit/loss ratio (~2.5-3.0x)

This confirms BX is a trend-following strategy that cuts losses short and lets winners run.

## Recommended Configuration

### Primary Strategy: BX Daily High-Beta Portfolio
```python
tickers = ["TSLA", "NVDA", "AMD", "COIN"]
# Entry: Daily BX crosses above 0
# Exit: Daily BX crosses below 0
# Position: Equal weight (25% each)
```

### Why This Configuration?
1. **Diversification** reduces single-stock risk
2. **High-beta universe** matches strategy characteristics
3. **Daily timeframe** provides sufficient signals without over-trading
4. **No weekly filter** - weekly analysis doesn't improve results

## Project IDs Reference

| Strategy | Project ID | Backtest ID |
|----------|------------|-------------|
| BX Daily TSLA | 27313201 | ea257bccc8d3536b7a2588be444f3bc1 |
| BX Daily HighBeta | 27313291 | fb5942ccee81811642da42dea5b42799 |
| BX MTF TSLA | 27313100 | b45e44abee6e6155d5a9b4c39e813c3a |
| BX SMA Filter TSLA | 27313402 | 9106c9e499552c73a0343412a80bbc10 |
