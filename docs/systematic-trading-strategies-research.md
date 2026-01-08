# Systematic Trading Strategies Research Report

**Date**: 2026-01-08
**Objective**: Identify indicator-based trading signal alpha (not stock alpha)
**Focus**: Strategies where the edge comes from WHEN to trade, not WHAT to trade

---

## Executive Summary

This research identified **25+ distinct systematic trading strategies** with documented backtest results. The strategies are categorized by edge type (mean reversion, trend following, momentum, seasonality, volatility). Key findings:

1. **Mean Reversion strategies** show the most consistent backtested results (Williams %R, RSI-2, IBS)
2. **Dual Momentum** (Gary Antonacci) has 200+ years of validation across asset classes
3. **Seasonal anomalies** (Turn of Month, Overnight Edge) are simple but powerful
4. **Regime filtering** dramatically improves any base strategy's risk-adjusted returns

---

## Tier 1: Highest Conviction Strategies (Strong Backtest Evidence)

### 1. Larry Connors' 2-Period RSI (Mean Reversion)

**Edge Hypothesis**: Short-term oversold conditions in stocks trading above their 200-day MA revert to mean quickly.

**Backtest Results**:
- Win rate: 75-83%
- Profit factor: 2.08
- Works best on indices (SPY, QQQ)
- Mean reversion strategy with market regime filter

**Rules**:
- Entry: Close > 200 SMA AND RSI(2) < 10 (or < 15 for more trades)
- Exit: RSI(2) > 70 or close > 5-day SMA

**Modification that doubled CAGR**: Changed entry threshold from RSI < 10 to RSI < 15, doubled CAGR and cut max drawdown in half (Alvarez Quant Trading).

