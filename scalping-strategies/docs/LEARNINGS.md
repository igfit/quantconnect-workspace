# Scalping Strategies - Learnings & Research

Comprehensive documentation of research findings, strategy rationale, and implementation learnings for short-term systematic trading strategies.

---

## Table of Contents

1. [Strategy Philosophy](#strategy-philosophy)
2. [Mean Reversion Strategies](#mean-reversion-strategies)
3. [Intraday Strategies](#intraday-strategies)
4. [Pairs Trading](#pairs-trading)
5. [Risk Management Framework](#risk-management-framework)
6. [Backtesting Methodology](#backtesting-methodology)
7. [Common Pitfalls](#common-pitfalls)
8. [Performance Tracking](#performance-tracking)

---

## Strategy Philosophy

### Core Principles

1. **Alpha from Timing, Not Selection**
   - The goal is to profit from entry/exit timing, not from picking "winning" stocks
   - Universe is fixed (high-beta, liquid stocks) - the edge is WHEN to trade

2. **High Win Rate vs High Expectancy**
   - Mean reversion: 70-85% win rate, small gains per trade
   - Trend following: 35-45% win rate, large gains per trade
   - Both can be profitable - consistency matters more than magnitude

3. **No Hindsight Bias**
   - Parameters chosen from academic research, not backtesting
   - Walk-forward validation required before deployment
   - If it works in 2018-2020, it must also work in 2021-2024

4. **Controlled Drawdowns**
   - Target: 15-25% max drawdown
   - Position sizing limits single-trade risk
   - Time stops prevent "hoping" losers recover

### Why High-Beta Stocks?

High-beta stocks (TSLA, NVDA, AMD) are ideal for scalping because:

- **Larger price swings**: More opportunities to capture mean reversion
- **Higher volatility**: Creates oversold/overbought conditions more frequently
- **Strong trends**: When trends form, they persist (momentum works)
- **High liquidity**: Tight spreads, easy to enter/exit

**Caution**: High beta also means larger drawdowns. Risk management is critical.

---

## Mean Reversion Strategies

### RSI(2) Pullback

**Thesis**: Extreme short-term oversold conditions (RSI(2) < 10) in trending stocks create bounce opportunities.

**Why It Works**:
- RSI(2) is extremely sensitive - only reaches <10 during capitulation selling
- Most capitulation is emotional, not fundamental
- Trend filter (200 SMA) ensures we buy pullbacks, not falling knives

**Academic Basis**: Larry Connors' "Short-Term Trading Strategies That Work"

**Expected Performance**:
| Metric | Target |
|--------|--------|
| Win Rate | 70-80% |
| Avg Gain | 2-4% |
| Avg Loss | 2-3% |
| Sharpe | 0.8-1.2 |

**Key Parameters**:
```python
RSI_PERIOD = 2          # Very short-term (academic recommendation)
RSI_OVERSOLD = 10       # Extreme oversold only
RSI_EXIT = 70           # Exit when mean reverted
SMA_PERIOD = 200        # Standard trend filter
MAX_HOLDING_DAYS = 5    # Time stop
STOP_LOSS = 3%          # Hard stop
```

**Why These Specific Values**:
- RSI(2) is academic standard - shorter periods are too noisy
- RSI < 10 catches only ~5% of bars (extreme events)
- 200 SMA is the institutional "line in the sand" for trend
- 5-day time stop captures most mean reversion (90% fill within 5 days)

---

### Connors RSI

**Thesis**: Multi-factor approach is more robust than single indicators.

**Formula**:
```
ConnorsRSI = (RSI(3) + StreakRSI(2) + PercentRank(100)) / 3
```

**Components Explained**:

1. **RSI(3)**: Short-term relative strength
   - Standard RSI with 3-day period
   - Captures momentum extremes

2. **StreakRSI(2)**: Streak exhaustion
   - Counts consecutive up/down days
   - Takes RSI of the streak values
   - High value = streak is "tired"

3. **PercentRank(100)**: Position in range
   - Where is current price vs last 100 days?
   - Low = near bottom of range
   - High = near top of range

**Why Multi-Factor Works**:
- Each component captures different information
- Reduces false signals from any single indicator
- Connors Research claims 75%+ win rate

**Key Parameters**:
```python
RSI_PERIOD = 3
STREAK_PERIOD = 2
RANK_PERIOD = 100
ENTRY_THRESHOLD = 15    # All three components must be low
EXIT_THRESHOLD = 70
```

---

### Bollinger Band Mean Reversion

**Thesis**: Price touching lower BB with RSI confirmation = high-probability bounce.

**Why It Works**:
- BBs capture ~95% of price action within 2 std devs
- Lower band touch is statistically rare
- RSI confirmation filters out "waterfall" declines

**Key Insight**: Exit at middle band, not upper band
- Captures reliable 1-2% gains
- Avoids waiting for rare overbought conditions
- Higher trade frequency = more opportunities

**Parameters**:
```python
BB_PERIOD = 20          # Standard
BB_STD = 2.0            # Standard
RSI_PERIOD = 14         # Standard for confirmation
RSI_THRESHOLD = 35      # Not extreme, just oversold
```

---

## Intraday Strategies

### Gap Fade Strategy

**Thesis**: Large overnight gaps (>2%) without news tend to partially fill.

**Why Gaps Fade**:
1. **After-hours illiquidity**: Prices overshoot in thin markets
2. **Retail overreaction**: Emotional trading at open
3. **Institutional mean reversion**: Algos fade gaps algorithmically

**Key Implementation Details**:

```python
# Only trade in first 30 minutes
if self.time.hour >= 10:
    return

# 2% minimum gap
GAP_THRESHOLD = 0.02

# Exit at 50% fill, not 100%
# Most reliable target - 75%+ of gaps fill this much
FILL_TARGET = 0.50

# Tight stop - gaps that don't fill often expand
STOP_LOSS = 0.015  # 1.5%
```

**Critical Rules**:
1. FLAT OVERNIGHT - never hold gap trades into next day
2. Skip gaps with earnings/news (they often don't fill)
3. Higher volume at open = more reliable signal

---

### VWAP Reversion

**Thesis**: Price significantly below VWAP attracts institutional buying.

**Why VWAP Matters**:
- VWAP = where institutional money actually traded
- Institutions benchmark to VWAP
- Price below VWAP = "cheap" relative to day's average

**Key Implementation**:

```python
# Wait for VWAP to stabilize
if self.time.hour == 9 and self.time.minute < 45:
    return

# 1.5% below VWAP is significant
VWAP_DEVIATION = 0.015

# RSI confirmation prevents buying falling knives
RSI_OVERSOLD = 30

# Exit AT VWAP, not above
# Most reliable target
```

**Best Conditions**:
- Mid-day (11am-2pm) - VWAP stable, volume moderate
- No major news flow
- Broad market not crashing

---

## Pairs Trading

### NVDA/AMD Pair

**Thesis**: Correlated stocks that temporarily diverge will revert to their historical relationship.

**Why NVDA/AMD**:
- Same sector (semiconductors)
- Similar customer base
- High historical correlation (>0.8)
- Both high-beta, liquid

**The Math**:

```python
# Spread calculation
Spread = NVDA_price - (hedge_ratio * AMD_price)

# Z-score for entry/exit
Z = (Spread - Mean(60)) / StdDev(60)

# Entry at 2 std devs
if Z > 2.0:
    # Spread too wide - short NVDA, long AMD
elif Z < -2.0:
    # Spread too narrow - long NVDA, short AMD

# Exit at mean reversion
if abs(Z) < 0.5:
    # Close both legs
```

**Hedge Ratio**:
- Calculated via regression: `hedge_ratio = Cov(NVDA, AMD) / Var(AMD)`
- Updates daily with 60-day rolling window
- Ensures dollar-neutral position

**Risk Considerations**:
- Pairs can "break" during major events (earnings divergence)
- Stop at Z > 3.5 to limit losses if spread keeps widening
- 20-day time stop - if no reversion, exit

---

## Risk Management Framework

### Position Sizing

**Fixed Dollar Amount** (recommended for scalping):
```python
position_size = $20,000 per trade
# With $100K capital, 5 max positions = $100K max exposure
```

**Why Not Percentage**:
- Scalping profits are small - need adequate size to overcome commissions
- Fixed dollar = consistent risk per trade
- Easier to track and manage

### Stop Loss Philosophy

**For Mean Reversion**:
- Hard stop (3-4%) + Time stop (5-7 days)
- Mean reversion either works quickly or doesn't work
- Don't let small loss become big loss

**For Momentum/Breakout**:
- Trailing stop (2x ATR)
- Let winners run
- Cut losers at first sign of failure

**For Pairs**:
- Z-score stop (3.5 std devs)
- If spread keeps widening, relationship may be broken
- Time stop (20 days) - force decision

### Portfolio-Level Controls

```python
MAX_DAILY_LOSS = 3%       # Stop trading for day if hit
MAX_WEEKLY_LOSS = 5%      # Reduce size if hit
DRAWDOWN_REDUCE = 15%     # Cut position sizes 50%
DRAWDOWN_HALT = 20%       # Stop trading, review strategy
```

---

## Backtesting Methodology

### Walk-Forward Analysis

**Period Structure**:
```
Train:    2018-01-01 to 2020-12-31 (3 years)
Test:     2021-01-01 to 2022-12-31 (2 years)
Validate: 2023-01-01 to 2024-12-31 (2 years)
```

**Rules**:
1. ALL parameter selection on Train period only
2. ONE test on Test period - no re-optimization
3. ZERO changes for Validate period
4. Strategy must pass ALL periods (Sharpe > 0.8)

### Avoiding Hindsight Bias

1. **Use academic parameters**: RSI(2), BB(20,2), etc. are documented
2. **No optimization**: Pick reasonable values, don't curve-fit
3. **Parameter stability**: Neighboring values should also work
4. **Out-of-sample first**: Never peek at test data during development

### Statistical Significance

**Minimum Requirements**:
- 30+ trades (Central Limit Theorem)
- Positive in 3+ of 5 years
- Profit factor > 1.5
- Win rate appropriate for strategy type

---

## Common Pitfalls

### 1. Over-Optimization

```python
# BAD: Optimized parameters
RSI_PERIOD = 2.7
RSI_OVERSOLD = 11.3
SMA_PERIOD = 187

# GOOD: Round, standard values
RSI_PERIOD = 2      # Academic standard
RSI_OVERSOLD = 10   # Round number
SMA_PERIOD = 200    # Industry standard
```

### 2. Survivorship Bias

Always check:
- Would these stocks have been tradeable at the time?
- Were they liquid enough?
- Did they exist (IPO dates)?

### 3. Look-Ahead Bias

```python
# BAD: Using today's data for today's trade
if data[symbol].close < bb.lower_band:
    self.market_order(symbol, shares)  # Can't know close until after close!

# GOOD: Trade on next bar
self.entry_signal[symbol] = True  # Set signal
# Execute in next on_data call
```

### 4. Slippage Underestimation

```python
# Intraday needs tighter slippage
Resolution.MINUTE -> 0.02% (2 bps)
Resolution.HOUR   -> 0.05% (5 bps)
Resolution.DAILY  -> 0.10% (10 bps)
```

### 5. Commission Ignorance

IBKR model: $0.005/share, $1 minimum
- 100 shares @ $50 = $0.50 (min $1.00)
- Need sufficient position size to overcome costs

---

## Performance Tracking

### Metrics to Track

| Metric | Formula | Target |
|--------|---------|--------|
| Sharpe Ratio | (Return - Rf) / StdDev | > 0.8 |
| CAGR | (End/Start)^(1/years) - 1 | > 15% |
| Max Drawdown | Max peak-to-trough decline | < 25% |
| Win Rate | Wins / Total Trades | > 55% (MR) |
| Profit Factor | Gross Profit / Gross Loss | > 1.5 |
| Avg Win/Loss | Avg winning trade / Avg losing trade | > 1.0 |

### Trade Journal Template

```markdown
## Trade: [Symbol] - [Date]

**Strategy**: [RSI2/Connors/BB/etc.]
**Direction**: [Long/Short]
**Entry**: $XX.XX @ [time]
**Exit**: $XX.XX @ [time]
**P&L**: $XX.XX (X.X%)

**Entry Reason**:
- [Indicator values that triggered entry]

**Exit Reason**:
- [Target/Stop/Time stop]

**Notes**:
- [What worked/didn't work]
- [Would you take this trade again?]
```

---

## Future Research Areas

1. **Regime Detection**: Only trade mean reversion in range-bound markets
2. **Volatility Adjustment**: Scale position size by VIX
3. **Sector Rotation**: Apply strategies to sector ETFs
4. **Options Overlay**: Use spreads instead of stock for defined risk
5. **Machine Learning**: Predict which signals are highest probability

---

*Last updated: January 2025*
