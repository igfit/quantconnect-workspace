# Clenow High-Beta Systematic Strategy Optimization

## Executive Summary

Tested the Clenow momentum strategy with systematic high-beta universe to find optimal balance between concentration (high returns) and diversification (lower drawdown).

**Key Finding**: 30% CAGR with <30% MaxDD is NOT achievable with 5 positions without leverage. There is a fundamental concentration vs diversification tradeoff.

## Best Results

| Configuration | CAGR | Max DD | Sharpe | Positions | Notes |
|--------------|------|--------|--------|-----------|-------|
| **Concentrated (TOP_N=1)** | 35.7% | 47.1% | 0.80 | 1 | Highest returns, highest risk |
| **Best Diversified (v6)** | 22.6% | 41.3% | 0.65 | 5 | Best for 5 positions |
| **Lowest DD (TOP_N=10)** | 15.6% | 25.8% | 0.58 | 10 | Conservative option |

---

## Phase 1: TOP_N Parameter Sweep

Tested different position counts while keeping all other parameters constant.

| TOP_N | CAGR | Max DD | Sharpe | Trades | Net Profit |
|-------|------|--------|--------|--------|------------|
| 1 | 35.7% | 47.1% | 0.80 | 95 | $2,018,084 |
| 2 | 13.2% | 42.5% | 0.40 | 240 | $246,366 |
| 3 | 17.9% | 36.6% | 0.56 | 352 | $388,662 |
| 5 | 13.6% | 31.9% | 0.47 | 572 | $243,866 |
| 10 | 15.6% | 25.8% | 0.58 | 927 | $312,700 |

**Observations:**
- TOP_N=1 dominates on CAGR but has highest drawdown
- TOP_N=2 underperforms due to less diversification without concentration benefits
- TOP_N=3 offers best risk-adjusted returns for low position counts
- TOP_N=10 achieves target <30% DD but sacrifices ~20% CAGR

---

## Phase 2: Diversified Strategy Optimization (5 positions)

Tested 7 variants to maximize CAGR while maintaining diversification.

| Version | Key Changes | CAGR | Max DD | Sharpe | Trades |
|---------|-------------|------|--------|--------|--------|
| v1 | Weekly rebalance | 7.9% | 59.0% | 0.26 | 2112 |
| v2 | Bi-weekly rebalance | 17.9% | 37.3% | 0.56 | 1119 |
| v3 | Monthly + faster SMA (20/50) | 18.8% | 38.3% | 0.56 | 699 |
| v4 | + 15% trailing stop | 13.3% | 33.2% | 0.43 | 583 |
| v5 | Linear momentum weighting | 18.8% | 38.0% | 0.58 | 582 |
| **v6** | **Squared momentum weighting** | **22.6%** | **41.3%** | **0.65** | **566** |
| v7 | + 75% bear market exposure | 22.8% | 46.6% | 0.64 | 566 |

---

## What Worked

### 1. Squared Momentum Weighting (+4% CAGR)
Instead of equal-weighting positions, allocate more capital to higher-momentum stocks by squaring their scores:

```python
# Square momentum to amplify differences
squared_mom = [(s, m**2) for s, m in top_rankings]
total_squared = sum(m for _, m in squared_mom)

for symbol, mom_sq in squared_mom:
    weight = (mom_sq / total_squared) * regime_exposure
    weight = min(weight, MAX_POSITION_SIZE)  # Cap at 60%
    self.set_holdings(symbol, weight)
```

**Why it works**: The best momentum stock typically has 2-3x the score of #5. Squaring amplifies this difference, concentrating capital in the strongest names while maintaining diversification.

### 2. Daily Trend Check with Loss Threshold
Exit positions that break trend AND are losing money:

```python
if not self.is_uptrending(symbol):
    avg_price = self.portfolio[symbol].average_price
    if current_price < avg_price * 0.97:  # Down 3%
        self.liquidate(symbol)
```

**Why it works**: Avoids holding losers through extended downtrends while allowing winners to stay even if temporarily below SMA.

### 3. MAX_POSITION_SIZE Cap (60%)
Even with momentum weighting, cap individual positions to maintain diversification.

---

## What Didn't Work

### 1. Weekly Rebalancing (v1)
- Caused 59% drawdown and only 7.9% CAGR
- Too much churn, too many false signals
- Monthly rebalancing is optimal for momentum strategies

### 2. Trailing Stops (v4)
- 15% trailing stop reduced CAGR from 18.8% to 13.3%
- Gets stopped out during normal volatility, misses recoveries
- Trend break exit is more effective

### 3. Bear Market Filter (v7)
- Reducing to 75% exposure in bear markets increased DD from 41% to 46%
- The trend filter already handles bear markets
- Adding regime filter causes whipsaw around 200 SMA

---

## Top P&L Contributors (v6)

| Symbol | Trades | Win Rate | Total P&L | Avg Win | Avg Loss |
|--------|--------|----------|-----------|---------|----------|
| GAP | 14 | 71.4% | $220,436 | 30.1% | -7.0% |
| GRPN | 7 | 57.1% | $165,999 | 57.1% | -15.4% |
| META | 9 | 66.7% | $80,177 | 42.5% | -5.0% |
| NVDA | 33 | 66.7% | $71,534 | 25.9% | -5.7% |
| TSLA | 18 | 61.1% | $68,747 | 44.8% | -10.8% |
| JWN | 9 | 55.6% | $61,193 | 11.0% | -10.2% |
| OXY | 8 | 100.0% | $49,006 | 30.1% | N/A |
| COP | 5 | 80.0% | $34,018 | 15.7% | -6.7% |

**Notable**: Strategy found value in "unloved" stocks (GAP, GRPN, JWN) that had strong momentum bursts. This validates the systematic high-beta universe approach that includes underperformers.

---

## Final Configuration (v6)

```python
# BEST DIVERSIFIED CONFIG (5 positions)
MOMENTUM_LOOKBACK = 63      # Standard momentum
TOP_N = 5                   # Five positions
MIN_MOMENTUM = 25           # Moderate threshold
MIN_R_SQUARED = 0.65        # Slightly relaxed
TREND_SMA_FAST = 50         # Standard fast SMA
TREND_SMA_SLOW = 100        # Standard slow SMA
LEVERAGE = 1.0              # No leverage
MAX_POSITION_SIZE = 0.60    # Allow 60% in best performer

# RISK MANAGEMENT
BEAR_MARKET_EXPOSURE = 1.0  # Full exposure (rely on trend filter)
TRAILING_STOP_PCT = 1.0     # Disabled
USE_MOMENTUM_WEIGHTING = True   # Weight by SQUARED momentum
DAILY_TREND_CHECK = True    # Check trend daily
```

---

## Recommendations

1. **For maximum returns**: Use TOP_N=1 concentrated strategy (35.7% CAGR, 47% DD)
2. **For diversified portfolio**: Use v6 configuration (22.6% CAGR, 41% DD)
3. **For conservative approach**: Use TOP_N=10 (15.6% CAGR, 26% DD)
4. **To achieve 30%+ CAGR with 5 positions**: Requires 1.3-1.5x leverage

---

## Backtest Period
- **Start**: January 1, 2015
- **End**: December 31, 2024
- **Duration**: 10 years
- **Starting Capital**: $100,000
