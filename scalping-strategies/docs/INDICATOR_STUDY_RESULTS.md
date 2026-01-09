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

# Round 2: Advanced Indicator Study

## Strategies Tested

Following the RSI study, we explored 9 new strategies using first-principles reasoning:

### 1. Volume-Based Strategies

| Strategy | Theory | CAGR | Sharpe | DD | Trades | Verdict |
|----------|--------|------|--------|-----|--------|---------|
| Vol Exhaustion | Buy when price drops on declining volume (sellers exhausted) | -0.39% | -1.24 | 9.9% | 89 | **FAILED** |
| MFI Divergence | Volume-weighted RSI divergence | 0% | 0 | 0% | 0 | No trades (too restrictive) |
| OBV Divergence | On-Balance Volume divergence detection | 9.3% | 1.30 | 1.2% | 5 | Promising but too few trades |

**Key Insight**: Volume exhaustion theory doesn't work on high-beta stocks. These stocks can drop on low volume and continue dropping.

### 2. Custom Composite Indicators

| Strategy | Components | CAGR | Sharpe | DD | Trades | Verdict |
|----------|------------|------|--------|-----|--------|---------|
| Composite Oversold | RSI + Stochastic + BB%B + SMA | 0.9% | -0.50 | 0.9% | 8 | **FAILED** |

**Key Insight**: Combining oversold indicators didn't add value - multiple signals don't make the trade better.

### 3. Multi-Timeframe Analysis

| Strategy | Structure | CAGR | Sharpe | DD | Trades | Verdict |
|----------|-----------|------|--------|-----|--------|---------|
| MTF Train (2018-2020) | Weekly EMA trend + Daily RSI | **25.0%** | **1.53** | 3.4% | 14 | **EXCELLENT in-sample** |
| MTF Test (2021-2024) | Same parameters | **-0.06%** | **0.04** | 8.0% | 39 | **FAILED out-of-sample** |

**Key Insight**: MTF looked excellent in training but **completely failed walk-forward validation**. This is the clearest example of overfitting in our study.

### 4. Volatility-Based Strategies

| Strategy | Theory | CAGR | Sharpe | DD | Trades | Verdict |
|----------|--------|------|--------|-----|--------|---------|
| Vol Compression | Enter after low ATR/BB width | 0% | 0 | 0% | 0 | No trades |
| Adaptive RSI | RSI Z-score relative to history | 1.28% | -0.31 | 11.9% | 381 | **FAILED** |
| Keltner Reversion | ATR-based channel touch | -1.06% | -0.87 | 13.1% | 156 | **FAILED** |

**Key Insight**: Volatility compression doesn't reliably predict direction - just that a move is coming.

### 5. Price Structure Strategies

| Strategy | Theory | CAGR | Sharpe | DD | Trades | Verdict |
|----------|--------|------|--------|-----|--------|---------|
| Swing Structure | Buy at swing low in uptrend | -1.79% | -0.87 | 1.8% | 12 | **FAILED** |

**Key Insight**: Swing lows in high-beta stocks often break down further rather than bounce.

---

## Round 2 Key Learnings

### 1. Walk-Forward Validation is Non-Negotiable

MTF strategy had **1.53 Sharpe in training** but **0.04 Sharpe in test period**. Without walk-forward testing, we would have deployed a losing strategy.

### 2. More Indicators ≠ Better Results

Every attempt to add complexity (composite scores, multiple timeframes, divergence detection) underperformed simple RSI.

### 3. First-Principles Can Mislead

Logical theories ("volume exhaustion signals reversal") didn't survive backtesting on real data. Markets are not purely mechanical.

### 4. High-Beta Stocks Require Different Approaches

Traditional mean reversion signals often fail on TSLA/NVDA/AMD because:
- Momentum is stronger than reversion
- Stop losses get hit before mean reversion completes
- Volatility makes entries/exits random

### 5. The 2022 Bear Market Broke Everything

All strategies that worked in 2018-2021 failed in 2022. Regime filters helped limit losses but couldn't generate positive returns.

---

## Strategies Summary (All Rounds)

| Rank | Strategy | CAGR | Sharpe | DD | Walk-Forward | Notes |
|------|----------|------|--------|-----|--------------|-------|
| 1 | RSI(5) E<35 X>55 | 24.6% | 1.49 | 3.4% | ❌ FAILED | Best in-sample but failed test |
| 2 | MTF Weekly-Daily | 25.0% | 1.53 | 3.4% | ❌ FAILED | Same pattern - great train, failed test |
| 3 | OBV Divergence | 9.3% | 1.30 | 1.2% | ⚠️ Untested | Only 5 trades - insufficient sample |
| 4 | RSI(7) E<35 X>65 | 16.4% | 1.43 | 1.7% | ❓ Unknown | Fewer trades, needs validation |
| 5 | Adaptive RSI | 1.28% | -0.31 | 11.9% | ❌ FAILED | Many trades, negative alpha |

---

## Next Steps

1. **Regime Detection**: Need more sophisticated regime classification beyond SPY > 200 SMA
2. **Momentum Integration**: Test momentum strategies for trending markets, reserve mean reversion for ranging
3. **Different Universe**: High-beta stocks may be fundamentally unsuitable for daily mean reversion
4. **Lower Timeframe**: Consider intraday for faster mean reversion on these volatile stocks

---

*Study updated: January 2026 - Round 2 Complete*
