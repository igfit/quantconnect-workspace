# Phase 2 Backtest Results

**Period**: 2015-01-01 to 2024-12-31 (10 years)
**Initial Capital**: $100,000

## Summary Table

| Strategy | Universe | CAGR | Sharpe | Max DD | Win% | Avg Win | Avg Loss | R:R | Trades |
|----------|----------|------|--------|--------|------|---------|----------|-----|--------|
| **Dual Momentum GEM** | A (ETFs) | 7.05% | 0.27 | 33.4% | 53% | 10.09% | -3.99% | 2.53 | 31 |
| **Sector Rotation** | B (Sectors) | 6.15% | 0.24 | 19.7% | 64% | 1.12% | -1.18% | 0.96 | 339 |
| **RSI-2 Mean Reversion** | E (SPY) | 3.88% | 0.10 | 29.0% | 75% | 1.87% | -2.97% | 0.63 | 123 |
| **Williams %R** | E (SPY) | 3.47% | 0.07 | 29.0% | 78% | 2.03% | -3.13% | 0.65 | 83 |
| SuperTrend Sectors | B (Sectors) | - | - | - | - | - | - | - | (Error) |

## Benchmark Comparison (SPY Buy-Hold 2015-2024)

| Metric | SPY B&H | Best Phase 2 Strategy |
|--------|---------|----------------------|
| CAGR | ~12% | 7.05% (Dual Momentum) |
| Sharpe | ~0.6 | 0.27 (Dual Momentum) |
| Max DD | ~34% | 19.7% (Sector Rotation) |

## Analysis

### What Worked ✓

1. **Sector Rotation** - Lowest max drawdown (19.7%) with decent returns
2. **High Win Rates** - RSI-2 (75%) and Williams %R (78%) have high win rates
3. **Regime Filters** - All strategies avoided worst of 2022 bear market

### What Didn't Work ✗

1. **CAGR Below Target** - All strategies below 25-30% target (max: 7.05%)
2. **Low Sharpe Ratios** - All below 0.5, well under 1.0 target
3. **Mean Reversion Struggles** - RSI-2 and Williams %R underperformed B&H SPY
4. **SuperTrend Error** - Strategy logic needs debugging

### Key Observations

1. **Dual Momentum GEM**
   - Best overall CAGR (7.05%) but still below SPY B&H
   - Highest R:R ratio (2.53) - big winners offset losers
   - 31 trades over 10 years = low turnover
   - Drawdown similar to SPY (~33%)

2. **Sector Rotation**
   - Best drawdown control (19.7%)
   - High win rate (64%) but small wins vs small losses
   - 339 trades = higher turnover and fees ($1,519)
   - Diversification across sectors helped

3. **RSI-2 & Williams %R**
   - Very high win rates (75-78%) as expected for mean reversion
   - BUT average loss > average win (R:R < 1.0)
   - In bull markets (2015-2024), mean reversion underperforms buy-hold
   - Regime filter helped avoid catastrophic losses

### Conclusions

**Phase 2 strategies do NOT meet the 25-30% CAGR target.**

- ETF/Sector strategies are inherently limited by their universe
- Mean reversion on SPY underperforms buy-and-hold in bull markets
- The 2015-2024 period was a strong bull market - these strategies are designed for risk management, not alpha generation

### Recommendations for Phase 3

1. **Focus on High-Beta universe** - Need more volatile stocks for higher returns
2. **Trend-following > Mean Reversion** - In trending markets, go with the trend
3. **Consider leverage** - These strategies could be applied with leveraged ETFs
4. **Combine strategies** - Regime switching between mean reversion (bear) and momentum (bull)

## Project IDs

| Strategy | Project ID | Backtest ID |
|----------|------------|-------------|
| Dual Momentum GEM | 27336895 | 0651f9ce20f6514197b8075672c07a29 |
| Sector Rotation | 27336896 | f199199252f7a84316a6a2cf33a8b8ef |
| RSI-2 Mean Reversion | 27336898 | 55190f00547b008db39434c587dd83ff |
| Williams %R | 27336903 | 96560ea63033b1bef5d399e106747fd0 |
| SuperTrend | 27336908 | (error - needs fix) |
