# Strategy Iteration 5 (Round 9) - Breaking Sharpe 1.0

## Round 8 Summary

Round 8 nearly hit Sharpe 1.0:
- Best: AdaptivePositions (Sharpe 0.967, CAGR 24.4%)
- Key insight: VIX-based position sizing works
- Multi-lookback momentum improves timing

## Round 9 Goal

**BREAK Sharpe 1.0 barrier while maintaining diversification.**

---

## Strategies Tested

| # | Strategy | Thesis |
|---|----------|--------|
| 1 | CombinedAdaptiveAccel | Merge AdaptivePositions + AccelMom best ideas |
| 2 | BreadthMomentum | Market breadth filter (% sectors > 200 SMA) |
| 3 | TrendStrengthMom | ADX > 20 filter for strong trends only |
| 4 | VolRegimeStrategic | Different allocation by volatility regime |
| 5 | MultiFactorRank | Combine momentum + volatility factors |

---

## Results - BREAKTHROUGH!

### Performance Summary

| Strategy | Sharpe | CAGR | Max DD | Orders |
|----------|--------|------|--------|--------|
| **TrendStrengthMom** | **1.321** | **32.7%** | 22.8% | 450 |
| **CombinedAdaptiveAccel** | **1.108** | 28.8% | 23.6% | 433 |
| **BreadthMomentum** | **1.03** | 26.4% | 25.7% | - |
| VolRegimeStrategic | 0.995 | 24.0% | 21.9% | - |
| MultiFactorRank | 0.926 | 22.5% | 30.2% | - |

**Benchmark: SPY Buy-Hold (2020-2024)**: Sharpe 0.57, CAGR 17.1%, MaxDD 33.7%

### KEY ACHIEVEMENT: 3 Strategies > Sharpe 1.0!

| Metric | Round 8 Best | Round 9 Best | Improvement |
|--------|--------------|--------------|-------------|
| Sharpe | 0.967 | **1.321** | +36.6% |
| CAGR | 24.4% | **32.7%** | +34% |
| MaxDD | 11.6% | 21.9% | Worse (trade-off) |

---

## Concentration Analysis

### TrendStrengthMom (Sharpe 1.321)

Total P&L: $312,277

| Ticker | P&L | % of Total |
|--------|-----|------------|
| GE | $70,727 | 22.7% |
| NVDA | $68,525 | 22.0% |
| TSLA | $35,465 | 11.4% |
| ABBV | $21,377 | 6.8% |
| META | $21,133 | 6.8% |

**Top 5 = 70% of P&L**
**24 positions traded** (16 closed, 8 open)

### CombinedAdaptiveAccel (Sharpe 1.108)

Total P&L: $255,964

| Ticker | P&L | % of Total |
|--------|-----|------------|
| NVDA | $76,483 | 29.9% |
| GE | $29,903 | 11.7% |
| TSLA | $27,920 | 10.9% |
| META | $16,265 | 6.4% |
| GS | $16,263 | 6.4% |

**Top 5 = 65% of P&L**
**29 positions traded** (24 closed, 5 open)

---

## Analysis: What Worked

### 1. ADX Trend Strength Filter (TrendStrengthMom) - BEST

**Why it worked:**
- ADX > 20 filters out choppy, sideways markets
- +DI > -DI confirms uptrend direction
- Only trades stocks in clear trends
- Momentum * trend_strength composite scoring

**Key insight**: Momentum signals are unreliable in ranging markets. ADX filter eliminates false signals.

### 2. VIX-Based Position Sizing + Multi-Lookback (CombinedAdaptiveAccel)

**Why it worked:**
- Low VIX (<18): 5 concentrated positions
- High VIX (>28): 11 diversified positions
- Multi-lookback momentum (1m, 3m, 6m) for timing
- Sector constraints (max 3 per sector)

### 3. Market Breadth Filter (BreadthMomentum)

