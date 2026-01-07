# Strategy Iteration 2 - Meeting Portfolio Requirements

## Problem Analysis

### Why Previous Strategies Failed

**roc_mom_large Analysis:**
- Sharpe: 1.028, CAGR: 32.9%, Max DD: 37%
- **Problem 1**: 37% max drawdown exceeds 15-20% target
- **Problem 2**: Concentrated in 6 tech stocks - NVDA alone drove 67% of returns
- **Problem 3**: Not diversified - all stocks correlate in crashes

**Key Insight**: The strategy "worked" because of NVDA's AI boom, not because of robust alpha generation.

### Target Requirements (from portfolio-strategy-requirements.md)

| Metric | Target | Stretch |
|--------|--------|---------|
| CAGR | 30-50% | 40%+ |
| Max Drawdown | 15% | <20% |
| Sharpe Ratio | >1.0 | >1.5 |
| Monthly Win Rate | >60% | >70% |
| Positions | 20+ | Variable |

### The Math Problem

To achieve 30% CAGR with 15% max DD requires Sharpe ~2.0.
- Top hedge funds achieve ~1.0-1.5 Sharpe
- This is **extremely ambitious**
- Realistic expectation: 20-30% CAGR, 20-25% DD, Sharpe 0.8-1.2

---

## Deep Analysis: What Actually Creates Alpha?

### Academic Research Findings

1. **Momentum (Jegadeesh & Titman, 1993)**
   - Winners continue winning for 3-12 months
   - Average excess return: 1% per month
   - But crashes hard in market reversals

2. **Accelerating Momentum (Grinblatt & Moskowitz, 2004)**
   - Multiple lookbacks (1m, 3m, 6m) outperform single lookback
   - Captures "acceleration" in trend
   - Reduces whipsaw

3. **52-Week High Momentum (George & Hwang, 2004)**
   - Proximity to 52-week high predicts returns
   - 0.65%/month vs 0.38% for classic momentum
   - Key crash protection - stocks near highs don't crash as hard

4. **Relative Strength (Levy, 1967)**
   - Compare stock to benchmark
   - Only hold stocks beating the market
   - Natural regime filter

### Structural Edge Sources

1. **Behavioral**: Anchoring, underreaction to good news
2. **Institutional**: Rebalancing flows, benchmark tracking
3. **Information**: Earnings momentum, analyst revisions

---

## Strategy Design: Accelerating Dual Momentum

### Core Logic

```
ENTRY (ALL must be true):
1. Accelerating Momentum > 0
   AccelMom = (ROC_21 + ROC_63 + ROC_126) / 3

2. Relative Strength > 0
   RelStr = Stock_AccelMom - SPY_AccelMom

3. Trend Confirmation
   Price > SMA(50)

4. Near 52-Week High (CRASH PROTECTION)
   Price / MAX(Price, 252) > 0.75

EXIT (ANY triggers):
1. Accelerating Momentum < 0
2. Relative Strength < 0 (stock underperforming SPY)
3. Price < SMA(50)
```

### Why This Should Work

| Component | Purpose | Expected Impact |
|-----------|---------|-----------------|
| AccelMom | Catch trending stocks | +8-12% annual |
| RelStr | Filter vs benchmark | +3-5% annual |
| SMA Filter | Avoid falling knives | Reduce DD by 5-10% |
| 52WH Filter | Crash protection | Reduce DD by 10-15% |

### Position Sizing

```
Max Position: 5% of portfolio
Min Position: 2% of portfolio
Max Positions: 20
Min Positions: 5 (else hold cash)

Rebalance: Weekly (Friday close -> Monday open)
```

---

## Universe Design

### Requirements
- 25-30 stocks
- 80% high-beta momentum names
- 20% stable large-caps for ballast
- Liquid ($500M+ daily volume)
- >$5 share price

### Proposed Universe (28 stocks)

**High-Beta Momentum (22 stocks):**

| Sector | Stocks |
|--------|--------|
| Tech Giants | AAPL, MSFT, GOOGL, AMZN, META |
| AI/Semiconductors | NVDA, AMD, AVGO, QCOM |
| High-Growth Tech | TSLA, NFLX, CRM, ADBE |
| Fintech/Payments | SQ, PYPL, V, MA |
| Cloud/Cyber | SNOW, CRWD, NET |
| E-commerce | SHOP |

**Stable Large-Caps (6 stocks):**

| Sector | Stocks |
|--------|--------|
| Financials | JPM, GS |
| Healthcare | UNH, LLY |
| Consumer | COST, HD |

### Why This Universe?

1. **Diversified by sector** - Not all tech
2. **High liquidity** - Easy to exit
3. **Mix of beta** - Some defensive, mostly growth
4. **Proven momentum** - These stocks have momentum characteristics

---

## Implementation Approach

### Challenge: Compiler Limitations

Current compiler doesn't support:
1. Relative strength comparison to benchmark
2. Maximum price over N periods (52-week high)
3. Composite indicators (averaging multiple ROCs)

### Solution: Custom QC Algorithm

Write a custom QuantConnect algorithm that implements:
1. Accelerating momentum calculation
2. Relative strength vs SPY
3. 52-week high proximity
4. Dynamic position sizing

This requires direct Python code, not the spec -> compiler flow.

---

## Alternative Strategies (Compiler-Compatible)

If custom code doesn't work, simpler strategies using existing infrastructure:

### Strategy A: Multi-ROC Filter
```
Entry: ROC(21) > 0 AND ROC(63) > 0 AND Price > SMA(50)
Exit: ROC(63) < 0 OR Price < SMA(50)
Universe: 20 diversified stocks
```

### Strategy B: EMA + Momentum
```
Entry: EMA(12) > EMA(26) AND ROC(63) > 0
Exit: EMA(12) < EMA(26)
Universe: 20 diversified stocks
```

### Strategy C: Sector Rotation Plus
```
Entry: ROC(63) > 0 AND ROC(21) > 0
Exit: ROC(63) < -5
Universe: 11 Sector ETFs (XLK, XLF, XLE, etc.)
```

---

## Next Steps

1. [ ] Write custom QC algorithm for Accelerating Dual Momentum
2. [ ] Backtest with full 28-stock universe
3. [ ] If DD too high, test with ETF-only universe
4. [ ] Test compiler-compatible alternatives
5. [ ] Compare results and iterate
