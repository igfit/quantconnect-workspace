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

### 3. Weekly BX Filter Analysis (Bug Fixed)

**Original Issue**: The original MTF strategy had 0 trades due to a **buffer size bug**:
- Code used `RollingWindow(25)` for weekly closes
- BX calculation requires: L2 + L3 + 1 = 20 + 15 + 1 = **36 bars minimum**
- With only 25 bars, the weekly BX always returned `None`

**Fixed versions tested:**

| Configuration | Return | Sharpe | Max DD | Trades |
|--------------|--------|--------|--------|--------|
| Weekly BX (5,20,15) fixed | 52.5% | 0.36 | 36.8% | 32 |
| Weekly BX (3,10,8) short | -7.9% | -0.03 | 46.0% | 33 |
| Weekly EMA (5>20) filter | 86.8% | 0.48 | 45.0% | 41 |

**Files**:
- `bx_mtf_debug.py` - Fixed buffer size (36+ bars)
- `bx_mtf_optimized.py` - Shorter weekly params (worse performance)
- `bx_mtf_ema.py` - Simple EMA crossover filter (best of MTF variants)

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

### 1. Weekly BX Bug & Fix
The original MTF implementation had a critical bug:
```python
# BUG: Only stored 25 weekly closes
self.weekly_bars = RollingWindow[TradeBar](25)

# But BX calculation needs:
# - L2 (20) closes to start slow EMA
# - L3+1 (16) more for RSI calculation
# - Total: 36+ closes minimum

# FIX:
min_bars = L2 + L3 + 1  # = 36
self.weekly_bars = RollingWindow[TradeBar](min_bars + 5)
```

### 2. Daily Timeframe Works Best
- Even with the bug fixed, weekly filters hurt TSLA performance
- Weekly BX with standard params: 52.5% return (vs 293% daily-only)
- Shorter weekly params (3,10,8): -7.9% return (too noisy)
- Simple EMA crossover: 86.8% return (best MTF variant, but still worse than daily-only)
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