**Why it worked:**
- Uses sector ETFs as breadth proxy
- Strong breadth (>70% above 200 SMA): aggressive allocation
- Weak breadth (<35%): defensive allocation
- Captures market regime more granularly than SPY alone

### What Didn't Work as Well

1. **VolRegimeStrategic** (Sharpe 0.995) - Close but complex
   - Quality filter in high vol helped drawdown
   - But regime switches may have caused whipsaw

2. **MultiFactorRank** (Sharpe 0.926) - Volatility factor hurt
   - Low volatility stocks didn't have enough momentum
   - Factor weighting may need optimization

---

## Conclusions

1. **SHARPE > 1.0 ACHIEVED** - Three strategies broke the barrier!
2. **ADX is the key** - Trend strength filter is the single most impactful addition
3. **TrendStrengthMom is the winner**: Sharpe 1.321, CAGR 32.7%
4. **Trade-off acknowledged**: Higher drawdown (22-25%) vs Round 7's 18-19%
5. **Concentration acceptable**: Top stock ~22-30% vs Round 6's 73%

### Best Strategies by Use Case

| Use Case | Strategy | Sharpe | CAGR | MaxDD |
|----------|----------|--------|------|-------|
| **Best Risk-Adjusted** | TrendStrengthMom | 1.321 | 32.7% | 22.8% |
| **Best Overall** | TrendStrengthMom | 1.321 | 32.7% | 22.8% |
| **Best Diversified** | BreadthMomentum | 1.03 | 26.4% | 25.7% |
| **Most Adaptive** | CombinedAdaptiveAccel | 1.108 | 28.8% | 23.6% |

---

## Strategy Files

| Strategy | File |
|----------|------|
| TrendStrengthMom | `algorithms/strategies/trend_strength_momentum.py` |
| CombinedAdaptiveAccel | `algorithms/strategies/combined_adaptive_accel.py` |
| BreadthMomentum | `algorithms/strategies/breadth_momentum.py` |
| VolRegimeStrategic | `algorithms/strategies/vol_regime_strategic.py` |
| MultiFactorRank | `algorithms/strategies/multi_factor_rank.py` |

---

## Cumulative Progress (Rounds 6-9)

| Round | Best Sharpe | Best CAGR | Best MaxDD | Top Stock % |
|-------|-------------|-----------|------------|-------------|
| 6 | 1.1+ | 70% | 30% | 73% |
| 7 | 0.898 | 22% | 18% | 20% |
| 8 | 0.967 | 24% | 11.6% | 22-27% |
| **9** | **1.321** | **33%** | 21.9% | 22-30% |

**Progress Summary**:
- Round 6: High Sharpe but extreme concentration (NVDA = 73%)
- Round 7: Solved concentration but lost Sharpe
- Round 8: Recovery to near 1.0 with diversification maintained
- Round 9: **BREAKTHROUGH** - Sharpe 1.321 with acceptable concentration

---

## Next Steps

1. [ ] Test TrendStrengthMom on 10-year period (2015-2024) for robustness
2. [ ] Walk-forward validation on out-of-sample data
3. [ ] Create portfolio combining top 2-3 strategies
4. [ ] Paper trade best performers for 3 months
5. [ ] Research: Why does ADX work so well? Can we optimize threshold?

---

## Key Learnings

### ADX Indicator Implementation

```python
# ADX filter for strong trends
adx_val = self.adx_ind[ticker].current.value
positive_di = self.adx_ind[ticker].positive_directional_index.current.value
negative_di = self.adx_ind[ticker].negative_directional_index.current.value

# ADX > 20 = trending, +DI > -DI = uptrend
if adx_val < 20:
    continue
if positive_di <= negative_di:
    continue
```

### Variable Naming Bug (Fixed)

```python
# WRONG - shadows method
self.momp = {}
self.momp[ticker] = self.momp(sym, 126)  # ERROR: dict not callable

# RIGHT - use suffix
self.momp_ind = {}
self.momp_ind[ticker] = self.momp(sym, 126)  # Works
```
