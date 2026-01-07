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

## 9. Signal / Strategy (To Be Determined)

### Question: What is a BUY signal? What is a SELL signal?

**Options presented:**
1. Dual Momentum (63-day return > 0 AND > SPY)
2. Trend Following (Price > 50 SMA AND 50 > 200 SMA)
3. Breakout (20-day high + ATR trailing stop)
4. Hybrid (Momentum + Trend confirmation)
5. Something else

**Answer:** Left for research - Claude Code to propose

### Question: How often to check signals?

**Options presented:**
- A) Daily
- B) Weekly
- C) Monthly

**Answer:** Left for research - Claude Code to propose

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
│  ├─ Method:             Equal weight OR Capped equal weight │
│  ├─ Max Positions:      Variable (only with active signal)  │
│  ├─ Cash:               Automatic (no signal = no position) │
│  └─ Leverage:           None (max 100% invested)            │
├─────────────────────────────────────────────────────────────┤
│  SIGNAL (TBD - For Research)                                │
│  ├─ Entry:              To be determined                    │
│  ├─ Exit:               To be determined                    │
│  └─ Frequency:          To be determined                    │
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

1. [ ] Claude Code to research and propose signal logic
2. [ ] Claude Code to generate initial universe candidates
3. [ ] User to approve/reject universe
4. [ ] Backtest strategy on approved universe
5. [ ] Iterate based on results

---

## Benchmarks to Beat

| Benchmark | CAGR | Sharpe | Max DD |
|-----------|------|--------|--------|
| Buy & Hold SPY/QQQ | 17.07% | 0.57 | 30.2% |
| Monthly DCA SPY/QQQ | 7.45% | 0.37 | 13.4% |

**Our Target**: CAGR 30-50%, Sharpe > 1.0, Max DD < 20%
