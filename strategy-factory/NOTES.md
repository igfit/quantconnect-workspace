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

*(To be updated during AI generation phase)*

### What Works
- *(Add successful patterns)*

### What Doesn't Work
- *(Add failed approaches)*

### Indicator Notes
- *(Add indicator-specific learnings)*

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

*(To be updated during testing)*

### API Performance
- *(Add timing observations)*

### Backtest Duration
- *(Add backtest timing notes)*

---

## Bug Fixes

*(Document bugs and fixes as encountered)*

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
