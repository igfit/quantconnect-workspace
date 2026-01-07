# Portfolio Strategy Requirements

## First Principles Q&A Session

This document captures the requirements gathering process for building a systematic portfolio strategy.

---

## 1. Goal Definition

### Question: What is the REAL goal?

**Options presented:**
- A) Maximize returns - Concentrate in best opportunities, accept volatility
- B) Steady income/growth - Consistent positive months, lower peaks but fewer valleys
- C) Beat benchmark with less risk - SPY-like returns with half the drawdown
- D) Absolute returns - Make money in any market

**Answer:** Combination of A + B

---

## 2. Performance Targets

### Question: What does "steady P&L" mean to you?

**Answer:**
- Should be positive almost every month
- Definitely positive every quarter

### Question: What drawdown is acceptable?

**Answer:** 15% portfolio level drawdown is OK

### Question: What return do you need?

**Answer:** 30-50% annually

### Question: What's your time horizon?

**Answer:** Long time horizon is fine

### Question: How much effort for universe management?

**Answer:** Monthly or quarterly as needed (but not necessary)

### Question: How many positions?

**Answer:** Can hold 20+ positions, that's OK

---

## 3. Risk Tolerance Clarification

### Question: Given the tension between high returns and low drawdown, which is MORE true?

**Options presented:**
- A) "I'd rather have a few bad months but hit 40%+ returns"
- B) "I'd rather have steady 20% returns with no month worse than -3%"
- C) "I want to try for both, understanding it's hard"

**Answer:** A or C

---

## 4. Return Source / Edge

### Question: Where do returns come from? What edge do you believe in?

**Options presented:**
1. Momentum (Trend Following) - "Winners keep winning"
2. Mean Reversion - "What goes up must come down"
3. Volatility Harvesting - "Collect premium from fear"
4. Factor Exposure - "Tilt toward what works"
5. Timing (Macro/Regime) - "Be in for the good, out for the bad"

**Answer:** (Implicit from earlier testing) - Momentum / Dual Momentum approach works well

---

## 5. Crash Handling

### Question: How do you handle the scenario where the whole market drops 30%?

**Options presented:**
1. Ride it out - Accept 20-30% drawdowns occasionally, recover over time
2. Exit on regime change - SPY < 200 SMA → reduce exposure
3. Hedge - Buy puts, VIX calls
4. Diversify across asset classes - Add bonds, gold, commodities

**Answer:** Option 1 - Ride it out

**Implication:**
- No regime switching
- No hedging
- Defense = diversification + position sizing + exit signals only

---

## 6. Universe Selection

### Question: What KIND of stocks do you want in this universe?

**Options presented:**
- A) High-growth tech/momentum names (TSLA, NVDA, AMD, META, etc.)
- B) Diversified large-caps (AAPL, JPM, UNH, XOM, etc.)
- C) Mix of both
- D) Sector leaders only

**Answer:** Mostly A, but a little bit of B might be OK

**Implication:**
- ~80% high-growth/momentum stocks
- ~20% stable large-caps for ballast

---

## 7. Universe Selection Method

### Question: How do you want to select the universe?

**Options presented:**
1. Fixed list (curated manually)
2. Quantitative screening (rules-based)
3. Hybrid (screen → you approve)

**Answer:** Hybrid + Claude Code/AI agent to generate the list

### Question: How often should the universe change?

**Options presented:**
- A) Quarterly
- B) Monthly
- C) Only when something breaks (delist, crashes 50%, etc.)

**Answer:** C - Only when something breaks

---

## 8. Position Sizing

### Question: How much in each position?

**Options presented:**
1. Equal weight (each stock = 100% / N)
2. Risk parity (volatility-adjusted)
3. Conviction-weighted (stronger signals = bigger positions)
4. Capped equal weight (equal weight with max % per stock)

**Answer:** Should be 1 or 4 (Equal weight OR Capped equal weight)

### Question: Max positions at once?

**Options presented:**
- A) Always hold all universe stocks
- B) Only hold stocks with active signal (variable)

**Answer:** B - Only hold stocks with active BUY signal

**Implication:**
- Variable number of positions (could be 5, could be 25)
- Cash is automatic risk management
- In weak markets: few signals → few positions → capital in cash

---

## 9. Signal / Strategy (Research Complete)

### Research Findings

Based on extensive research across academic papers, practitioner strategies, and hedge fund approaches, the following strategy is proposed:

### Proposed Strategy: Accelerating Dual Momentum with 52WH Filter

**Why this approach?**
- Accelerating momentum (multiple lookbacks) outperforms single lookback
- 52-week high proximity is the strongest momentum predictor (0.65%/month vs 0.38% for classic)
- Trend confirmation (50 SMA) reduces whipsaws
- Research shows this combination prevents crashes without sacrificing returns

### Entry Conditions (ALL must be true)

```
1. Accelerating Momentum > 0
   Formula: (1-month return + 3-month return + 6-month return) / 3

2. Accelerating Momentum > SPY Accelerating Momentum
   (Relative strength filter)

3. Price > 50-day SMA
   (Trend confirmation)

4. Price within 25% of 52-week high
   (Near-high filter - key crash protection)
```

### Exit Conditions (ANY triggers exit)

