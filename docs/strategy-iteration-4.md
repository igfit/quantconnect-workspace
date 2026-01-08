# Strategy Iteration 4 (Round 8) - Signal Enhancement

## Round 7 Summary

Round 7 solved the concentration problem:
- NVDA contribution reduced from 73% to 20%
- Best: MultiSectorBalanced (Sharpe 0.898, CAGR 22.1%, MaxDD 19%)
- Trade-off: Lower returns but better risk-adjusted

## Round 8 Goal

**Improve signal quality while maintaining diversification.**

Can we get Sharpe > 1.0 with better entry timing?

---

## Strategies Tested

| # | Strategy | Thesis |
|---|----------|--------|
| 1 | AccelMomSectors | Multi-lookback momentum (1m, 3m, 6m average) |
| 2 | Near52WH | Academic 52-week-high filter for alpha |
| 3 | MomWeightedSectors | Weight sectors by momentum strength |
| 4 | QualityMegaCap | Tighter quality filter, only profitable mega-caps |
| 5 | AdaptivePositions | VIX-based position count (more positions in volatility) |

---

## Results

### Performance Summary

| Strategy | Sharpe | CAGR | Max DD | Orders | Top Stock % |
|----------|--------|------|--------|--------|-------------|
| **AdaptivePositions** | **0.967** | **24.4%** | **16.9%** | 267 | NVDA 26.6% |
| **AccelMomSectors** | **0.934** | **22.5%** | **18.1%** | 336 | TSLA 21.8% |
| MomWeightedSectors | 0.931 | 23.3% | 23.2% | 359 | - |
| QualityMegaCap | 0.811 | 15.5% | **11.6%** | 347 | - |
| Near52WH | 0.763 | 16.0% | 15.6% | 347 | - |

**Benchmark: SPY Buy-Hold**: Sharpe 0.57, CAGR 17.1%, MaxDD 33.7%

### Key Achievements

| Metric | Round 7 Best | Round 8 Best | Improvement |
|--------|--------------|--------------|-------------|
| Sharpe | 0.898 | **0.967** | +7.7% |
| CAGR | 22.1% | **24.4%** | +10.4% |
| MaxDD | 18.1% | **11.6%** (QualityMegaCap) | -36% |
| Top Stock % | 19.8% | 21.8% | Similar |

### Concentration Analysis

**AdaptivePositions (Sharpe 0.967):**
- Total P&L: $198,188
- NVDA: $52,668 (26.6%) - higher than R7
- Top 5 = 66% of P&L
- 22 profitable positions

**AccelMomSectors (Sharpe 0.934):**
- Total P&L: $177,028
- TSLA: $38,608 (21.8%) - **better diversified**
- NVDA: $26,561 (15.0%)
- Top 5 = 60% of P&L
- 20 profitable positions

---

## Analysis: What Worked

### 1. Adaptive Position Count (AdaptivePositions)
- VIX-based position sizing
- Low VIX (<20): 6 concentrated positions
- High VIX (>30): 12 diversified positions
- Result: Near Sharpe 1.0 (0.967)

### 2. Accelerating Momentum (AccelMomSectors)
- Multi-lookback: avg(1m, 3m, 6m)
- Weights recent momentum more (50/30/20)
- Catches momentum earlier than 6-month alone
- Better diversification than AdaptivePositions

### 3. Quality Filter (QualityMegaCap)
- Removed NVDA, TSLA (too volatile)
- Only profitable mega-caps
- **Lowest drawdown ever: 11.6%**
- Trade-off: Lower returns (15.5% CAGR)

### What Didn't Help

1. **52-Week High Filter** - Didn't improve over simple momentum
2. **Momentum-Weighted Sectors** - High drawdown (23.2%)

---

## Conclusions

1. **Sharpe 0.967 achieved** - nearly hit 1.0 target
2. **Adaptive position count works** - adjust to market conditions
3. **Accelerating momentum improves timing** - multi-lookback better than single
4. **Quality filter = lowest drawdown** - 11.6% MaxDD is excellent
5. **Concentration slightly higher** (26.6% vs 19.8%) - trade-off for higher returns

### Best Strategies by Use Case

| Use Case | Strategy | Sharpe | CAGR | MaxDD |
|----------|----------|--------|------|-------|
| **Best Returns** | AdaptivePositions | 0.967 | 24.4% | 16.9% |
| **Best Diversified** | AccelMomSectors | 0.934 | 22.5% | 18.1% |
| **Lowest Risk** | QualityMegaCap | 0.811 | 15.5% | 11.6% |
| **Balanced** | AccelMomSectors | 0.934 | 22.5% | 18.1% |

---

## Strategy Files

| Strategy | File |
|----------|------|
| AdaptivePositions | `algorithms/strategies/adaptive_positions.py` |
| AccelMomSectors | `algorithms/strategies/accel_momentum_sectors.py` |
| Near52WH | `algorithms/strategies/near_52wh_sectors.py` |
| MomWeightedSectors | `algorithms/strategies/momentum_weighted_sectors.py` |
| QualityMegaCap | `algorithms/strategies/quality_megacap_diversified.py` |

---

## Cumulative Progress (Rounds 6-8)

| Round | Best Sharpe | Best CAGR | Best MaxDD | NVDA % |
|-------|-------------|-----------|------------|--------|
| 6 | 1.1+ | 70% | 30% | 73% |
| 7 | 0.898 | 22% | 18% | 20% |
| **8** | **0.967** | **24%** | **11.6%** | 22-27% |

**Progress**: Sharpe nearly 1.0 with diversification maintained!

---

## Next Steps

1. [ ] Combine AdaptivePositions with AccelMomSectors
2. [ ] Test on 10-year period (2015-2024)
3. [ ] Create portfolio of multiple strategies
4. [ ] Paper trade best performers
