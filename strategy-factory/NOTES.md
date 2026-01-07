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

*(To be updated during implementation)*

### Authentication
- Uses SHA-256 timestamped auth (not basic auth)
- `qc-api.sh` handles this automatically

### Backtest API
- *(Add notes as discovered)*

### Common Errors
- *(Add errors and solutions as encountered)*

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
