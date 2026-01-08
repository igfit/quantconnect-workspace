# Strategy Iteration 6 (Round 10) - Drawdown Reduction

## Round 9 Summary

Round 9 achieved Sharpe > 1.0 breakthrough:
- Best: TrendStrengthMom (Sharpe 1.321, CAGR 32.7%, MaxDD 22.8%)
- Key insight: ADX > 20 filter eliminates false signals in choppy markets
- Trade-off: Higher drawdown (22-25%) vs Round 7's 18-19%

## Round 10 Goal

**Reduce drawdown while maintaining Sharpe > 1.0**

---

## Strategies Tested

| # | Strategy | Thesis |
|---|----------|--------|
| 1 | TrendMomRSIExit | ADX entry + RSI < 30 early exit (from Wave-EWO research) |
| 2 | ATRTrailingStop | ADX entry + ATR-based trailing stops |
| 3 | AccelMomentum | Only enter when momentum accelerating (1m > 3m) |
| 4 | VolTargeted | Position sizing to target constant portfolio volatility |
| 5 | DualFilterMom | ADX + RSI confirmation for entry AND exit |

---

## Results

### Performance Summary

| Strategy | Sharpe | CAGR | MaxDD | Win% | R:R | Orders |
|----------|--------|------|-------|------|-----|--------|
| **TrendMomRSIExit** | **1.351** | 32.7% | 21.7% | 70% | 1.56 | 475 |
| **ATRTrailingStop** | **1.243** | 24.0% | **14.7%** | 58% | - | 561 |
| DualFilterMom | 0.953 | 16.9% | 15.7% | 49% | 2.30 | 551 |
| VolTargeted | 0.814 | 11.0% | **6.4%** | 63% | - | 549 |
| AccelMomentum | 0.275 | 8.3% | 28.0% | 58% | - | 475 |

**Benchmark: SPY Buy-Hold (2020-2024)**: Sharpe 0.57, CAGR 17.1%, MaxDD 33.7%

### Key Achievement: Drawdown Reduced!

| Metric | Round 9 Best | Round 10 Best | Improvement |
|--------|--------------|---------------|-------------|
| Sharpe | 1.321 | **1.351** | +2.3% |
| MaxDD | 22.8% | **14.7%** | -35.5% |
| CAGR | 32.7% | 32.7% / 24.0% | Same / -27% |

---

## Concentration Analysis

### TrendMomRSIExit (Sharpe 1.351)

Total P&L: $312,855

| Ticker | P&L | % of Total |
|--------|-----|------------|
| GE | $76,799 | 24.5% |
| NVDA | $61,139 | 19.5% |
| TSLA | $38,832 | 12.4% |
| META | $21,557 | 6.9% |
| NFLX | $20,501 | 6.6% |

**Top 5 = 70% of P&L**
**25/29 positions profitable (86%)**

### ATRTrailingStop (Sharpe 1.243, Best Drawdown)

Total P&L: $194,417

| Ticker | P&L | % of Total |
|--------|-----|------------|
| GE | $46,074 | 23.7% |
| NVDA | $35,296 | 18.2% |
| TSLA | $25,297 | 13.0% |
| LLY | $13,586 | 7.0% |
| CRM | $13,584 | 7.0% |

**Top 5 = 69% of P&L**
**22/29 positions profitable (76%)**

---

## Analysis: What Worked

### 1. RSI < 30 Early Exit (TrendMomRSIExit) - BEST SHARPE

