# Strategy Factory - Implementation Notes & Learnings

> This file captures learnings, gotchas, and insights discovered during implementation.
> Update this file whenever you learn something new that could help future development.

---

## Environment Notes

### 2025-01-07 - Initial Setup

**LEAN CLI Status:**
- LEAN CLI is NOT installed
- Docker is NOT available in this environment
- Must use QuantConnect cloud API for all backtesting

**QC API Status:**
- API credentials configured and working
- `./scripts/qc-api.sh auth` returns success
- Rate limit: 30 requests/minute

**Implication:**
- All backtests go through QC cloud API
- Need smart rate limiting and batching
- ~40-50 backtests per hour max throughput

---

## QC API Learnings

### Authentication
- Uses SHA-256 timestamped auth (not basic auth)
- `qc-api.sh` handles this automatically
- Direct API calls require: `{api_token}:{unix_timestamp}` → SHA-256 → Base64 with user_id

### Backtest API

**Response Structure:**
- `backtestId` is nested: `response["backtest"]["backtestId"]` NOT `response["backtestId"]`
- Statistics are in: `response["backtest"]["statistics"]`

**Statistics Key Names (IMPORTANT!):**
```
Expected Key       → Actual QC Key
─────────────────────────────────────
Total Trades       → Total Orders
Total Net Profit   → Net Profit
Starting Capital   → Start Equity
Equity Final       → End Equity
```

**Sample Statistics Response:**
```json
{
  "Total Orders": "193",
  "Average Win": "1.80%",
  "Average Loss": "-0.56%",
  "Compounding Annual Return": "10.088%",
  "Drawdown": "16.200%",
  "Sharpe Ratio": "0.503",
  "Win Rate": "46%",
  "Profit-Loss Ratio": "3.21",
  "Alpha": "0.009",
  "Beta": "0.183",
  "Start Equity": "100000",
  "End Equity": "161765.57",
  "Net Profit": "61.766%"
}
```

### Common Errors

**1. JSON Parsing with qc-api.sh**
- The script uses `jq` which formats output with individual JSON objects, not arrays
- Solution: Use direct API calls with `urllib.request` for programmatic access

**2. Backtest ID Extraction**
- Wrong: `response.get("backtestId")`
- Right: `response.get("backtest", {}).get("backtestId")`

---

## Strategy Generation Learnings

### Round 7 - Diversification Strategies (2026-01-08)

**Problem Identified:** Previous strategies had 25-73% of P&L from NVDA alone.

**Solutions Tested:**
1. **Multi-Sector Balanced** - Force sector diversification (max 35% per sector)
2. **Diversified Caps** - Hard 10% position caps, 10 positions minimum
3. **Sector ETF Momentum** - Use ETFs instead of individual stocks
4. **Equal-Risk Contribution** - Volatility-weighted positions
5. **Anti-Concentration** - Force rotation of long-held positions

**Results:**
| Strategy | Sharpe | CAGR | Max DD | NVDA % |
|----------|--------|------|--------|--------|
| MultiSectorBalanced | 0.898 | 22.1% | 19.0% | 19.8% |
| DiversifiedCaps | 0.865 | 20.4% | 18.1% | 20.0% |
| SectorETFMomentum | 0.727 | 14.2% | 13.0% | N/A |
| EqualRiskContrib | 0.713 | 17.9% | 24.4% | ~25% |
| AntiConcentration | 0.712 | 19.8% | 25.2% | ~25% |

**Key Insight:** Diversification WORKS. NVDA contribution reduced from 73% to 20%.
Trade-off is lower absolute returns (22% vs 40%+) but much better risk-adjusted.

**Best Approach:** MultiSectorBalanced - forces sector diversification while
maintaining strong momentum signal. 8 positions, max 3 per sector, 35% sector cap.

---

### What Works

**High Breakout Strategy:**
- Simple price > SMA entry, price < SMA exit
- Universe: Large cap tech (AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, AMD)
- Results: Sharpe 0.81, CAGR 15.8%, MaxDD 20.1%, 1100 trades over 5 years
- Note: High turnover (244/year) gets penalized in ranking

**MA Crossover Momentum:**
- 20/50 SMA crossover on large cap tech
- Results: Sharpe 0.48, CAGR 981.8%*, MaxDD 16.7%, 193 trades
- More conservative, lower turnover
- *Note: CAGR likely inflated due to position sizing on multiple symbols

**Dual EMA Trend (NEW):**
- 12/26 EMA crossover entry/exit
- Universe: QQQ, SPY, AAPL, NVDA, TSLA, AMZN
- Results: Sharpe 0.78, CAGR 13.8%, MaxDD 12.5%, 213 trades
- Best risk-adjusted returns with low drawdown

### What Doesn't Work

