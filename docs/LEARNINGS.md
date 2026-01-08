# QuantConnect & Strategy Development Learnings

A comprehensive guide capturing learnings from developing and testing trading strategies on QuantConnect.

---

## Table of Contents
1. [QuantConnect Platform](#quantconnect-platform)
2. [BX Trender Indicator](#bx-trender-indicator)
3. [Multi-Timeframe Analysis](#multi-timeframe-analysis)
4. [Strategy Development Insights](#strategy-development-insights)
5. [Common Pitfalls](#common-pitfalls)
6. [Best Practices](#best-practices)
7. [BX & Wave Indicator Variations](#bx--wave-indicator-variations)
8. [Wave-EWO Deep Dive](#wave-ewo-deep-dive)
9. [High-Beta Stock Testing](#high-beta-stock-testing)
10. [Complete Performance Comparison](#complete-performance-comparison)
11. [Stock Selection for Momentum Strategies](#stock-selection-for-momentum-strategies)
12. [Momentum Strategy Research Findings](#momentum-strategy-research-findings)

---

## QuantConnect Platform

### API Authentication

QuantConnect uses **SHA-256 timestamped authentication**, not simple basic auth:

```bash
# Correct authentication flow:
timestamp=$(date +%s)
hash=$(echo -n "${API_TOKEN}:${timestamp}" | openssl dgst -sha256 | awk '{print $2}')
auth=$(echo -n "${USER_ID}:${hash}" | base64 -w 0)  # -w 0 prevents newlines

# Headers required:
Authorization: Basic ${auth}
Timestamp: ${timestamp}
```

### API Gotchas

| Issue | Wrong | Correct |
|-------|-------|---------|
| Project language | `"Python"` | `"Py"` |
| Backtest name param | `name` | `backtestName` |
| Base64 encoding | `base64` | `base64 -w 0` (no newlines) |

### Weekly Consolidation

```python
# WRONG - CalendarType doesn't exist
self.consolidate(symbol, Resolution.DAILY, CalendarType.WEEK, handler)

# CORRECT
self.consolidate(symbol, Calendar.Weekly, handler)
```

### Handling None Data

```python
def on_data(self, data):
    if self.symbol not in data:
        return
    bar = data[self.symbol]
    if bar is None:  # IMPORTANT: bar can be in dict but be None
        return
```

### Warm-up Period

- EMAs need `period` bars to be ready
- Check `indicator.is_ready` before using
- Use `self.set_warm_up(days, Resolution.DAILY)` for automatic warm-up

---

## BX Trender Indicator

### Formula

```
BX = RSI(EMA_fast - EMA_slow, period) - 50

Where:
- EMA_fast = EMA(close, L1)  # Default: 5
- EMA_slow = EMA(close, L2)  # Default: 20
- RSI period = L3            # Default: 15

Result: Oscillates between -50 and +50
- BX > 0: Bullish (green)
- BX < 0: Bearish (red)
```

### Standard Parameters

| Timeframe | L1 | L2 | L3 | Use Case |
|-----------|----|----|----|---------|
| Daily (short) | 5 | 20 | 15 | Primary signals |
| Daily (long) | 20 | 50 | 15 | Trend confirmation |
| Weekly | 5 | 20 | 15 | Higher timeframe filter |

### Implementation

```python
def calculate_bx(self, closes, l1, l2, l3):
    """
    Calculate BX value from closing prices.

    CRITICAL: Requires at least L2 + L3 + 1 data points!
    For (5, 20, 15): Need 36+ closes minimum
    """
    min_len = l2 + l3 + 1
    if len(closes) < min_len:
        return None

    # Calculate EMA differences
    ema_diffs = []
    for i in range(len(closes) - l2 + 1):
        subset = closes[:l2 + i]
        fast = calc_ema(subset, l1)
        slow = calc_ema(subset, l2)
        if fast and slow:
            ema_diffs.append(fast - slow)

    if len(ema_diffs) < l3 + 1:
        return None

    # RSI of EMA differences
    rsi = calc_rsi(ema_diffs, l3)
    return (rsi - 50) if rsi else None
```

### Trading Signals

```python
# Entry: BX crosses above 0 (turns bullish)
if prev_bx < 0 and current_bx >= 0:
    buy()

# Exit: BX crosses below 0 (turns bearish)
if prev_bx >= 0 and current_bx < 0:
    sell()
```

---

## Multi-Timeframe Analysis

### The Buffer Size Bug

**Problem**: Original implementation used `RollingWindow(25)` for weekly bars, but BX calculation requires more data.

```python
# BUG
self.weekly_bars = RollingWindow[TradeBar](25)  # Too small!

# MATH
# BX needs: L2 closes for slow EMA + L3+1 for RSI
# With (5, 20, 15): 20 + 16 = 36 minimum

# FIX
min_bars = L2 + L3 + 1  # = 36
self.weekly_bars = RollingWindow[TradeBar](min_bars + 5)  # Add buffer
```

### MTF Performance Comparison (TSLA 2020-2024)

| Strategy | Return | Sharpe | Max DD | Trades |
|----------|--------|--------|--------|--------|
| Daily Only | **293%** | **0.90** | 45.9% | 67 |
| Weekly BX (5,20,15) | 52.5% | 0.36 | **36.8%** | 32 |
| Weekly BX (3,10,8) | -7.9% | -0.03 | 46.0% | 33 |
| Weekly EMA filter | 86.8% | 0.48 | 45.0% | 41 |
| Weekly SMA filter | 16.8% | 0.17 | 45.4% | 43 |

### Key MTF Findings

1. **Weekly filters hurt high-momentum stocks** - TSLA's best moves get filtered out
2. **Shorter weekly params are too noisy** - (3,10,8) lost money
3. **Simple EMA crossover > full BX** for weekly filter
4. **Drawdown reduction is minimal** - not worth the return sacrifice
5. **Daily timeframe is sufficient** for high-beta stocks

### When MTF Might Help

- Lower volatility assets (SPY, bonds)
- Mean-reversion strategies
- Longer holding periods
- Risk-averse portfolios prioritizing drawdown over returns

---

## Strategy Development Insights

### Optimal Stock Universe for BX Trender

**Best performers:**
- High-beta stocks (beta > 1.0)
- Growth/momentum names (TSLA, NVDA, AMD)
- High volatility assets (COIN, crypto-related)

**Why:** BX is a trend-following indicator. High-beta stocks have stronger trends that BX can capture effectively.

### Win Rate vs Profit/Loss Ratio

All BX strategies showed:
- **Low win rate**: ~38-45%
- **High P/L ratio**: 2.5-3.0x

This is characteristic of trend-following systems:
- Many small losses (false signals)
- Few large wins (catching major trends)
- Overall profitable due to asymmetric payoffs

### Portfolio Diversification Effect

| Approach | Return | Sharpe | Max DD |
|----------|--------|--------|--------|
| Single stock (TSLA) | 293% | 0.90 | 45.9% |
| Portfolio (4 stocks) | 133% | 0.85 | 41.3% |

Trade-off: Lower return but better Sortino (0.97 vs 0.85) and reduced single-stock risk.

### Position Sizing

```python
# Equal weight for portfolio
weight = 1.0 / len(tickers)  # 25% each for 4 stocks

# Full allocation for single stock
self.set_holdings(symbol, 1.0)
```

---

## Common Pitfalls

### 1. Insufficient Data Buffer

```python
# WRONG: Will return None forever
self.window = RollingWindow[float](20)
# ... later trying to calculate indicator needing 30+ values

# RIGHT: Calculate minimum requirement
min_required = period1 + period2 + buffer
self.window = RollingWindow[float](min_required)
```

### 2. Not Checking Indicator Readiness

```python
# WRONG
value = self.ema.current.value  # Might be garbage

# RIGHT
if self.ema.is_ready:
    value = self.ema.current.value
```

### 3. F-String Formatting with Conditionals

```python
# WRONG - causes format error
self.debug(f"Value: {x:.2f if x else 'None'}")

# RIGHT
x_str = f"{x:.2f}" if x is not None else "None"
self.debug(f"Value: {x_str}")
```

### 4. List Reversal for RollingWindow

```python
# RollingWindow stores newest first (index 0 = most recent)
# For chronological order, reverse:
values = [window[i] for i in range(window.count)]
values.reverse()  # Now oldest first
```

### 5. Consolidator Handler Scope

```python
# WRONG - all symbols use same handler with wrong symbol
for symbol in symbols:
    self.consolidate(symbol, Calendar.Weekly, self.handler)

# RIGHT - capture symbol in lambda
for symbol in symbols:
    self.consolidate(symbol, Calendar.Weekly,
                     lambda bar, s=symbol: self.handler(bar, s))
```

---

## Best Practices

### 1. Always Set Benchmark

```python
def initialize(self):
    self.add_equity("SPY", Resolution.DAILY)
    self.set_benchmark("SPY")  # Enables alpha/beta calculations
```

### 2. Log Key Metrics

```python
def on_end_of_algorithm(self):
    self.log(f"Final: ${self.portfolio.total_portfolio_value:,.2f}")
```

### 3. Debug Strategically

```python
# Log state changes, not every tick
if turned_bullish:
    self.debug(f"{self.time}: Signal change - BX: {bx:.1f}")
```

### 4. Handle Edge Cases

```python
# Division by zero in RSI
if avg_loss == 0:
    return 100  # All gains, RSI = 100

# Empty data
if not data or symbol not in data:
    return
```

### 5. Document Strategy Parameters

```python
class MyStrategy(QCAlgorithm):
    """
    Strategy: BX Trender on High-Beta Stocks

    Parameters:
        - L1, L2, L3: 5, 20, 15 (BX calculation)
        - Universe: TSLA, NVDA, AMD, COIN
        - Position: Equal weight (25% each)

    Entry: Daily BX crosses above 0
    Exit: Daily BX crosses below 0
    """
```

### 6. Test Incrementally

1. Single stock, daily only → verify basic logic
2. Add weekly filter → compare performance
3. Expand to portfolio → test diversification
4. Optimize parameters → avoid overfitting

---

## Strategy Template

```python
from AlgorithmImports import *
import numpy as np

class MyStrategy(QCAlgorithm):
    """
    [Strategy description]

    Entry: [conditions]
    Exit: [conditions]
    Universe: [assets]
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        # Add securities
        self.symbol = self.add_equity("SPY", Resolution.DAILY).symbol

        # Indicators
        self.indicator = self.ema(self.symbol, 20, Resolution.DAILY)

        # State
        self.prev_value = None

        # Benchmark & warmup
        self.set_benchmark("SPY")
        self.set_warm_up(50, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up:
            return
        if self.symbol not in data or data[self.symbol] is None:
            return
        if not self.indicator.is_ready:
            return

        # Trading logic here
        current = self.indicator.current.value

        if self.prev_value is not None:
            # Signal detection
            pass

        self.prev_value = current

    def on_end_of_algorithm(self):
        self.log(f"Final: ${self.portfolio.total_portfolio_value:,.2f}")
```

---

## BX & Wave Indicator Variations

### Overview

Tested multiple variations of the BX Trender and new Wave-based indicators on high-beta stocks (TSLA, NVDA) from 2020-2024.

### Variation Strategies Tested

| Strategy | Description | File |
|----------|-------------|------|
| BX-ATR | EMA diff normalized by ATR before RSI | `bx_atr_normalized.py` |
| BX-Stochastic | Stochastic applied to BX values (80/20 levels) | `bx_stochastic.py` |
| BX-Connors | Multi-factor: BX_short + BX_medium + StreakRSI + ROC% | `bx_connors.py` |
| BX-Divergence | Price vs BX divergence detection | `bx_divergence.py` |
| Wave-EWO | Elliott Wave Oscillator (5/34 SMA) + RSI filter | `wave_ewo.py` |
| Wave-Adaptive | ATR-normalized wave with dynamic thresholds | `wave_adaptive.py` |
| Wave-Supertrend | Wave + SuperTrend trailing stop | `wave_supertrend.py` |

### TSLA Results (2020-2024)

| Strategy | Return | Sharpe | Drawdown | Win Rate |
|----------|--------|--------|----------|----------|
| **Baseline (BX Daily)** | 293% | 0.90 | 45.9% | ~40% |
| BX-ATR | 331% | 0.96 | 48.7% | 48% |
| BX-Stochastic | 552% | 1.18 | 59.9% | 59% |
| BX-Connors | 730% | 1.34 | 37.4% | 40% |
| BX-Divergence | 192% | 0.72 | 59.7% | 42% |
| Wave-Adaptive | 499% | 1.17 | 36.8% | 46% |
| Wave-Supertrend | 392% | 1.06 | 40.2% | 42% |
| **Wave-EWO** | **858%** | **1.50** | **34.1%** | 47% |

### NVDA Results (2020-2024) - Robustness Test

| Strategy | Return | Sharpe | Drawdown | Win Rate |
|----------|--------|--------|----------|----------|
| Wave-EWO | 294% | 0.97 | 45.1% | 32% |
| BX-Connors | 62% | 0.38 | 58.3% | 40% |

### Key Findings

1. **Wave-EWO is the best overall performer**
   - Highest return (858% TSLA), highest Sharpe (1.50)
   - Lowest drawdown (34.1%)
   - Most robust across different stocks (294% NVDA vs 62% for BX-Connors)

2. **Simpler indicators often outperform complex ones**
   - EWO uses simple SMA difference (5/34)
   - BX uses EMA + RSI combination
   - Less complexity = more robustness

3. **BX-Connors is stock-specific**
   - Excellent on TSLA (730%)
   - Poor on NVDA (62%)
   - May be overfitted to TSLA's characteristics

4. **ATR normalization helps with drawdowns**
   - Wave-Adaptive: 36.8% DD
   - BX-ATR: 48.7% DD (vs 45.9% baseline)

5. **Divergence detection didn't improve results**
   - BX-Divergence underperformed baseline
   - Complexity without benefit

### Wave-EWO Implementation

```python
# Elliott Wave Oscillator (5/34 SMA diff) with RSI filter
self.sma_fast = self.sma(symbol, 5, Resolution.DAILY)
self.sma_slow = self.sma(symbol, 34, Resolution.DAILY)
self.rsi_indicator = self.rsi(symbol, 14, MovingAverageType.WILDERS, Resolution.DAILY)

# Entry: EWO crosses above 0 AND RSI > 40
if prev_ewo < 0 and ewo >= 0 and rsi >= 40:
    buy()

# Exit: EWO crosses below 0 OR RSI < 30
if ewo < 0 or rsi < 30:
    sell()
```

### API Gotcha: Indicator Signatures

```python
# WRONG - missing MovingAverageType
self.atr_indicator = self.atr(symbol, period, Resolution.DAILY)
self.rsi_indicator = self.rsi(symbol, period, Resolution.DAILY)

# CORRECT - include MovingAverageType
self.atr_indicator = self.atr(symbol, period, MovingAverageType.SIMPLE, Resolution.DAILY)
self.rsi_indicator = self.rsi(symbol, period, MovingAverageType.WILDERS, Resolution.DAILY)
```

### Recommendations

1. **Use Wave-EWO for high-beta stocks** - Best risk-adjusted returns
2. **Test on multiple stocks** before deploying - BX-Connors showed poor robustness
3. **Keep indicators simple** - Complexity doesn't guarantee better performance
4. **Add RSI filter** - Improves entry timing significantly

---

## Wave-EWO Deep Dive

### What is Wave-EWO?

Wave-EWO (Elliott Wave Oscillator) is a **trend-following momentum strategy** that combines:
1. **EWO**: Difference between fast and slow Simple Moving Averages
2. **RSI Filter**: Momentum confirmation to reduce false signals

```
EWO = SMA(5) - SMA(34)

Entry: EWO crosses above 0 AND RSI > 40
Exit: EWO crosses below 0 OR RSI < 30
```

### Why 5 and 34?

These are **Fibonacci numbers** used in Elliott Wave analysis:
- **5**: Captures immediate price action (~1 week)
- **34**: Filters noise, represents ~7 weeks of trading

### Signal Logic Explained

```
EWO Value
    │
  + │         ╭────╮
    │        ╱      ╲         HOLD (long position)
  0 │───────╱────────╲───────────────
    │      ↑          ↓
  - │   BUY         SELL
    │
    └────────────────────────────── Time
```

**The RSI filter prevents:**
- Entering weak trends (RSI < 40 = no momentum)
- Holding through momentum collapse (RSI < 30 = exit early)

### Why Wave-EWO Outperforms BX Trender

| Aspect | BX Trender | Wave-EWO |
|--------|------------|----------|
| Fast MA | EMA(5) | SMA(5) |
| Slow MA | EMA(20) | SMA(34) |
| Signal | RSI of EMA diff | Zero-cross + RSI filter |
| Complexity | Higher | Lower |
| Robustness | Stock-specific | Works across stocks |

**Key insight**: Simpler indicators with longer lookback periods are more robust.

### Complete Implementation

```python
from AlgorithmImports import *

class WaveEWO(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.symbol = self.add_equity("TSLA", Resolution.DAILY).symbol

        # EWO params (Fibonacci)
        self.sma_fast = self.sma(self.symbol, 5, Resolution.DAILY)
        self.sma_slow = self.sma(self.symbol, 34, Resolution.DAILY)

        # RSI filter
        self.rsi_indicator = self.rsi(self.symbol, 14, MovingAverageType.WILDERS, Resolution.DAILY)

        self.ewo = None
        self.prev_ewo = None

        self.set_warm_up(50, Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_data(self, data):
        if self.is_warming_up or self.symbol not in data or data[self.symbol] is None:
            return
        if not self.sma_fast.is_ready or not self.sma_slow.is_ready or not self.rsi_indicator.is_ready:
            return

        # Calculate EWO
        self.ewo = self.sma_fast.current.value - self.sma_slow.current.value
        rsi_val = self.rsi_indicator.current.value

        if self.prev_ewo is not None:
            crossed_bullish = self.prev_ewo < 0 and self.ewo >= 0
            crossed_bearish = self.prev_ewo >= 0 and self.ewo < 0

            # Entry: EWO crosses bullish AND RSI confirms
            if crossed_bullish and rsi_val >= 40:
                if not self.portfolio[self.symbol].invested:
                    self.set_holdings(self.symbol, 1.0)

            # Exit: EWO crosses bearish OR RSI fails
            elif self.portfolio[self.symbol].invested:
                if crossed_bearish or rsi_val < 30:
                    self.liquidate(self.symbol)

        self.prev_ewo = self.ewo
```

### Trade Characteristics

| Metric | Typical Value | Explanation |
|--------|---------------|-------------|
| Win Rate | 35-45% | Low, but winners are big |
| P/L Ratio | 6-7x | Winners ~6x size of losers |
| Trades/Year | ~10 | Very low turnover |
| Avg Hold | 30-60 days | Catches full trends |
| Drawdown | 34-45% | Lower than buy-hold |

---

## High-Beta Stock Testing

### Stocks Tested

Tested Wave-EWO on 5 high-beta stocks (2020-2024):

| Ticker | Company | Beta | Sector |
|--------|---------|------|--------|
| AMD | Advanced Micro Devices | ~1.8 | Semiconductor |
| COIN | Coinbase | ~2.3 | Crypto/Fintech |
| META | Meta Platforms | ~1.7 | Social/Tech |
| MSTR | MicroStrategy | ~2.5+ | Bitcoin Proxy |
| SMCI | Super Micro Computer | ~2.0+ | AI Infrastructure |

### Results Summary

| Ticker | Return | Sharpe | Drawdown | Win Rate | End Value |
|--------|--------|--------|----------|----------|-----------|
| **TSLA** | **858%** | **1.50** | 34.1% | ~35% | $958K |
| **MSTR** | **365%** | 0.91 | 76.3% | 35% | $465K |
| SMCI | 159% | 0.65 | 41.2% | ~35% | $259K |
| AMD | 145% | 0.67 | 38.9% | 45% | $245K |
| META | 139% | 0.72 | 41.1% | 35% | $239K |
| COIN | 41% | 0.40 | 59.1% | 44% | $141K |

### Key Findings

1. **TSLA remains the best performer** - unique combination of trend strength and momentum
2. **MSTR has extreme characteristics** - highest return (365%) but also extreme drawdown (76%)
3. **META has best risk-adjusted return** among new tests (0.72 Sharpe)
4. **COIN struggles** - crypto correlation creates whipsaw signals
5. **Semiconductor stocks (AMD, SMCI)** show consistent performance

### Why COIN Underperforms

```
COIN Price Action:
     ╭╮  ╭╮  ╭╮         News-driven spikes
    ╱  ╲╱  ╲╱  ╲        Sudden reversals
   ╱          ╲        No sustained trends
  ╱            ╲       EWO generates false signals
```

Crypto-correlated stocks move on:
- Bitcoin price swings (external factor)
- Regulatory news (binary events)
- Sentiment shifts (unpredictable)

**Wave-EWO needs sustained trends** - COIN doesn't provide them.

---

## Complete Performance Comparison

### All Strategies Compared (2020-2024, $100K initial)

| Strategy | Type | Orders | Start | End | Return | Sharpe | Drawdown | Win Rate |
|----------|------|--------|-------|-----|--------|--------|----------|----------|
| **Wave-EWO TSLA** | Active | ~40 | $100K | $958K | **858%** | **1.50** | 34.1% | ~35% |
| **Wave-EWO MSTR** | Active | 41 | $100K | $465K | **365%** | 0.91 | 76.3% | 35% |
| Wave-EWO SMCI | Active | ~40 | $100K | $259K | 159% | 0.65 | 41.2% | ~35% |
| Wave-EWO AMD | Active | 41 | $100K | $245K | 145% | 0.67 | 38.9% | 45% |
| Wave-EWO META | Active | 41 | $100K | $239K | 139% | 0.72 | 41.1% | 35% |
| QQQ Buy-Hold | Passive | 1 | $100K | $195K | 95% | 0.59 | 34.8% | N/A |
| DCA TSLA | Passive | 48 | $100K | $163K | 63% | 0.39 | 62.4% | N/A |
| SPY Buy-Hold | Passive | 1 | $100K | $157K | 57% | 0.43 | 33.3% | N/A |
| Wave-EWO COIN | Active | 33 | $100K | $141K | 41% | 0.40 | 59.1% | 44% |
| DCA QQQ | Passive | 48 | $100K | $133K | 33% | 0.35 | 21.7% | N/A |
| DCA SPY | Passive | 48 | $100K | $124K | 24% | 0.28 | 14.8% | N/A |

### Active vs Passive Analysis

| Comparison | Active (Wave-EWO) | Passive |
|------------|-------------------|---------|
| Best Return | TSLA 858% | QQQ 95% |
| Best Sharpe | TSLA 1.50 | QQQ 0.59 |
| Lowest Drawdown | TSLA 34.1% | DCA SPY 14.8% |
| Worst Case | COIN 41% | DCA SPY 24% |

**Key insight**: Even the worst Wave-EWO (COIN) beats most DCA strategies.

### DCA vs Lump Sum vs Active

| Approach | TSLA Return | Why? |
|----------|-------------|------|
| Wave-EWO | 858% | Captures trends, avoids crashes |
| Buy-Hold | ~500% | Full exposure to drawdowns |
| DCA | 63% | Averages into winner = dilutes gains |

**DCA underperforms on trending assets** - you keep buying at higher prices.

---

## Stock Selection for Momentum Strategies

### Ideal Characteristics for Wave-EWO

| Factor | Ideal | Avoid |
|--------|-------|-------|
| Beta | 1.5 - 2.5 | < 1.0 or > 3.0 |
| Trend Behavior | Sustained moves | Choppy/mean-reverting |
| Catalysts | Earnings, growth | News-driven, binary events |
| Sector | Tech, Growth | Utilities, REITs |
| Correlation | Market-driven | External factors (crypto) |

### Stock Tiers for Wave-EWO

**Tier 1 - Best Performers:**
- TSLA - Strong trends, retail momentum
- NVDA - AI/semiconductor cycles
- MSTR - Bitcoin proxy (if comfortable with volatility)

**Tier 2 - Solid Performers:**
- AMD - Semiconductor cycles
- META - Large-cap with trend behavior
- SMCI - AI infrastructure momentum

**Tier 3 - Avoid:**
- COIN - Crypto correlation, no sustained trends
- Meme stocks (GME, AMC) - Too erratic
- Biotech - Binary event-driven

### Beta Screening Approach

To find high-beta stocks programmatically:

```python
# Beta = Cov(stock_returns, market_returns) / Var(market_returns)

# Get 252 days of returns
stock_returns = history.loc[symbol]['close'].pct_change()
spy_returns = history.loc['SPY']['close'].pct_change()

# Calculate beta
covariance = np.cov(stock_returns, spy_returns)[0][1]
variance = np.var(spy_returns)
beta = covariance / variance

# Filter for high beta
if beta > 1.5:
    high_beta_stocks.append(symbol)
```

**Note**: QuantConnect doesn't have built-in beta screening - must calculate manually.

---

## Momentum Strategy Research Findings

### Key Academic Insights

**1. 52-Week High Effect is Dominant**
- Stocks near 52WH: **0.65%/month** returns
- Classic momentum: **0.38%/month** returns
- Industry momentum: **0.25%/month** returns
- 52WH dominates and improves upon classic momentum

Source: George & Hwang (2004), Bauer UH Research

**2. Multiple Lookback Periods Outperform Single**
- 12-month lookback: Academic standard but performs poorly recently
- 3-6 month lookback: Better in recent market conditions
- **Best practice**: Combine 1, 3, 6 month returns (Accelerating Momentum)

Source: Engineered Portfolio, Seeking Alpha research

**3. Momentum Crashes are Predictable**
- Crashes happen **1-3 months AFTER** market plunges
- Solution: Switch to contrarian after 10%+ market drop
- 52WH-neutral strategy improves skewness from -1.89 to 0.13

Source: Quantpedia, Marquette Research

### Accelerating Dual Momentum Formula

```python
# Better than classic 12-month lookback
accel_momentum = (return_1m + return_3m + return_6m) / 3

# Entry conditions (ALL must be true):
# 1. accel_momentum > 0 (absolute)
# 2. accel_momentum > SPY_accel_momentum (relative)
# 3. price > 50-day SMA (trend confirmation)
# 4. price within 25% of 52-week high (near-high filter)
```

**Performance**: $10K → $420K (1998-2017) vs $40K for S&P 500

### Volatility Targeting

Position sizing based on volatility stabilizes returns:

```python
# Target constant portfolio volatility
scaling_factor = target_volatility / recent_volatility
position_size = base_size * scaling_factor
```

**Benefits**:
- Improved Sharpe ratio
- Better drawdown management
- More consistent monthly returns

### Time-Series vs Cross-Sectional Momentum

| Type | Definition | Best When |
|------|------------|-----------|
| Time-Series | Stock's own return > 0 | Strong trending markets |
| Cross-Sectional | Stock return > peer returns | Sideways markets |

**Recommendation**: Use BOTH for robustness

### Key Sources

- [Alpha Architect - 52WH Secret](https://alphaarchitect.com/the-secret-to-momentum-is-the-52-week-high/)
- [Engineered Portfolio - ADM](https://engineeredportfolio.com/2018/05/02/accelerating-dual-momentum-investing/)
- [Quantpedia - Momentum Crashes](https://quantpedia.com/three-methods-to-fix-momentum-crashes/)
- [AQR - Case for Momentum](https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/The-Case-for-Momentum-Investing.pdf)

---

## Signal-Based Momentum Strategy (Acceleration Entry)

### Overview

The **Acceleration Entry** strategy achieved **32.94% CAGR** with **1.035 Sharpe** and only **21.1% max drawdown** by focusing on trading SIGNALS rather than stock selection.

### Core Concept

**Enter when momentum is accelerating, not just positive.**

```python
# Entry Signal
entry = (6_month_momentum > 0) AND (1_month_momentum > previous_1_month_momentum)

# Position Sizing (momentum-weighted)
weight[stock] = stock_momentum / sum(top_10_momentum)
```

### Strategy Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Lookback | 126 days (6 months) | Optimal - 3m/9m/12m all worse |
| Positions | Top 10 | Balances returns vs robustness |
| Rebalancing | Weekly (Monday) | Faster signal response |
| Regime Filter | SPY > 200 SMA | Avoids bear markets |
| Position Sizing | Momentum-weighted | Ride winners harder |

### Signal Optimization Results

| Configuration | CAGR | Sharpe | Max DD | Notes |
|---------------|------|--------|--------|-------|
| 3m lookback | 17.4% | 0.55 | 30.9% | Too noisy |
| **6m lookback** | **24.5%** | **0.76** | **28.8%** | **Optimal** |
| 9m lookback | 16.8% | 0.51 | 32.0% | Too slow |
| 12m lookback | 15.0% | 0.46 | 27.2% | Misses moves |
| Top 5 (concentrated) | 28.9% | 0.81 | 29.8% | NVDA-dependent |
| **Top 10 (balanced)** | **24.5%** | **0.76** | **28.8%** | **Robust** |
| Top 15 (diversified) | 19.9% | 0.65 | 29.5% | Diluted |
| + Acceleration filter | **32.9%** | **1.04** | **21.1%** | **Best** |

### Key Findings

1. **Acceleration > Raw Momentum**: Entering when momentum is increasing (not just positive) adds ~8% CAGR
2. **Momentum Weighting**: Allocating more to stronger momentum outperforms equal weight
3. **Weekly Rebalancing**: Faster than monthly, captures trend changes
4. **Stop-Losses Hurt**: Tested 8-15% stops - all reduced returns by cutting winners early
5. **6-Month Optimal**: Shorter is noisy, longer misses moves

### Robustness Testing (Without NVDA)

| Strategy | With NVDA | Without NVDA | CAGR Drop |
|----------|-----------|--------------|-----------|
| Top 5 | 28.9% | 17.7% | -11.2% ❌ |
| **Top 10** | **24.5%** | **21.3%** | **-3.1%** ✓ |
| Acceleration Entry | 32.9% | 28.5% | -4.5% ✓ |

**Conclusion**: Top 10 is robust. Alpha comes from signals, not single-stock dependency.

### Implementation

```python
# Key code from momentum_acceleration_entry.py

def rebalance(self):
    # Regime filter
    if self.securities[self.spy].price < self.spy_sma.current.value:
        self.liquidate()
        return

    scores = {}
    for symbol in self.symbols:
        mom = self.momentum[symbol].current.value      # 6-month ROC
        short_mom = self.short_mom[symbol].current.value  # 1-month ROC
        prev_mom = self.prev_short_mom.get(symbol, 0)

        acceleration = short_mom - prev_mom
        self.prev_short_mom[symbol] = short_mom

        # Only enter if positive momentum AND accelerating
        if mom > 0 and acceleration > 0:
            scores[symbol] = mom

    # Momentum-weighted positions
    top_symbols = sorted(scores, key=scores.get, reverse=True)[:10]
    total_mom = sum(scores[s] for s in top_symbols)
    for symbol in top_symbols:
        self.set_holdings(symbol, scores[symbol] / total_mom)
```

### Universe Generation (Hindsight-Free)

Used Claude AI to generate universe based on **features** not returns:

**Selection Criteria**:
- High beta (1.2-2.0)
- Profitable or near-profitable
- US-focused (no China risk)
- Market leaders (#1-2 in category)
- Liquid (>$5M daily volume)

**Sectors Included** (56 stocks):
- Semiconductors: NVDA, AMD, AVGO, QCOM, MU, AMAT, LRCX, KLAC, MRVL, ON
- Software: CRM, ADBE, NOW, INTU, PANW, VEEV, WDAY
- Payments: V, MA, PYPL, SQ
- Travel: BKNG, RCL, CCL, MAR, HLT, WYNN
- Energy: XOM, CVX, OXY, DVN, SLB, COP
- Consumer: TSLA, NKE, LULU, CMG, DECK

**Excluded**:
- Chinese ADRs (BABA, JD, BIDU)
- Legacy tech (IBM, ORCL, CSCO, INTC)
- Defensive (utilities, staples, REITs)

### Trade Statistics

| Metric | Acceleration Entry |
|--------|-------------------|
| Total Trades | 2,680 |
| Win Rate | 56% |
| Avg Win | +0.46% |
| Avg Loss | -0.34% |
| Profit/Loss Ratio | 1.38 |
| Risk:Reward | 1:1.38 |

### Top P&L Contributors

| Ticker | P&L | Trades |
|--------|-----|--------|
| NVDA | +$75,881 | 87 |
| TSLA | +$46,085 | 60 |
| DVN | +$33,738 | 40 |
| SHOP | +$25,030 | 56 |
| CCL | +$20,905 | 29 |

### Files

- `algorithms/strategies/momentum_acceleration_entry.py` - Main strategy
- `algorithms/strategies/momentum_acceleration_no_nvda.py` - Robustness test
- `strategy-factory/universe/claude_universe_generator.py` - Universe generation
- `strategy-factory/universe/run_generator.py` - CLI runner

---

## Future Improvements to Explore

1. **Adaptive parameters** - adjust SMA periods based on volatility regime
2. **Regime detection** - different params for bull/bear markets
3. **Risk management** - stop losses, position sizing based on ATR
4. **Sector rotation** - apply Wave-EWO to sector ETFs
5. **Options overlay** - use Wave-EWO signals for options strategies
6. **Combine Wave-EWO + SuperTrend** - use SuperTrend as trailing stop
7. **Portfolio approach** - equal weight multiple high-beta stocks
8. **Exit optimization** - test different RSI exit thresholds
9. **Volatility filter** - avoid entries during extreme VIX

---

*Last updated: January 2026*
