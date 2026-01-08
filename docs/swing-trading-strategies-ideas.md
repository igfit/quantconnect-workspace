# Swing Trading Strategy Ideas (Days-Weeks Holding Period)

**Focus**: Trend-following strategies with days-to-weeks holding periods
**Approach**: Raw ideas and inspiration for backtesting (not validated claims)

---

## Category 1: Trend Following / Breakout Strategies

### 1. Clenow Momentum Ranking (Stocks on the Move)

**Concept**: Rank stocks by momentum quality, buy top performers, use risk parity sizing.

**Ranking Formula**:
```
Score = Annualized Slope of 90-day Exponential Regression × R²
```

**Rules**:
- Trade once per week (same day each week)
- Buy top 20% of S&P 500 by momentum score
- Position size: (Account × 0.001) / ATR(20)
- **Market filter**: Only buy when S&P 500 > 200 SMA
- **Stock filter**: Stock must be > 100 SMA, no gaps > 15%
- Rebalance positions every 2 weeks
- Hold 10-30 positions

**Why it might work**: Momentum persistence is well-documented. R² filter ensures smooth trends (not choppy).

**Source**: Andreas Clenow - "Stocks on the Move"

---

### 2. Donchian Channel Breakout (Turtle-Style)

**Concept**: Price breaking N-day highs signals trend continuation.

**Rules**:
- Entry: Close > 20-day high
- Exit: Close < 10-day low
- Position sizing: ATR-based (risk 1-2% per trade)
- **Double Donchian variant**: 55/20 channels for longer holds

**Swing Timeframe**: Hold days to weeks until 10-day low breaks

**Filter Ideas**:
- Volume confirmation (>50% above average)
- Only trade when ADX > 25
- RSI > 50 at breakout

**Source**: Curtis Faith - "Way of the Turtle"

---

### 3. 52-Week High Breakout

**Concept**: Stocks making new 52-week highs tend to continue (institutional buying).

**Statistics**:
- 68% of breakouts continue in same direction
- Average gain: 9.2% over 27 trading days
- 31% failure rate within 3 days (mostly on low volume)

**Rules**:
- Entry: Close > 52-week high on volume >50% above average
- Stop: Below the breakout candle low or 5-8%
- Target: Trail with ATR stop or exit after 4-6 weeks
- Filter: 50 SMA > 200 SMA (confirmed uptrend)

**Source**: Multiple (ChartMill, Stockopedia momentum research)

---

### 4. Mark Minervini SEPA / VCP (Volatility Contraction Pattern)

**Concept**: Buy stocks in Stage 2 uptrends that show decreasing volatility (supply drying up).

**Trend Template Requirements**:
- Price > 50, 150, and 200 SMA
- 200 SMA trending up for >1 month
- 50 SMA > 150 SMA > 200 SMA
- Price within 25% of 52-week high
- Relative Strength > 70

**VCP Entry**:
- Look for 3-5 contractions in price range
- Each pullback smaller than previous
- Enter on breakout from final contraction
- Volume should spike on breakout day (>50% above average)

**Risk Management**:
- Max stop: 7-8% from entry
- Never risk >1% of capital per trade
- Trailing stop as price advances

**Holding Period**: Days to weeks (sell if setup fails or hits trailing stop)

**Source**: Mark Minervini - "Trade Like a Champion"

---

### 5. Darvas Box Method

**Concept**: Buy stocks making new highs that consolidate in a "box" before breaking out again.

**Rules**:
- Stock must be making new 52-week highs with high volume
- Define "box" as consolidation range (highest high / lowest low of consolidation)
- Entry: Price breaks above box top
- Stop: Just below box bottom
- Trail stop: Create new boxes as price advances

**Historical Performance**:
- Works best in strong bull markets
- Weekly timeframe often better than daily (10.5% avg gain, 49% win rate on ETFs)

**Source**: Nicolas Darvas - "How I Made $2,000,000 in the Stock Market"

---

### 6. NR7 (Narrow Range 7) Breakout

**Concept**: After volatility contraction (narrowest range in 7 days), expect expansion.

**Rules**:
- Identify NR7 day: Today's range < previous 6 days' ranges
- Entry: Buy break above NR7 high (or short below NR7 low)
- Stop: Opposite side of NR7 bar
- Exit: 6 bars after breakout (or trail with ATR)
- Filter: Trade in direction of 89 SMA

**Holding Period**: 3-10 days typically

**Risk**: Higher whipsaw risk - use volume confirmation

**Source**: Toby Crabel - "Day Trading with Short Term Price Patterns"

---

## Category 2: Trend Following with Indicators

### 7. Chandelier Exit System

**Concept**: ATR-based trailing stop that lets winners run while cutting losers.

**Formula**:
```
Chandelier Long = 22-day High - (ATR(22) × 3)
Chandelier Short = 22-day Low + (ATR(22) × 3)
```

**Rules**:
- Entry: Use another method (breakout, momentum, etc.)
- Exit long: Price closes below Chandelier Long line
- Exit short: Price closes above Chandelier Short line
- Adjust multiplier: 2.5-3 for normal stocks, 4-5 for high volatility