```
1. Accelerating Momentum < 0
   (Absolute momentum fails)

2. Accelerating Momentum < SPY Accelerating Momentum
   (Relative strength fails)

3. Price < 50-day SMA
   (Trend breaks)
```

### Signal Frequency

**Answer:** Weekly (Friday close → Monday open execution)

**Rationale:**
- Daily is too noisy, causes whipsaws
- Monthly is too slow for high-beta stocks
- Weekly balances responsiveness with transaction costs
- Aligns with institutional rebalancing patterns

### Position Sizing

```
Method: Capped Equal Weight
- Max per position: 5%
- Minimum positions: 5 (if fewer signals, hold cash)
- Maximum positions: 20

Risk-Based Alternative (optional):
- Target 1% portfolio risk per position
- Position Size = (1% × Portfolio) / (Stock ATR × Price)
- Cap at 5%
```

### Crash Protection (Optional Enhancement)

```
IF SPY drops 10%+ in 1 month:
   Switch to contrarian mode for 3 months
   (Buy stocks DOWN most, not UP most)
   Then revert to momentum

Rationale: Research shows momentum crashes 1-3 months AFTER market plunge
```

---

## Requirements Summary

```
┌─────────────────────────────────────────────────────────────┐
│  PORTFOLIO STRATEGY REQUIREMENTS                            │
├─────────────────────────────────────────────────────────────┤
│  PERFORMANCE TARGETS                                        │
│  ├─ Annual Return:      30-50%                              │
│  ├─ Max Drawdown:       15% (portfolio level)               │
│  ├─ Win Rate:           Positive almost every month         │
│  │                      Positive EVERY quarter              │
│  └─ Time Horizon:       Long-term                           │
├─────────────────────────────────────────────────────────────┤
│  RISK APPROACH                                              │
│  ├─ Priority:           Returns first (A), then steadiness  │
│  ├─ Crash Handling:     Ride it out (accept 20-30% DD)      │
│  ├─ Hedging:            None                                │
│  └─ Regime Switching:   None                                │
├─────────────────────────────────────────────────────────────┤
│  UNIVERSE                                                   │
│  ├─ Composition:        80% high-beta momentum              │
│  │                      20% stable large-caps               │
│  ├─ Size:               25-30 stocks                        │
│  ├─ Selection:          Hybrid (quant screen + approval)    │
│  ├─ Generator:          Claude Code / AI agent              │
│  └─ Review:             Only when something breaks          │
├─────────────────────────────────────────────────────────────┤
│  POSITION SIZING                                            │
│  ├─ Method:             Capped equal weight (max 5%)        │
│  ├─ Max Positions:      20 (variable based on signals)      │
│  ├─ Min Positions:      5 (else hold cash)                  │
│  ├─ Cash:               Automatic (no signal = no position) │
│  └─ Leverage:           None (max 100% invested)            │
├─────────────────────────────────────────────────────────────┤
│  SIGNAL (Research Complete)                                 │
│  ├─ Strategy:           Accelerating Dual Momentum + 52WH   │
│  ├─ Entry:              AccelMom > 0 AND > SPY AND          │
│  │                      Price > 50SMA AND near 52WH         │
│  ├─ Exit:               AccelMom < 0 OR < SPY OR            │
│  │                      Price < 50SMA                       │
│  └─ Frequency:          Weekly (Friday → Monday)            │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Tensions to Acknowledge

1. **30-50% returns with 15% max DD** is extremely ambitious (Sharpe ~2.0+)
   - Top hedge funds achieve ~1.0-1.5 Sharpe
   - May need to accept 20-25% DD realistically

2. **Positive every month** conflicts with **riding out crashes**
   - If market drops 20% in a month, portfolio will likely be down
   - Diversification helps but doesn't eliminate systematic risk

3. **High-beta stocks** inherently have **high correlation in crashes**
   - 20+ positions helps with idiosyncratic risk
   - Does NOT help when "everything drops together"

---

## Next Steps

1. [x] Claude Code to research and propose signal logic ✓ (See Section 9)
2. [x] Claude Code to generate initial universe candidates (28 stocks) ✓
3. [ ] User to approve/reject universe
4. [x] Implement strategy in QuantConnect ✓
5. [ ] Backtest strategy on approved universe
6. [ ] Compare results vs benchmarks (SPY/QQQ B&H, DCA)
7. [ ] Iterate based on results

## Related Documentation

- **Research**: `docs/portfolio-strategy-research.md` - Full research compilation with sources
- **Universe**: `docs/universe-candidates.md` - Proposed 28-stock universe
- **Learnings**: `docs/LEARNINGS.md` - Platform and strategy learnings

---

## Implementation Files

| File | Description |
|------|-------------|
| `algorithms/strategies/accel_dual_momentum_portfolio.py` | QuantConnect implementation |
| `algorithms/pinescript/accel_dual_momentum.pine` | TradingView verification script |
| `docs/universe-candidates.md` | Proposed 28-stock universe |

---

## Benchmarks to Beat

| Benchmark | CAGR | Sharpe | Max DD |
|-----------|------|--------|--------|
| Buy & Hold SPY/QQQ | 17.07% | 0.57 | 30.2% |
| Monthly DCA SPY/QQQ | 7.45% | 0.37 | 13.4% |

**Our Target**: CAGR 30-50%, Sharpe > 1.0, Max DD < 20%