**Why it worked:**
- ADX filter for entry (same as Round 9's best)
- RSI < 30 triggers early exit when momentum collapses
- Reduces time in losing positions
- Result: Sharpe 1.351 (slight improvement), DD 21.7% (slight improvement)

**Key insight**: RSI exit catches momentum failures before full reversion.

### 2. ATR Trailing Stops (ATRTrailingStop) - BEST DRAWDOWN

**Why it worked:**
- Entry same as TrendStrengthMom (ADX filter)
- 2×ATR trailing stop locks in profits
- Stops move UP only, never down
- Forces earlier exits in volatile corrections
- Result: MaxDD 14.7% (vs 22.8%) - 35% improvement!

**Key insight**: Trailing stops are the key to drawdown control.

### 3. Volatility Targeting (VolTargeted) - LOWEST DD

**Why it worked:**
- Smaller positions in high-volatility stocks
- Target 15% portfolio volatility
- Scale exposure based on regime
- Result: MaxDD 6.4% (best!), but CAGR only 11%

**Trade-off**: Too conservative - limited upside to preserve downside.

### What Didn't Work

1. **AccelMomentum** (Sharpe 0.275) - FAILED
   - Acceleration filter too restrictive
   - Missed too many good opportunities
   - Only 8.3% CAGR = worse than buy-hold

2. **DualFilterMom** (Sharpe 0.953) - Close but not quite
   - RSI 40-70 entry filter was too strict
   - Win rate dropped to 49%
   - Still viable for conservative portfolios

---

## Conclusions

1. **ATR trailing stops are the breakthrough** for drawdown reduction
2. **TrendMomRSIExit is the new best** overall (Sharpe 1.351)
3. **ATRTrailingStop is best for risk-averse** (Sharpe 1.243, DD 14.7%)
4. **Trade-off confirmed**: Lower drawdown = lower returns (VolTargeted)
5. **Acceleration filter doesn't work** - too restrictive

### Best Strategies by Use Case

| Use Case | Strategy | Sharpe | CAGR | MaxDD |
|----------|----------|--------|------|-------|
| **Best Risk-Adjusted** | TrendMomRSIExit | 1.351 | 32.7% | 21.7% |
| **Best Drawdown** | ATRTrailingStop | 1.243 | 24.0% | 14.7% |
| **Most Conservative** | VolTargeted | 0.814 | 11.0% | 6.4% |

---

## Strategy Files

| Strategy | File |
|----------|------|
| TrendMomRSIExit | `algorithms/strategies/trend_mom_rsi_exit.py` |
| ATRTrailingStop | `algorithms/strategies/atr_trailing_stop.py` |
| AccelMomentum | `algorithms/strategies/accel_momentum.py` |
| VolTargeted | `algorithms/strategies/vol_targeted.py` |
| DualFilterMom | `algorithms/strategies/dual_filter_mom.py` |

---

## Cumulative Progress (Rounds 6-10)

| Round | Best Sharpe | Best CAGR | Best MaxDD | Top Stock % |
|-------|-------------|-----------|------------|-------------|
| 6 | 1.1+ | 70% | 30% | 73% |
| 7 | 0.898 | 22% | 18% | 20% |
| 8 | 0.967 | 24% | 11.6% | 22-27% |
| 9 | **1.321** | **33%** | 21.9% | 22-30% |
| **10** | **1.351** | 33% | **14.7%** | 23-24% |

**Progress Summary**:
- Round 6: High Sharpe but extreme concentration (NVDA = 73%)
- Round 7: Solved concentration but lost Sharpe
- Round 8: Recovery to near 1.0 with diversification maintained
- Round 9: **BREAKTHROUGH** - Sharpe 1.321 with acceptable concentration
- Round 10: **Drawdown solved** - Sharpe 1.351, MaxDD 14.7%

---

## Key Learnings

### ATR Trailing Stop Implementation

```python
# Track highest price since entry
if ticker not in self.highest_since_entry:
    self.highest_since_entry[ticker] = price
else:
    self.highest_since_entry[ticker] = max(self.highest_since_entry[ticker], price)

# Calculate trailing stop: highest - 2*ATR
new_stop = self.highest_since_entry[ticker] - (2.0 * atr_val)

# Only move stop up, never down
self.trailing_stops[ticker] = max(self.trailing_stops[ticker], new_stop)

# Exit if price hits trailing stop
if price < self.trailing_stops[ticker]:
    self.liquidate(holding.symbol)
```

### RSI Early Exit

```python
# Daily check for RSI-based early exits
if rsi_val < 30:
    self.liquidate(holding.symbol)
    self.debug(f"RSI EXIT {ticker} (RSI={rsi_val:.1f})")
```

---

## Next Steps

1. [ ] Combine best elements: ADX entry + ATR trailing + RSI exit
2. [ ] Test on 10-year period (2015-2024) for robustness
3. [ ] Walk-forward validation on out-of-sample data
4. [ ] Paper trade ATRTrailingStop for 3 months
5. [ ] Research: Optimal ATR multiplier (test 1.5x, 2x, 2.5x)