**Key Insight**: 3× ATR assumes trend reversal is likely only when price moves against trend by 3× normal volatility.

**Source**: Charles Le Beau, Alexander Elder

---

### 8. SuperTrend System

**Concept**: Simple trend-following indicator combining ATR with price action.

**Default Settings**: Period 10, Multiplier 3

**Rules**:
- Long: Price breaks above SuperTrend line (turns green)
- Short: Price breaks below SuperTrend line (turns red)
- Exit: When SuperTrend changes color
- Best on: 4H or Daily charts (fewer false signals)

**Holding Period**: Days to weeks until trend reverses

---

### 9. Hull Moving Average (HMA) System

**Concept**: Faster-responding MA that reduces lag while maintaining smoothness.

**Rules**:
- Long: HMA turns up and price > HMA
- Short: HMA turns down and price < HMA
- Exit: HMA reverses direction
- Settings: 50-period for swing trading

**Crossover Variant**:
- Fast HMA (10) crosses above slow HMA (50) = Buy
- Fast HMA (10) crosses below slow HMA (50) = Sell

**Source**: Alan Hull (2005)

---

### 10. Elder Impulse System

**Concept**: Color-coded bars combining EMA trend + MACD momentum.

**Components**:
- 13-period EMA (trend)
- MACD Histogram (momentum)

**Bar Colors**:
- **Green**: EMA rising AND MACD histogram rising = Strong buy
- **Red**: EMA falling AND MACD histogram falling = Strong sell
- **Blue**: Mixed signals = Neutral/hold

**Rules**:
- Buy: On green bar after red/blue bars
- Sell: On red bar after green/blue bars
- Exit: When opposite color appears (or hold through 1-2 neutral bars)
- Higher TF confirmation: Check weekly impulse before daily entry

**Source**: Alexander Elder

---

### 11. Dual/Triple Moving Average Crossover

**Concept**: Classic trend-following using MA alignment.

**Popular Combinations**:
| Style | Fast | Slow | Filter |
|-------|------|------|--------|
| Aggressive | 9 EMA | 21 EMA | - |
| Standard | 20 SMA | 50 SMA | 200 SMA |
| Conservative | 50 SMA | 200 SMA | - |

**Rules**:
- Long: Fast > Slow AND Price > Filter
- Short: Fast < Slow AND Price < Filter
- Exit: Crossover in opposite direction

**Holding Period**: Weeks to months depending on settings

---

### 12. Linear Regression Channel Trading

**Concept**: Price tends to revert to regression line while respecting channel boundaries.

**Rules**:
- Calculate linear regression of 50+ bars
- Upper/Lower bands = ±2 standard deviations
- Long: Price touches lower band in upward-sloping channel
- Short: Price touches upper band in downward-sloping channel
- Exit: Price returns to regression line or opposite band

**Filter**: Only trade when slope is significant (avoid flat channels)

---

## Category 3: Momentum Indicators

### 13. CTA-Style Trend Following

**Concept**: Managed futures approach using multiple timeframes and assets.

**Signal Generation**:
- Blend 3, 6, 9, 12-month momentum signals
- Volatility-weight the blend
- Trade across equities, bonds, commodities, FX

**Position Sizing**:
```
Size = Target Vol / Asset Vol
```

**Why it works**: Behavioral biases (herding, anchoring) cause trends to persist.

**Timeframe**: DUNN Capital uses 100-250 day signals ("trend sweet spot")

---

### 14. Momentum Burst (Stockbee Method)

**Concept**: Catch 8-20% moves in 3-5 days after volatility contraction.

**Setup Criteria**:
- Stock had a strong move up (>4% day) recently
- Now consolidating within 5% of 21 EMA
- Volume dried up during consolidation
- Bollinger Band squeeze or narrow range bars

**Entry**:
- Anticipation: Enter during consolidation, expecting burst
- Confirmation: Enter after 4-5% move on expanding volume

**Exit**: 8-20% gain or when momentum stalls

**Stop**: Below consolidation low or 1-2%

**Source**: Pradeep Bonde (Stockbee)

---

### 15. True Strength Index (TSI) Crossover

**Concept**: Double-smoothed momentum oscillator with signal line.

**Settings**: TSI(25, 13) with 7-period signal line

**Rules**:
- Long: TSI crosses above signal line AND TSI > 0
- Short: TSI crosses below signal line AND TSI < 0
- Exit: Opposite crossover
- Divergence: TSI diverging from price signals reversal

**Timeframe**: Daily chart, 4-7 day holds typical

---

### 16. Know Sure Thing (KST) + Coppock Curve

**Concept**: Multi-timeframe ROC indicator for identifying trend changes.

**KST Components**: Weighted sum of 10, 15, 20, 30-period ROCs

**Rules**:
- Long: KST crosses above signal line from below zero
- Exit: KST crosses below signal line
- Coppock confirmation: Coppock Curve > 0 aligns with KST

**Best use**: Monthly for major trend turns, weekly for swing trades

---

### 17. Aroon Indicator System

