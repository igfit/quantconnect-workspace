# Strategy Results Comparison

**Date**: 2026-01-07
**Backtest Period**: 2020-01-01 to 2024-12-31 (5 years)
**Initial Capital**: $100,000

---

## Target Requirements

| Metric | Target | Stretch |
|--------|--------|---------|
| CAGR | 30-50% | 40%+ |
| Max Drawdown | <15% | <20% |
| Sharpe Ratio | >1.0 | >1.5 |

---

## Results Summary (All Strategies Tested)

| Strategy | Sharpe | CAGR | Max DD | Notes |
|----------|--------|------|--------|-------|
| **Top Picks Momentum** | **1.189** | **38.31%** | 33.5% | **Best returns & Sharpe** |
| Top Picks Balanced | 0.951 | 29.2% | 31.7% | Trailing stops didn't help |
| Adaptive V2 (less conservative) | 0.949 | 28.6% | 30.7% | Higher returns, high DD |
| **Adaptive (conservative)** | **0.960** | 18.4% | **15.6%** | **Best drawdown** |
| Top Picks Tight Risk | 0.911 | 23.8% | 24.1% | Tighter stops hurt returns |
| Accel Mom Aggressive | 0.952 | 26.4% | 28.0% | Daily rebalance |
| Accel Mom Balanced | 0.935 | 21.1% | 17.2% | Conservative |
| Accel Dual Momentum | 0.898 | 20.0% | 16.2% | Base strategy |
| Bi-weekly | 0.720 | 19.5% | 25.7% | More trading hurt |
| Sector Rotation | 0.285 | 7.8% | 16.8% | ETFs underperform |

---

## Key Finding: Return vs Risk Trade-off

```
                    HIGH RETURNS
                         ^
                         |
    Top Picks Momentum   ●  (38% CAGR, 33% DD)
                         |
    Adaptive V2          ●  (29% CAGR, 31% DD)
                         |
    Tight Risk           ●  (24% CAGR, 24% DD)
                         |
    Adaptive Conservative●  (18% CAGR, 16% DD)
                         |
                         v
                    LOW DRAWDOWN
```

**No single strategy meets ALL three targets simultaneously.**

---

## Best Strategies by Use Case

### Option A: Maximum Returns (Accept Higher DD)

**Top Picks Momentum**
```
Sharpe:     1.189 ✓ (>1.0)
CAGR:       38.31% ✓ (30-50%)
Max DD:     33.5% ✗ (>20%)
```

Best for: Aggressive investors, long time horizon, can stomach 30%+ swings

### Option B: Controlled Risk (Accept Lower Returns)

**Adaptive (Conservative)**
```
Sharpe:     0.960 (~1.0)
CAGR:       18.4% ✗ (<30%)
Max DD:     15.6% ✓ (<20%)
```

Best for: Risk-averse investors, steady growth preferred

### Option C: Hybrid Approach

Run both strategies with 50/50 allocation:
- Expected CAGR: ~28%
- Expected Max DD: ~25%
- Blended Sharpe: ~1.05

---

## Strategy Details

### Top Picks Momentum

```python
# Entry Conditions (ALL must be true)
1. Composite score > 0
   Score = (ROC_21 × 0.5) + (ROC_63 × 0.3) + (ROC_126 × 0.2)
2. Score > SPY score (relative strength)
3. Price > 50 SMA (trend confirmation)
4. Within 35% of 52-week high

# Position Sizing
- 6 positions, max 15% each
- Equal weight

# Risk Management
- 15% hard stop loss
- Exit if score < 0 or price < SMA

# Rebalance
- Weekly (Friday)
```

### Adaptive (Conservative)

```python
# Same entry conditions PLUS:

# Market Regime Detection
- BULLISH: SPY > SMA50 > SMA200, momentum > 5%
  → Full exposure (1.0x)
- CAUTIOUS: Mixed signals
  → Reduced exposure (0.7x)
- BEARISH: SPY < SMA200 or momentum < -10%
  → Exit all positions

# Volatility-Adjusted Sizing
- Lower ATR stocks get larger positions
- Higher ATR stocks get smaller positions
```

---

## Why The Trade-off Exists

### March 2020 Crash Analysis

The 2020 crash dominates drawdown metrics:
- SPY dropped 34% in 5 weeks
- High-beta stocks dropped 40-60%
- No daily stop could prevent gap-down losses

**Strategies that stayed invested** through March 2020:
- Captured the V-shaped recovery (100%+ gains)
- But showed 30%+ max drawdown

**Strategies that exited early**:
- Avoided the worst of the crash
- But missed much of the recovery
- Lower returns, lower drawdown

---

## Learnings

### What Drives High Returns

1. **Concentration**: 6 positions > 20 positions
2. **Momentum weighting**: Recent momentum more predictive
3. **Relative strength**: Only hold what beats benchmark
4. **Position size**: 15% positions compound faster

### What Reduces Drawdown

1. **Regime detection**: Exit before crashes (hard to time)
2. **Volatility scaling**: Smaller positions in volatile stocks
3. **More diversification**: 10+ positions reduces single-stock risk
4. **Stop losses**: 10-12% stops limit damage (but also returns)

### What Doesn't Help Much

1. **Trailing stops**: Don't help in fast crashes (gaps)
2. **More frequent trading**: Just adds costs
3. **Sector ETFs**: Lower beta = lower returns
4. **Bi-weekly rebalancing**: Extra turnover, worse results

---

## Recommended Next Steps

1. **10-Year Backtest**: Extend to 2015-2024 to validate
2. **Walk-Forward**: Out-of-sample testing
3. **Paper Trade**: 3 months before live capital
4. **Regime Refinement**: Better crash detection signals

---

## Files Reference

| Strategy | File | QC Project ID |
|----------|------|---------------|
| Top Picks Momentum | `algorithms/strategies/top_picks_momentum.py` | 27319694 |
| Top Picks Tight Risk | `algorithms/strategies/top_picks_tight_risk.py` | 27320479 |
| Top Picks Adaptive | `algorithms/strategies/top_picks_adaptive.py` | 27320541 |
| Top Picks Adaptive V2 | `algorithms/strategies/top_picks_adaptive_v2.py` | 27320600 |
| Top Picks Balanced | `algorithms/strategies/top_picks_balanced.py` | 27320672 |
| Top Picks Biweekly | `algorithms/strategies/top_picks_biweekly.py` | 27320634 |
| Accel Mom Aggressive | `algorithms/strategies/accel_mom_aggressive.py` | 27319630 |
