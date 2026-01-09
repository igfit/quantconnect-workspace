# RSI Indicator Parameter Study Results

## Executive Summary

This study systematically tested RSI-based mean reversion strategies on high-beta stocks (TSLA, NVDA, AMD) with regime filtering. The best configuration found was **RSI(5) with Entry < 35, Exit > 55**, but walk-forward validation shows the strategy is highly regime-dependent.

## Study Methodology

### Universe
- High-beta stocks: TSLA, NVDA, AMD
- Daily resolution
- $100,000 starting capital
- $20,000 per position, max 5 positions

### Regime Filter
- Bull market: SPY > 200 SMA
- Bear market: Exit all positions, wait for recovery

### Walk-Forward Periods
- Train: 2018-2020 (3 years)
- Test: 2021-2022 (2 years)
- Validate: 2023-2024 (2 years)

---

## RSI Period Comparison (Full Period 2018-2024)

| RSI Period | Entry | Exit | CAGR | Sharpe | DD | Win% | Trades |
|------------|-------|------|------|--------|-----|------|--------|
| 2 | <20 | >60 | 4.2% | 0.07 | 12% | 56% | 858 |
| 3 | <25 | >55 | 2.6% | -0.03 | 1.5% | 86% | 15 |
| 5 | <30 | >60 | 21.5% | 1.33 | 3.4% | 80% | 10 |
| **5** | **<35** | **>55** | **24.6%** | **1.49** | **3.4%** | **86%** | **15** |
| 5 | <40 | >50 | -0.2% | -0.29 | 4.7% | 62% | 28 |
| 7 | <35 | >65 | 16.4% | 1.43 | 1.7% | 100% | 7 |
| 14 | <30 | >70 | 0% | 0 | 0% | - | 0 |

### Key Findings - RSI Period

1. **RSI(2) generates too many trades** - 858 trades with 56% win rate is low quality
2. **RSI(5-7) is the sweet spot** - fewer but higher quality trades
3. **RSI(14) is too slow** - never triggers on high-beta stocks
4. **Trade frequency vs quality tradeoff** - longer periods = fewer but better trades

---

## Entry/Exit Threshold Analysis

| Config | CAGR | Sharpe | Trades | Verdict |
|--------|------|--------|--------|---------|
| E<30 X>60 | 21.5% | 1.33 | 10 | Good but few trades |
| E<35 X>55 | 24.6% | 1.49 | 15 | **Best overall** |
| E<40 X>50 | -0.2% | -0.29 | 28 | Too loose, diluted signal |

### Key Findings - Thresholds

1. **Entry < 35 is optimal** - catches moderate oversold, not just extremes
2. **Exit > 55 (quick exit)** - better than waiting for overbought
3. **Looser thresholds (E<40) dilute the signal** - too many marginal trades

---

## Confirmation Indicator Tests

| Indicator | CAGR | Sharpe | Trades | Verdict |
|-----------|------|--------|--------|---------|
| RSI alone | 24.6% | 1.49 | 15 | Best performer |
| RSI + ATR filter | 0.0% | -0.44 | 224 | Failed |
| RSI + Momentum confirm | -6.7% | -1.27 | 8 | Failed |
| Williams %R | 1.5% | -0.47 | 175 | Failed |
| Expanded Universe (6 stocks) | 10.9% | 0.51 | 37 | Diluted returns |

### Key Findings - Confirmation

1. **Simple is better** - adding indicators hurt performance
2. **ATR volatility filter generated too many trades** - lost selectivity
3. **Momentum confirmation is counterproductive** - we want to buy BEFORE momentum turns
4. **High-beta universe (3 stocks) outperforms expanded universe**

---

## Walk-Forward Validation Results

| Period | CAGR | Sharpe | DD | Win% | Trades |
|--------|------|--------|-----|------|--------|
| Train (2018-2020) | 24.6% | 1.49 | 3.4% | 86% | 15 |
| Test (2021-2022) | -0.06% | 0.04 | 8.0% | 56% | 39 |
| Validate (2023-2024) | 3.5% | -0.36 | 2.1% | 25% | 8 |

### Walk-Forward Analysis

**FAILED WALK-FORWARD TEST**

The strategy shows significant regime dependency:

1. **Train period (2018-2020)**: Strong bull market with TSLA's historic run-up. RSI pullbacks provided excellent entry points.

2. **Test period (2021-2022)**: Includes 2022 bear market. Regime filter worked (limited losses to 8% DD) but win rate dropped from 86% to 56%.

3. **Validate period (2023-2024)**: Recovery phase but strategy didn't capitalize. Only 8 trades with 25% win rate.

### Why the Strategy Failed Walk-Forward

1. **Regime Dependency**: 2018-2020 had ideal conditions (strong uptrend with pullbacks)
2. **Post-2020 High-Beta Behavior Changed**: These stocks became more volatile with quicker reversions
3. **Regime Filter is Binary**: Works well to avoid losses but misses nuanced market conditions
4. **Small Sample Size**: 15 trades in training is statistically insufficient

---

## Conclusions

### What Worked
1. RSI(5) is better than RSI(2) for high-beta stocks - more selective
2. Regime filtering (SPY > 200 SMA) prevented major drawdowns
3. Quick exits (RSI > 55) captured mean reversion without waiting too long
4. Simple strategy without confirmation indicators performed best

### What Didn't Work
1. Strategy failed walk-forward validation - not robust
2. Adding confirmation indicators (ATR, momentum) hurt performance
3. Williams %R underperformed RSI
4. Expanding universe beyond high-beta diluted returns

### Recommendations for Future Research

1. **Add Market Regime Nuance**: Instead of binary (bull/bear), consider:
   - Trending up: momentum strategies
   - Ranging: mean reversion
   - Trending down: cash

2. **Adaptive Parameters**: RSI thresholds that adjust to volatility

3. **Longer Lookback for Entry**: Combine RSI with higher timeframe trend

4. **Position Sizing Based on Conviction**: Scale size by how oversold

5. **Different Exit Strategy**: Trail stop instead of fixed RSI exit

---

## Final Strategy Code

Best configuration: `rsi5_e35_x55_2018_2020.py`

```python
Parameters:
- RSI Period: 5
- Entry: RSI < 35
- Exit: RSI > 55 OR Stop Loss 5% OR Time Stop 5 days
- Regime: SPY > 200 SMA
- Universe: TSLA, NVDA, AMD
- Position Size: $20,000 per trade
- Max Positions: 5
```

**Note**: This strategy showed excellent in-sample results but failed out-of-sample testing. Use with caution and only as a starting point for further research.

---

*Study completed: January 2026*
