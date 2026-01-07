# Portfolio Strategy Research

Deep research compilation for systematic portfolio strategy development.

---

## Executive Summary

Based on extensive research across academic papers, practitioner blogs, Reddit discussions, and hedge fund strategies, here are the key findings for building a systematic portfolio that targets 30-50% returns with controlled drawdowns.

### Key Insight

**The holy grail combination appears to be:**
1. **Dual/Accelerating Momentum** for signal generation (time-series + cross-sectional)
2. **Volatility-adjusted position sizing** for steady risk
3. **Multiple lookback periods** (1, 3, 6 months) for robustness
4. **52-week high proximity** as a crash filter
5. **Weekly rebalancing** to balance responsiveness and costs

---

## 1. Momentum Strategy Variants

### 1.1 Classic Dual Momentum (Antonacci)
- **Lookback**: 12 months
- **Signal**: Absolute (return > 0) + Relative (return > benchmark)
- **Rebalance**: Monthly
- **Performance**: ~7-11% CAGR, max DD ~20%
- **Problem**: 12-month lookback is too slow for fast-moving markets

**Source**: [Optimal Momentum](https://www.optimalmomentum.com), [TuringTrader](https://www.turingtrader.com/portfolios/antonacci-dual-momentum/)

### 1.2 Accelerating Dual Momentum (ADM)
- **Innovation**: Multiple lookback periods (1, 3, 6 months) averaged
- **Formula**: Momentum Score = (1mo return + 3mo return + 6mo return) / 3
- **Performance**: ~11% CAGR, max DD 24% over 15 years
- **$10K → $420K** (1998-2017) vs $40K for S&P 500

**Criticism**: Gary Antonacci himself called it "highly data mined using limited data"

**Source**: [Engineered Portfolio](https://engineeredportfolio.com/2018/05/02/accelerating-dual-momentum-investing/), [Allocate Smartly](https://allocatesmartly.com/taa-strategy-accelerating-dual-momentum/)

### 1.3 Time-Series vs Cross-Sectional Momentum

| Type | Description | Best When |
|------|-------------|-----------|
| **Time-Series** | Individual stock momentum (return > 0) | Strong trending markets |
| **Cross-Sectional** | Relative ranking vs peers | Sideways markets |

**Key finding**: Time-series is significant in 18/24 markets; cross-sectional only in 12/24.

**Recommendation**: Use BOTH - time-series for entry, cross-sectional for ranking

**Source**: [Quantpedia](https://quantpedia.com/time-series-vs-cross-sectional-implementation-of-momentum-value-and-carry-strat/)

---

## 2. Optimal Lookback Periods

### Academic vs Practical

| Period | Academic Support | Recent Performance | Notes |
|--------|------------------|-------------------|-------|
| 12 months | Strong (classic) | Poor recently | Too slow |
| 6 months | Good | Better recently | Good balance |
| 3 months | Moderate | Best recently | More responsive |
| 1 month | Weak | Noisy | Too much whipsaw |

### Best Practice: Combine Multiple Lookbacks

**iShares MTUM ETF** uses 6 + 12 month lookbacks for diversification.

**Research finding**: Using 63, 126, and 262 days (3, 6, 12 months) creates more robust results.

**Skip the most recent month** to avoid short-term reversal effect.

**Source**: [Seeking Alpha](https://seekingalpha.com/article/4240540-optimal-lookback-period-for-momentum-strategies), [NextInvest](https://nextinvest.org/post_detail/8089150d-e2ff-4e99-8eb8-19746983e885)

---

## 3. 52-Week High Effect

### Key Research Finding

Stocks near their 52-week high outperform stocks far from it.

- **52WH strategy**: 0.65% per month
- **Classic momentum**: 0.38% per month
- **Industry momentum**: 0.25% per month

**52-week high dominates other momentum measures.**

### Behavioral Explanation

Investors use 52-week high as an "anchor" - they're unwilling to bid prices above it, creating underreaction that we can exploit.

### Crash Protection

**Nearhigh-neutral strategy** (equalizing 52WH exposure on long/short sides):
- Improves minimum return from -74% to -24%
- Improves skewness from -1.89 to 0.13
- **No sacrifice in profitability**

**Source**: [Bauer Research](https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf), [Marquette Research](https://epublications.marquette.edu/cgi/viewcontent.cgi?article=1168&context=fin_fac)

---

## 4. Position Sizing & Volatility Targeting

### Volatility Targeting

**Goal**: Keep portfolio volatility constant regardless of market conditions.

**Formula**:
```
Scaling Factor = Target Volatility / Recent Volatility
Position Size = Base Size × Scaling Factor
```

**Benefits**:
- Stabilized risk profile
- Improved Sharpe ratio (10.7% vs 9% return in one study)
- Better drawdown management
- Reduces panic selling

**Source**: [Quantpedia](https://quantpedia.com/an-introduction-to-volatility-targeting/), [Research Affiliates](https://www.researchaffiliates.com/publications/articles/1014-harnessing-volatility-targeting)

### Risk Parity for Individual Stocks

Applied to FAANG stocks:
- **Risk Parity**: 23.71% return, 22.55% std dev, **1.051 Sharpe**
- **Tangency Portfolio**: 17.22% return, 26.42% std dev, 0.652 Sharpe

Risk parity beats optimization-based approaches for individual stocks.

**Source**: [Open Quant Live Book](https://bookdown.org/souzatharsis/open-quant-live-book/risk-parity-portfolios.html)

---

## 5. Avoiding Momentum Crashes

### Three Proven Methods

| Method | How It Works | Effectiveness |
|--------|-------------|---------------|
| **52WH Neutral** | Balance 52WH exposure on both sides | Best - improves skewness dramatically |
| **Idiosyncratic Momentum** | Use stock-specific momentum, remove market beta | Emerges as best in multi-model comparison |
| **Volatility Scaling** | Reduce positions when vol spikes | Good but constant scaling underperforms dynamic |

### Dynamic Switching

**Key insight**: Momentum crashes 1-3 months AFTER market plunges.

**Solution**: Switch to contrarian strategy after market crash for 3 months, then revert to momentum.

**Source**: [Quantpedia](https://quantpedia.com/three-methods-to-fix-momentum-crashes/), [1nve.st](https://www.1nve.st/p/how-to-sidestep-momentum-crashes)

---

## 6. CANSLIM & Minervini (Growth Momentum)

### CANSLIM (O'Neil)

Named top-performing strategy 1998-2009 by AAII.

**Key criteria**:
- Current quarterly earnings up 25%+
- Annual earnings growth 25%+ over 3 years
- New product/management catalyst
- Price at 52-week high with volume
- Market in uptrend

**Limitation**: Doesn't work in bear markets.

**Source**: [TraderLion](https://traderlion.com/trading-strategies/canslim/)

### SEPA (Minervini)

Two-time US Investing Champion (1997, 2021).

**Key elements**:
- **Trend Template**: Price > 50/150/200 SMA, 200 SMA rising
- **Volatility Contraction Pattern (VCP)**: Tightening price ranges
- **Breakout entry** on high volume
- **7-8% stop loss** rule

**Source**: [QuantStrategy.io](https://quantstrategy.io/blog/sepa-strategy-explained-mastering-trend-following-with-mark/), [ChartMill](https://www.chartmill.com/documentation/stock-screener/fundamental-analysis-investing-strategies/464-Mark-Minervini-Strategy-Think-and-Trade-Like-a-Champion-Part-1)

---

## 7. What Renaissance/Medallion Does

- **Returns**: 66% annually before fees (39% after)
- **Win rate**: Only 50.75% but across millions of trades
- **Profit per trade**: 0.01% to 0.05%

**Strategies**:
1. **Mean reversion**: Prices return to average after extremes
2. **Momentum/trending**: Predict how long trends continue
3. **Statistical arbitrage**: Pairs trading, market-neutral

**Key insight**: They combine momentum AND mean reversion based on regime.

**Source**: [Cornell Capital](https://www.cornell-capital.com/blog/2020/02/medallion-fund-the-ultimate-counterexample.html), [Quartr](https://quartr.com/insights/edge/renaissance-technologies-and-the-medallion-fund)

---

## 8. Factor Timing & Regime Switching

### When Momentum Works vs Doesn't

| Regime | Momentum Performance |
|--------|---------------------|
| Bull market | Works well |
| Early recovery | Often crashes |
| Late cycle | Good |
| Recession | Mixed |
| High volatility | Crashes more likely |

### Factor Momentum

Factors with positive returns over prior year earn significant premiums; those with negative returns earn premiums indistinguishable from zero.

**Simple rule**: Bet on factor autocorrelation continuing.

**Source**: [BlackRock](https://www.blackrock.com/us/individual/insights/factor-timing), [Research Affiliates](https://www.researchaffiliates.com/publications/articles/828-factor-timing-keep-it-simple)

---

## 9. Trend Following Performance Data

### Long-Term Backtests

| Source | CAGR | Sharpe | Max DD | Period |
|--------|------|--------|--------|--------|
| SSRN Study (stocks) | 15.19% | N/A | N/A | 1991-2024 |
| CFM (200 years) | N/A | 0.72 | N/A | 200 years |
| China futures | 16.24% | 0.88 | N/A | 1999-2019 |
| TTU Index | 7.04% | N/A | 20.4% | 2000-2025 |

### Key Characteristic

Trend following has positive Sharpe AND positive skewness - "investors receive a premium and get protection."

**Challenge**: Works better on commodities than stocks.

**Source**: [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5084316), [Top Traders Unplugged](https://www.toptradersunplugged.com/trend-following-performance-report-may-2025/)

---

## 10. Practical Implementation Insights

### From Reddit/FinTwit Community

1. **Expect 50%+ of trades to be losers** - focus on making winners go further
2. **Simpler strategies outperform complex ones** out of sample
3. **Run multiple strategies** to reduce correlation risk
4. **1-2% risk per trade** is the community consensus
5. **Backtests are unreliable** - 99% have bias

### Transaction Costs Matter

52-week high momentum profits disappear after transaction costs in most international markets.

**Solution**: Less frequent rebalancing (weekly/monthly vs daily).

---

## 11. Research Synthesis: Proposed Strategy

Based on all research, here's my synthesized recommendation:

### Signal Generation

```
MOMENTUM SCORE = (1-month return + 3-month return + 6-month return) / 3

ENTRY CONDITIONS (ALL must be true):
1. Momentum Score > 0 (absolute momentum)
2. Momentum Score > SPY Momentum Score (relative momentum)
3. Price > 50-day SMA (trend confirmation)
4. Price within 25% of 52-week high (near high filter)

EXIT CONDITIONS (ANY triggers):
1. Momentum Score < 0
2. Momentum Score < SPY Momentum Score
3. Price < 50-day SMA
```

### Position Sizing

```
Target portfolio volatility: 15%
Individual position risk: 1% of portfolio

Position Size = (1% × Portfolio) / (Stock 20-day ATR × Stock Price)
Cap at 5% per stock
```

### Portfolio Rules

```
Max positions: 20
Min positions: 5 (if fewer, hold cash)
Rebalance: Weekly (Friday close → Monday open)
Universe review: Quarterly or when stock breaks criteria
```

### Crash Protection

```
IF market drops 10% in 1 month:
   Switch to 3-month contrarian for 3 months
   (Buy stocks DOWN most, not up most)
   Then revert to momentum
```

---

## 12. Sources

### Academic
- [Bauer UH - 52-Week High Research](https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf)
- [AQR - Case for Momentum](https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/The-Case-for-Momentum-Investing.pdf)
- [SSRN - Trend Following Stocks](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5084316)

### Practitioner
- [Optimal Momentum](https://www.optimalmomentum.com)
- [Quantpedia](https://quantpedia.com)
- [Alpha Architect](https://alphaarchitect.com)
- [Engineered Portfolio](https://engineeredportfolio.com)

### Funds & Research
- [Renaissance Technologies](https://en.wikipedia.org/wiki/Renaissance_Technologies)
- [Research Affiliates](https://www.researchaffiliates.com)
- [AQR Capital](https://www.aqr.com)

### Trading Systems
- [TuringTrader](https://www.turingtrader.com)
- [Allocate Smartly](https://allocatesmartly.com)
- [TraderLion - CANSLIM](https://traderlion.com/trading-strategies/canslim/)
- [QuantStrategy - SEPA](https://quantstrategy.io/blog/sepa-strategy-explained-mastering-trend-following-with-mark/)