**Crossover Strategies with Trend Filter:**
- Strategy: Price crosses above SMA AND RSI > 50
- Problem: If price already above SMA at backtest start, no crossover detected
- Result: 0 trades generated
- Fix needed: Initialize prev_indicator_values during warmup period

### Indicator Notes

**Crossover Detection:**
- Requires previous day's values to detect the "cross"
- Current implementation stores prev values at end of each day
- Edge case: Day 1 after warmup has no prev values (defaults to 0)
- This can cause false positives or no signals depending on condition

---

## Code Generation Learnings

*(To be updated during compiler development)*

### QC Code Patterns
- *(Add working code patterns)*

### Common Pitfalls
- *(Add pitfalls and how to avoid)*

---

## Validation Learnings

*(To be updated during validation phase)*

### Walk-Forward Results
- *(Add observations about validation)*

### Regime Analysis
- *(Add market regime insights)*

---

## Performance Notes

### API Performance
- Rate limit: 30 requests/minute (implemented with 2.5s buffer between requests)
- Backtest polling: 3 second intervals
- Average backtest completion: 15-20 seconds for 5-year daily strategies

### Backtest Duration
- 3 strategies full pipeline: ~1-1.5 minutes
- Per strategy (push + compile + backtest + poll): ~20-25 seconds
- Estimated throughput: ~40-50 backtests per hour

### Pipeline Timing (3 strategies, skip sweep)
```
Phase 1 (Generation): <1 second
Phase 2 (Backtests):  ~60-70 seconds
Phase 3 (Filtering):  <1 second
Phase 5 (Validation): <1 second
Phase 6 (Ranking):    <1 second
Phase 7 (Report):     <1 second
Total:                ~1-1.5 minutes
```

---

## Bug Fixes

### Bug: Parser Key Mismatches
**Date:** 2026-01-07
**Symptoms:** All strategies showed `Trades: 0` but had meaningful Sharpe ratios and win rates
**Root Cause:** QC API uses different key names than expected:
- `Total Orders` not `Total Trades`
- `Net Profit` not `Total Net Profit`
- `Start Equity` not `Starting Capital`
- `End Equity` not `Equity Final`
**Fix:** Updated `core/parser.py` to use correct QC API key names
**Prevention:** Always check raw API response (`raw_statistics` field) when metrics look wrong

### Bug: Report Generation TypeError
**Date:** 2026-01-07
**Symptoms:** `TypeError: object of type 'int' has no len()`
**Root Cause:** Used `len(self.generator.generated_count)` but `generated_count` is an int, not a list
**Fix:** Changed to `self.generator.generated_count`
**Prevention:** Check variable types before using len()

### Bug: Security Initializer Overwrite
**Date:** 2026-01-07
**Symptoms:** Slippage model not being applied to strategies
**Root Cause:** Calling `set_security_initializer` twice in the template - second call overwrites the first
**Fix:** Combined both slippage and fee model into a single initializer function
**Prevention:** Only call `set_security_initializer` once with all security settings

### Bug: Crossover Detection Missing Previous Values
**Date:** 2026-01-07
**Symptoms:** Strategies with crossover conditions generated 0 trades
**Root Cause:** `prev_indicator_values` was empty on first day after warmup, causing crossover detection to always return False
**Fix:**
1. Initialize prev values on first run in `generate_signals()`
2. Skip first day to establish baseline for crossovers
3. Return `None` from `_get_prev_value()` instead of 0.0 for missing values
4. Check for `None` in crossover functions before comparing
**Prevention:** Always test crossover strategies to ensure they generate trades

### Bug: Unused Indicators Causing 0 Trades
**Date:** 2026-01-07
**Symptoms:** Strategies with complex indicators (BB, MACD, ATR) not used in conditions generated 0 trades
**Root Cause:** `_has_valid_data()` checks ALL indicators for `is_ready`, but complex indicators like Bollinger Bands and MACD may not report ready correctly even after warmup
**Fix:** Removed unused indicators from strategy definitions. Only define indicators actually used in conditions.
**Prevention:** Never define indicators that aren't used in entry/exit conditions

### Bug Template
```
### Bug: [Title]
**Date:** YYYY-MM-DD
**Symptoms:** What went wrong
**Root Cause:** Why it happened
**Fix:** How it was resolved
**Prevention:** How to avoid in future
```

---

## Ideas & Future Improvements

*(Capture ideas as they come up)*

- *(Add ideas here)*

---

## References

### QuantConnect Docs
- [Algorithm Framework](https://www.quantconnect.com/docs/v2/writing-algorithms/algorithm-framework)
- [Indicators](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators)
- [API Reference](https://www.quantconnect.com/docs/v2/cloud-platform/api-reference)

### Strategy Research
- *(Add useful research links)*