**Sources**: [Quantified Strategies](https://www.quantifiedstrategies.com/connors-rsi/), [Alvarez Quant Trading](https://alvarezquanttrading.com/blog/rsi2-strategy-double-returns-with-a-simple-rule-change/)

---

### 2. Williams %R Short-Term Mean Reversion

**Edge Hypothesis**: Williams %R extremes (<-90 or >-10) identify short-term reversal points.

**Backtest Results**:
- Win rate: 81%
- CAGR: 11.9% (vs. 10.3% buy & hold)
- Profit factor: 2.2
- Market exposure: only 22%
- Max drawdown: 17%
- Performed exceptionally in 2008 (98.9% return) and 2020 (43.3%)

**Rules**:
- Entry: Williams %R(2) < -90
- Exit: Close > prior day's high OR Williams %R > -30

**Key Finding**: 2-day lookback outperforms longer periods. Williams %R beats RSI and Stochastics in backtests.

**Source**: [Quantified Strategies](https://www.quantifiedstrategies.com/williams-r-trading-strategy/)

---

### 3. Internal Bar Strength (IBS) Strategy

**Edge Hypothesis**: When price closes near the bar's low (IBS < 0.1-0.2), short-term bounce is likely.

**Calculation**: IBS = (Close - Low) / (High - Low)

**Backtest Results**:
- QQQ: 742 trades, 0.56% avg return, 16.6% CAGR
- SPY: 0.41% avg gain per trade
- IBS < 0.10 filter increases performance by 58%

**Rules**:
- Entry: IBS < 0.10 AND Close > 200 EMA
- Exit: IBS > 0.98 or hold max 12-14 days

**Limitation**: Requires entry at market close (execution challenge)

**Source**: [Quantified Strategies](https://www.quantifiedstrategies.com/internal-bar-strength-ibs-indicator-strategy/)

---

### 4. Gary Antonacci's Dual Momentum (GEM)

**Edge Hypothesis**: Combine relative momentum (which asset) with absolute momentum (risk-on/risk-off).

**Backtest Results**:
- 200+ years of supporting data (Geczy & Samonov, 2015)
- During 1973-74 bear: GEM +20% while S&P -40%
- Avg 2-3 trades per year (low turnover)
- Significantly reduced max drawdown

**Rules (GEM)**:
- Monthly: Compare 12-month return of US stocks (SPY) vs International (EFA)
- Buy whichever has higher momentum
- If BOTH have negative 12-month momentum → move to bonds (BND)

**Why It Works**: Avoids bear market losses through absolute momentum filter.

**Sources**: [Optimal Momentum](https://www.optimalmomentum.com), [Quantified Strategies](https://www.quantifiedstrategies.com/dual-momentum-trading-strategy/)

---

### 5. Overnight Edge (Close-to-Open Returns)

**Edge Hypothesis**: Most equity gains occur overnight; day session has near-zero expected return.

**Backtest Results**:
- Since 1993, virtually ALL S&P 500 gains came from overnight holds
- Day trading (open→close) has negative expectancy
- Average overnight gain: 0.04% per night
- With ATR/IBS filters: 0.31% avg gain, 688 trades

**Rules**:
- Entry: Buy at market close when specific criteria met (IBS low, etc.)
- Exit: Sell at next day's open
- Filter: Close > 200 SMA improves results significantly

**Why It Works**: Retail traders don't hold overnight; market moves to lock them out.

**Source**: [Quantified Strategies](https://www.quantifiedstrategies.com/overnight-trading-strategy-sp500/)

---

### 6. Turn of Month Effect

**Edge Hypothesis**: Capital inflows from pension funds, 401k, automatic savings create buying pressure around month-end/start.

**Backtest Results**:
- CAGR: 7.2% with only 25% time in market
- Win ratio: 62%
- Max drawdown: 27%
- Academically validated over 90 years (Lakonishok & Smidt)

**Rules**:
- Entry: Buy 2 days before month end
- Exit: Sell 3 days into new month

**Academic Support**: "Most of the average annual return of the Dow Jones index over 1897-1986 was realized in the first and last days of the month."

**Source**: [Quantified Strategies](https://www.quantifiedstrategies.com/end-of-month-strategy-in-sp-500/)

---

## Tier 2: Well-Documented Strategies (Good Backtest Evidence)

### 7. Sector Momentum Rotation (Faber)

**Edge Hypothesis**: Sectors with recent strength continue outperforming (momentum persistence).

**Backtest Results**:
- Avg yearly profit: 12.8% (vs SPY 5.1%)
- Sharpe ratio: 1.16 (vs SPY 0.25)
- Max drawdown: 17% (vs SPY 55%)
- Outperformed buy-and-hold ~70% of time over 80+ years

**Rules**:
- Calculate 3-month Rate-of-Change for sector ETFs (XLK, XLF, XLU, etc.)
- Buy top 2-3 sectors
- Rebalance monthly or quarterly
- Optional: Only buy if sector > 200 SMA

**Source**: [StockCharts](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/fabers-sector-rotation-trading-strategy)

---

### 8. ADX + Moving Average "Holy Grail" (Raschke/Connors)

**Edge Hypothesis**: Strong trends (high ADX) with pullbacks to MA offer high-probability entries.

**Rules**:
- ADX(14) > 30 and rising (strong trend confirmed)
- Price touches 20-day SMA (pullback)
- Entry: At high/low of candle touching SMA
- Exit: Trailing stop or fixed target

**Validation**: Named "Holy Grail" by Linda Raschke and Larry Connors in Street Smarts.

**Key Insight**: ADX > 25 filter dramatically improves any strategy's performance.

**Source**: [Trading Setups Review](https://www.tradingsetupsreview.com/the-holy-grail-trading-setup/)

---

### 9. Money Flow Index (MFI) Mean Reversion

**Edge Hypothesis**: Volume-weighted RSI identifies stronger oversold/overbought signals.

**Backtest Results (26 years, S&P 500)**:
- Total return: 1,690% (vs 881% buy & hold)
- 23,524 trades tested
- 54% of trading days winners
- Risk-adjusted return: 26% (invested only 39% of time)

**Rules**:
- Entry: MFI(14) < 30 (oversold with volume confirmation)
- Exit: MFI > 70 or close > short-term MA
- Filter: Use with EMA trend filter for better results

**Source**: [Liberated Stock Trader](https://www.liberatedstocktrader.com/money-flow-index/)

---

### 10. Donchian Channel Breakout (Turtle Trading)

**Edge Hypothesis**: Price breaking N-day highs signals trend continuation (used by Turtle Traders).

**Backtest Results**:
- Curtis Faith testing (1996-2007): 29.4% CAGR on currencies/commodities
- S&P 500: Lower CAGR than buy & hold but significantly lower max drawdown
- QQQ, SPY, DIA (2001-2021): ~40% win rate, >200% return over 20 years

**Rules (Original Turtle)**:
- Entry: Price breaks 20-day high
- Exit: Price breaks 10-day low (or trailing stop)
- Position sizing: ATR-based (1-2% risk per trade)

**Modern Modification**: Works better with MA filter to avoid ranging markets.

**Sources**: [Quantified Strategies](https://www.quantifiedstrategies.com/turtle-trading-strategy/), [Raposa Trade](https://raposa.trade/blog/testing-turtle-trading-the-system-that-made-newbie-traders-millions/)

---

### 11. Keltner Channel Mean Reversion

**Edge Hypothesis**: Price touching lower Keltner band in uptrend = oversold bounce opportunity.

**Backtest Results**:
- Win ratio: 77-80%
- CAGR: 6.3%
- Time in market: 15%
- Profit factor: 2
- Note: Performance declined post-2016

**Rules (Mean Reversion)**:
- Entry: Close below lower Keltner band (6-day period, 1.3 ATR)
- Exit: Close above central line (20 EMA)
- Filter: Works best with trend confirmation

**Source**: [Quantified Strategies](https://www.quantifiedstrategies.com/keltner-bands-trading-strategies/)

---

### 12. VIX-Based Market Timing

**Edge Hypothesis**: Extreme VIX readings signal mean reversion opportunities in equities.

**Backtest Results**:
- VIX spot strategy: 44% risk-adjusted return
- Invested only 13% of time
- Max drawdown: 23% (vs 55% buy & hold)

**Rules**:
- Entry: VIX spike above threshold (e.g., > 30)
- Exit: VIX normalizes or fixed time exit
- Use VIX close > open as contrarian buy signal

**Key Insight**: VIX is superior to Put/Call ratio as sentiment indicator.

**Source**: [Quantified Strategies](https://www.quantifiedstrategies.com/vix-futures-trading-strategy/)

---

### 13. Rate of Change (ROC) Momentum

**Edge Hypothesis**: Short-term price momentum persists.

**Backtest Results**:
- 66% win rate on Dow 30 stocks (20 years)
- Apple: 1,795% return vs 668% buy & hold
- IBM: +76% using ROC vs -22.5% buy & hold
- With Heikin Ashi charts: 93% win rate (day trading)

**Rules**:
- Entry: ROC(9) crosses above 0 AND close > 200 SMA
- Exit: ROC crosses below 0 or fixed target

**Source**: [Liberated Stock Trader](https://www.liberatedstocktrader.com/rate-of-change-indicator/)

---

### 14. Golden Cross / Death Cross (50/200 SMA)

**Edge Hypothesis**: Long-term moving average crossovers identify regime changes.

**Backtest Results (S&P 500, 1960-present)**:
- Only 33 signals in 66 years
- Risk-adjusted return HIGHER than buy & hold
- Max drawdown cut roughly in half
- $100K → $7.2M over 66 years (excl. dividends)

**Rules**:
- Buy: 50 SMA crosses above 200 SMA (Golden Cross)
- Sell: 50 SMA crosses below 200 SMA (Death Cross)

**Weakness**: Whipsaws in choppy markets; V-shaped recoveries cause missed gains.

**Source**: [Quantified Strategies](https://www.quantifiedstrategies.com/golden-cross-trading-strategy/)

---

## Tier 3: Promising Strategies (Needs More Validation)

### 15. TQQQ/TMF Leveraged Rotation

**Backtest Results**:
- $100K → $2.7M (2010-2025)
- CAGR: 23.8%
- Sharpe: 0.95
- Max drawdown: 38.7%

**Rules**:
- Hold 50% TQQQ / 50% TMF
- Rebalance every 2 months
- Crash filter: Exit if TQQQ drops 20% in one day

**Risk**: Beta slippage, leverage decay in sideways markets.

**Source**: [Setup4Alpha](https://setup4alpha.substack.com/p/tqqq-gold-leveraged-etf-strategy-backtest)

---

### 16. Larry Williams Volatility Breakout

**Edge Hypothesis**: After periods of low volatility, directional breakouts persist.

**Rules**:
- Calculate previous day's range: (High - Low)
- Entry Price = Previous Close + (Range × 0.6)
- Exit: End of day (day trade)

**Application**: Works well on trending instruments; combine with narrow range filter.

**Source**: [Trading Volatility](https://aborysenko.com/larry-williams-volatility-breakout-strategy-explained/)

---

### 17. Market Regime Filtering (HMM-Based)

**Edge Hypothesis**: Different strategies work in different regimes; detect regime first.

**Backtest Results**:
- Max drawdown reduced from ~56% to ~24%
- Regime filter eliminates trend-following losses in high-vol periods

**Implementation**:
- Train Hidden Markov Model on volatility/returns
- In low-vol regime: allow long trades
- In high-vol regime: close positions, stay cash

**Source**: [QuantStart](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/)

---

### 18. TTM Squeeze / Bollinger Squeeze

**Edge Hypothesis**: Low volatility (BB inside Keltner) precedes explosive moves.

**Backtest Results (Optimized)**:
- With proper risk management: 87.65% profit
- Best on weekly timeframe
- Multi-timeframe alignment improves results

**Rules**:
- Squeeze: Bollinger Bands inside Keltner Channels
- Entry: When squeeze "fires" (BB breaks outside KC)
- Direction: Use momentum histogram

**Source**: [Medium - Superalgos](https://medium.com/superalgos/a-quantitative-study-of-the-bollinger-bands-squeeze-strategy-9f47143f33fb)

---

### 19. OBV + RSI Divergence

**Backtest Results**:
- ~50% of backtests showed profit factor > 2
- 5-day RSI with buy threshold 30: 73% win rate, 337 trades
- Max drawdown: 24%

**Challenge**: Divergence patterns are hard to backtest systematically.

**Source**: [Quantified Strategies](https://www.quantifiedstrategies.com/on-balance-volume-strategy/)

---

### 20. Elliott Wave Oscillator (EWO)

**Edge Hypothesis**: Wave 3 (strongest move) identified by EWO peak.

**Calculation**: EWO = SMA(5) - SMA(34)

**Rules**:
- Long: EWO positive AND increasing AND 50 SMA sloping up
- Target: 100-161% of Wave 1 length

**Limitation**: Subjective wave counting; works best with 100-150 bars on chart.

---

### 21. First Trading Day of Month

**Backtest Results**:
- Avg gain: 0.14% (open to close on first day)
- Statistically significant vs. other days

**Why It Works**: Pension fund inflows, 401k contributions.

**Source**: [Quantified Strategies](https://www.quantifiedstrategies.com/the-first-trading-day-of-the-month/)

---

## Tier 4: Mixed Evidence / Use as Filters Only

### 22. Ichimoku Cloud

- 10% win rate in extensive backtests
- Works better as trend confirmation, not standalone
- Reduces drawdowns but often underperforms buy & hold

### 23. Parabolic SAR

- 73% win rate on SPY with default settings
- 30% win rate on standard charts (poor)
- 63% win rate with Heikin Ashi charts
- Best as trailing stop, not entry signal

### 24. Supertrend

- 42-43% win rate
- Should never be used in isolation
- Better as trend confirmation filter

### 25. CANSLIM

- Historically beat S&P since 2003
- BUT: CANSLIM-based funds (CANGX, FFTY) underperformed
- Requires discretionary judgment; hard to systematize

---

## Key Meta-Learnings

### What Creates Sustainable Edge?

1. **Behavioral Biases**: Mean reversion works because traders overreact to short-term moves
2. **Structural Flows**: Turn-of-month effect from pension/401k inflows
3. **Risk Premium**: Overnight edge from bearing overnight risk
4. **Momentum Persistence**: 3-12 month returns persist (behavioral underreaction)

### Strategy Combination Principles

1. **Regime Filter First**: Use 200 SMA or VIX to determine risk-on/off
2. **Combine Uncorrelated Signals**: Mean reversion + momentum filters
3. **Multi-Timeframe Confirmation**: Higher TF trend + lower TF entry

### Common Failure Modes

1. **No Regime Filter**: Strategies fail when market regime changes
2. **Over-optimization**: Curve-fitting to historical data
3. **Ignoring Transaction Costs**: Many strategies fail with realistic commissions
4. **Look-ahead Bias**: Using close prices for same-day decisions

---

## Implementation Priority for QuantConnect

### Immediate Implementation (High Conviction + Feasible)

| Strategy | Complexity | Data Needs | Expected Sharpe |
|----------|------------|------------|-----------------|
| RSI-2 Mean Reversion | Low | Daily OHLC | 1.0-1.5 |
| Williams %R | Low | Daily OHLC | 1.0-1.5 |
| IBS Strategy | Low | Daily OHLC | 1.2-1.6 |
| Turn of Month | Very Low | Calendar | 0.8-1.0 |
| Dual Momentum (GEM) | Low | Monthly | 0.8-1.2 |

### Medium-Term Implementation

| Strategy | Complexity | Data Needs |
|----------|------------|------------|
| Sector Rotation | Medium | Sector ETFs |
| ADX Holy Grail | Medium | Daily OHLC |
| VIX Market Timing | Medium | VIX data |
| Keltner Mean Reversion | Medium | Daily OHLC |

### Research-Only (Needs More Validation)

- Overnight Edge (execution challenges)
- TTM Squeeze (mixed results)
- TQQQ/TMF (leverage risks)
- Regime Detection (HMM complexity)

---

## Sources & Further Reading

### Primary Research Sources
- [Quantified Strategies](https://www.quantifiedstrategies.com/) - 200+ backtested strategies
- [Quantpedia](https://quantpedia.com/) - Academic strategy database
- [Liberated Stock Trader](https://www.liberatedstocktrader.com/) - Extensive indicator backtests
- [Alvarez Quant Trading](https://alvarezquanttrading.com/) - Mean reversion research

### Books Referenced
- "Short Term Trading Strategies That Work" - Larry Connors
- "Dual Momentum Investing" - Gary Antonacci
- "Street Smarts" - Connors & Raschke
- "What Works on Wall Street" - James O'Shaughnessy
- "The Way of the Turtle" - Curtis Faith

### Academic Papers (SSRN)
- [Diversified Statistical Arbitrage](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1666799)
- [Statistical Arbitrage in US Equities](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1153505)
- [Trend Following Strategies: A Practical Guide](https://papers.ssrn.com/sol3/Delivery.cfm/5140633.pdf?abstractid=5140633)

---

## Appendix: Quick Reference Card

### Mean Reversion Signals (Buy Low)
| Indicator | Oversold Level | Holding Period |
|-----------|---------------|----------------|
| RSI(2) | < 10-15 | Until RSI > 70 |
| Williams %R | < -90 | Until > -30 |
| IBS | < 0.10 | 1-14 days |
| MFI | < 30 | Until > 70 |

### Trend Filters (Risk-On/Off)
| Filter | Bullish | Bearish |
|--------|---------|---------|
| Price vs 200 SMA | Above | Below |
| ADX | > 25 rising | < 20 |
| VIX | < 20 | > 30 |
| Dual Momentum | Positive 12mo | Negative 12mo |

### Seasonal Edges
| Anomaly | Entry | Exit |
|---------|-------|------|
| Turn of Month | -2 days | +3 days |
| First Day | Open | Close |
| Overnight | Close | Next Open |