**Concept**: Time-based indicator showing how recently price made high/low.

**Signals**:
- Aroon Up > 70 AND Aroon Down < 30 = Strong uptrend
- Aroon Up crosses above Aroon Down = Bullish
- Entry: On pullback when Aroon Up still > 50

**Exit**: Aroon Up drops below 50 while Aroon Down rises

---

### 18. Chande Momentum Oscillator (CMO)

**Concept**: Measures momentum as ratio of ups vs downs.

**Settings**: CMO(20) with 9-period signal line

**Rules**:
- Long: CMO crosses above signal AND CMO > 0
- Short: CMO crosses below signal AND CMO < 0
- Overbought: CMO > 50 (caution, don't short)
- Oversold: CMO < -50 (caution, don't buy)

**Best for**: Swing trading on 4H+ charts

---

## Category 4: Price Action / Structure Based

### 19. Higher High / Higher Low Trend Trading

**Concept**: Trade in direction of market structure.

**Rules**:
- Identify uptrend: 2+ consecutive HH and HL
- Entry: At formation of new HL (pullback entry)
- Stop: Below the HL
- Target: Previous HH or trail with ATR

**Exit Rules**:
- Close if price makes lower low (trend broken)
- Or trail stop 1 ATR below each new HL

---

### 20. Swing Point Breakout

**Concept**: Trade breaks of significant swing highs/lows.

**Rules**:
- Mark major swing points (use 5-bar pivot)
- Long entry: Close above prior swing high
- Short entry: Close below prior swing low
- Stop: Below/above the breakout swing point
- Target: Distance equal to prior swing

**Quality Filter**: Larger swing-to-swing distance = stronger signal

---

### 21. MACD Histogram Divergence

**Concept**: Histogram divergence signals momentum shift before price.

**Rules**:
- Bullish divergence: Price makes lower low, MACD histogram makes higher low
- Wait for histogram to turn positive
- Entry: First green histogram bar after divergence
- Stop: Below the price low
- Exit: MACD histogram starts declining OR price reaches target

**Note**: Divergences work better on larger timeframes (daily/weekly)

---

## Category 5: Seasonality / Timing Filters

### 22. Weekly Chart Momentum (13/26 Week Lookback)

**Concept**: Long-term trend identification using weekly momentum.

**Rules**:
- Uptrend: Current price > price 13 weeks ago AND price 26 weeks ago
- Downtrend: Current price < price 13 weeks ago AND price 26 weeks ago
- Only take long positions in uptrends
- Hold trades for weeks to months

---

### 23. Regime-Filtered Trend Following

**Concept**: Only trade trend strategies when market regime is favorable.

**Regime Detection**:
- S&P 500 > 200 SMA = Bull regime (trade longs)
- S&P 500 < 200 SMA = Bear regime (cash or shorts only)
- VIX < 20 = Low vol regime (trend strategies work)
- VIX > 30 = High vol regime (reduce position sizes)

**Implementation**: Apply any trend strategy but filter trades by regime.

---

## Implementation Priority for QuantConnect

### Tier 1: Try First (Clear Rules, Good Edge Hypothesis)
| Strategy | Complexity | Holding Period |
|----------|------------|----------------|
| Clenow Momentum | Medium | Weeks |
| Donchian Breakout | Low | Days-Weeks |
| Minervini VCP | Medium | Days-Weeks |
| Chandelier Exit | Low | Days-Weeks |
| Elder Impulse | Low | Days-Weeks |

### Tier 2: Worth Testing (Interesting Concepts)
| Strategy | Complexity | Note |
|----------|------------|------|
| 52-Week High Breakout | Low | Needs volume filter |
| NR7 Breakout | Low | Higher whipsaw risk |
| Momentum Burst | Medium | Short holding (3-5 days) |
| HMA System | Low | Test vs SMA systems |
| TSI Crossover | Low | Good momentum filter |

### Tier 3: Research Ideas (Less Defined)
- Linear Regression Channel
- KST + Coppock Curve
- Aroon system
- Swing Point breakouts

---

## Key Themes Across All Strategies

1. **Trend Alignment**: Almost all strategies require price > 200 SMA or similar filter
2. **Volume Confirmation**: Breakouts without volume often fail
3. **Volatility Awareness**: ATR-based stops adapt to market conditions
4. **Multiple Timeframes**: Weekly trend + daily entry often mentioned
5. **Risk Management**: 1-2% risk per trade, 7-8% max stop loss

---

## Sources for Further Research

- Andreas Clenow - "Stocks on the Move" (momentum ranking)
- Mark Minervini - "Trade Like a Champion" (VCP, SEPA)
- Alexander Elder - "Trading for a Living" (Impulse, Force Index)
- Curtis Faith - "Way of the Turtle" (Donchian breakouts)
- Toby Crabel - "Day Trading with Short Term Price Patterns" (NR7)
- Pradeep Bonde - Stockbee blog (Momentum Burst)
- Linda Raschke & Larry Connors - "Street Smarts" (multiple setups)
- TradingView Scripts Library - Pine Script implementations
- Quantified Strategies - Backtests of most indicators
