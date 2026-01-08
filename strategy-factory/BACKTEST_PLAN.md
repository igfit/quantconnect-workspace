# Systematic Strategy Backtesting Plan

## Objective

Create an efficient, scalable infrastructure to backtest 15-20 swing trading strategies on QuantConnect with:
- Carefully defined stock universes (avoiding survivorship/hindsight bias)
- Consistent metrics and comparison framework
- Reusable components across strategies
- Clear rationale for all design decisions

---

## Part 1: Universe Design Philosophy

### The Core Problem

We cannot simply pick "stocks that worked" (NVDA, TSLA, etc.) - that's hindsight bias. We need universes that:
1. Were investable at the START of the backtest period
2. Represent a reasonable trading universe for retail/small institutional
3. Match the strategy's intended use case
4. Are liquid enough to trade without excessive slippage

### Universe Categories

We'll define **4 universe types** that cover all our strategies:

| Universe | Use Case | Size | Rationale |
|----------|----------|------|-----------|
| **ETF-Only** | Index/sector strategies | 10-20 ETFs | No survivorship bias, highly liquid, low friction |
| **Large-Cap Liquid** | Momentum ranking, breakout | 100-200 stocks | S&P 500 members, liquid, lower bias |
| **High-Beta Growth** | Trend following, VCP | 30-50 stocks | Higher volatility = more signal opportunities |
| **Sector ETFs** | Rotation strategies | 11 sector SPDRs | Pure signal alpha, no stock picking |

---

## Part 2: Universe Definitions

### Universe A: Core ETFs (Lowest Bias Risk)

**Rationale**: ETFs don't have survivorship bias - SPY existed in 2010, still exists today. Same underlying methodology. This is the cleanest test of signal alpha.

```
Broad Market:
- SPY (S&P 500)
- QQQ (Nasdaq 100)
- IWM (Russell 2000)
- DIA (Dow 30)

Leveraged (for specific strategies):
- TQQQ, SQQQ (3x Nasdaq)
- UPRO, SPXU (3x S&P)

Bonds/Safety:
- TLT (20+ Year Treasury)
- IEF (7-10 Year Treasury)
- BND (Total Bond)

Volatility:
- VXX (VIX Short-term)

Commodities:
- GLD (Gold)
- USO (Oil)
```

**Strategies to test on this universe**:
- Dual Momentum (GEM)
- Leveraged ETF rotation
- Cross-asset momentum
- VIX timing strategies

---

### Universe B: Sector SPDRs (11 Sectors)

**Rationale**: Sector rotation is pure signal alpha - we're not picking stocks, we're picking which sector is trending. All 11 sector SPDRs have existed since 1998.

```
XLK - Technology
XLF - Financials
XLV - Healthcare
XLE - Energy
XLI - Industrials
XLP - Consumer Staples
XLY - Consumer Discretionary
XLB - Materials
XLU - Utilities
XLRE - Real Estate (2015+)
XLC - Communications (2018+)
```

**Note**: XLRE and XLC are newer. For backtests before 2015, use 9 original sectors.

**Strategies to test**:
- Sector momentum rotation
- Relative strength ranking
- Faber-style sector momentum

---

### Universe C: Large-Cap Liquid (100 Stocks)

**Rationale**: We need a stock universe for strategies like Clenow momentum, VCP breakouts, etc. The challenge is survivorship bias.

**Approach - "Mega Cap Core"**:
Select stocks that were:
1. In the S&P 500 as of backtest start date (2015-01-01)
2. Had market cap > $50B at that time
3. Average daily dollar volume > $100M

**Why this works**:
- Mega caps rarely go bankrupt (low survivorship bias)
- Highly liquid (realistic execution)
- ~80-100 stocks meet these criteria
- We accept some bias (a few may have declined) but it's minimal

**Proposed Universe (as of 2015)**:
```
Technology: AAPL, MSFT, GOOGL, INTC, CSCO, ORCL, IBM, QCOM, TXN, ADBE, CRM, AVGO
Financials: JPM, BAC, WFC, C, GS, MS, BLK, AXP, USB, PNC
Healthcare: JNJ, UNH, PFE, MRK, ABBV, TMO, ABT, MDT, AMGN, GILD, BMY, LLY
Consumer: AMZN, HD, MCD, NKE, SBUX, TGT, COST, LOW, TJX
Industrials: BA, HON, UNP, CAT, GE, MMM, LMT, RTX, DE, FDX
Energy: XOM, CVX, COP, SLB, EOG
Communications: META, NFLX, DIS, CMCSA, VZ, T
Other: BRK.B, V, MA, PYPL, KO, PEP, PM, WMT, PG, CL
```

**Note**: Some tickers changed (FB→META, etc.). Use historical tickers in QC.

**Strategies to test**:
- Clenow momentum ranking
- 52-week high breakout
- NR7 breakout
- Donchian channel
- Elder Impulse
- MACD divergence

---

### Universe D: High-Beta Growth (30-50 Stocks)

**Rationale**: Trend-following and VCP strategies need volatility. Low-beta dividend stocks don't give enough signal. We want stocks that MOVE.

**Selection Criteria**:
- Beta > 1.3 (vs S&P 500)
- Average True Range > 2% of price
- In S&P 500 or Nasdaq 100
- Daily dollar volume > $200M

**Approach**: Rather than hand-pick, we'll create a dynamic screen that selects the top 30-50 by beta/volatility at backtest start, then hold that universe fixed.

**Example High-Beta Names (illustrative, not hardcoded)**:
```
Tech Growth: NVDA, AMD, TSLA, SHOP, SQ, SNOW, NET, DDOG, ZS, CRWD
Biotech: MRNA, BIIB, REGN, VRTX, ILMN
Cyclicals: FCX, FSLR, ENPH
Financials: COIN (post-IPO)
```

**IMPORTANT**: We must NOT use 2024 knowledge to pick this list. The screener runs at backtest start.

**Alternative (lower bias)**: Use QQQ top holdings as of start date. Nasdaq 100 is naturally higher beta.

**Strategies to test**:
- Minervini VCP
- Momentum burst
- SuperTrend
- Chandelier Exit
- High-beta breakouts

---

### Universe E: Single Instrument (Benchmark Comparison)

**Rationale**: Some strategies are designed for single instruments. Test on SPY/QQQ to measure pure signal alpha vs buy-and-hold.

```
SPY - S&P 500 ETF
QQQ - Nasdaq 100 ETF
```

**Strategies to test**:
- RSI-2 mean reversion
- Williams %R
- IBS strategy
- Overnight edge
- Turn of month
- Golden cross/death cross

---

## Part 3: Strategy-Universe Mapping

| Strategy | Universe | Rationale |
|----------|----------|-----------|
| **Clenow Momentum** | C (Large-Cap) | Needs stock ranking, requires diversified pool |
| **Donchian Breakout** | C or E | Classic on futures, test on stocks and ETFs |
| **52-Week High** | C (Large-Cap) | Needs individual stocks, institutional breakout |
| **Minervini VCP** | D (High-Beta) | Needs volatility for pattern formation |
| **Darvas Box** | D (High-Beta) | Designed for fast-moving stocks |
| **NR7 Breakout** | C or D | Volatility compression → expansion |
| **Chandelier Exit** | D (High-Beta) | ATR-based, needs volatility |
| **SuperTrend** | B (Sectors) or E | Simple trend, test on ETFs first |
| **Elder Impulse** | C (Large-Cap) | Works on any liquid stock |
| **Hull MA System** | E (Single) | Test signal vs noise on index |
| **Dual Momentum** | A (Core ETFs) | Asset class rotation |
| **Sector Rotation** | B (Sectors) | Sector momentum |
| **RSI-2/Williams %R** | E (Single) | Mean reversion on index |
| **Momentum Burst** | D (High-Beta) | Needs explosive movers |
| **TSI Crossover** | C (Large-Cap) | Momentum oscillator |

---

## Part 4: Backtest Parameters

### Time Period

**Primary Period**: 2015-01-01 to 2024-12-31 (10 years)

**Why 2015 start**:
- Post-2008 recovery complete
- Most ETFs/stocks we want are liquid
- Includes 2018 correction, 2020 crash, 2022 bear market
- Avoids 2008-2009 (too extreme, distorts results)

**Robustness Tests**:
- 2018-2024 (6 years, more recent)
- 2020-2024 (post-COVID, different regime)
- Walk-forward: Train on 2015-2019, test on 2020-2024

### Capital and Position Sizing

```
Starting Capital: $100,000
Position Sizing: Strategy-dependent (see below)
Commission Model: Interactive Brokers
Slippage: 0.1% per trade
```

**Position Sizing Options**:
1. **Equal Weight**: 10% per position (10 positions max)
2. **ATR-Based**: Risk 1% of capital per trade, size = Risk$ / ATR
3. **Volatility Parity**: Size inversely proportional to volatility
4. **Kelly Criterion**: (Not recommended for initial tests)

### Benchmark Comparison

Every strategy must compare against:
1. **Buy & Hold SPY** (baseline)
2. **Buy & Hold QQQ** (if tech-heavy universe)
3. **60/40 Portfolio** (for risk comparison)

---

## Part 5: Infrastructure Architecture

### Modular Design

```
strategy-factory/
├── universes/
│   ├── etf_core.py           # Universe A
│   ├── sector_spdrs.py       # Universe B
│   ├── large_cap_liquid.py   # Universe C
│   ├── high_beta_growth.py   # Universe D
│   └── single_instrument.py  # Universe E
├── indicators/
│   ├── momentum.py           # ROC, Clenow slope, momentum score
│   ├── trend.py              # SuperTrend, HMA, Elder Impulse
│   ├── volatility.py         # ATR, Chandelier, NR7
│   ├── oscillators.py        # RSI, Williams %R, TSI, CMO
│   └── breakout.py           # Donchian, 52-week high, Darvas
├── strategies/
│   ├── base_strategy.py      # Common logic, metrics, logging
│   ├── clenow_momentum.py
│   ├── donchian_breakout.py
│   ├── vcp_breakout.py
│   ├── sector_rotation.py
│   └── ... (one file per strategy)
├── sizing/
│   ├── equal_weight.py
│   ├── atr_risk.py
│   └── volatility_parity.py
├── filters/
│   ├── regime.py             # S&P > 200 SMA, VIX filter
│   ├── volume.py             # Min volume, relative volume
│   └── trend.py              # ADX filter, MA alignment
└── runner/
    ├── batch_backtest.py     # Run multiple strategies
    ├── parameter_sweep.py    # Test parameter ranges
    └── results_parser.py     # Extract metrics
```

### Base Strategy Template

Every strategy inherits from a base class that provides:
- Standard logging and metrics
- Consistent entry/exit tracking
- Position sizing integration
- Regime filter hooks
- P&L attribution by trade

```python
class BaseSwingStrategy(QCAlgorithm):
    def initialize(self):
        # Common setup
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Metrics tracking
        self.trades = []
        self.trade_log = []

        # Regime filter (override in subclass)
        self.regime_filter_enabled = True
        self.spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy_sma200 = self.sma("SPY", 200, Resolution.DAILY)

    def is_bull_regime(self):
        """Returns True if SPY > 200 SMA"""
        return self.securities["SPY"].price > self.spy_sma200.current.value

    def log_trade(self, symbol, direction, entry_price, exit_price, bars_held):
        """Standard trade logging for analysis"""
        pass
```

---

## Part 6: Execution Plan

### Phase 1: Infrastructure Setup (Week 1)

**Deliverables**:
1. Create `strategy-factory/` directory structure
2. Implement Universe A, B, E (ETFs and sectors - no bias risk)
3. Create BaseSwingStrategy template
4. Implement core indicators: ATR, SMA, EMA, ROC
5. Test infrastructure with simple SMA crossover

**Validation**:
- Run SMA crossover on SPY
- Verify metrics match manual calculation
- Confirm logging works

---

### Phase 2: Low-Bias Strategies (Week 2)

**Focus**: Strategies on ETFs/Sectors (Universe A, B, E) - minimal survivorship bias

**Strategies to implement**:
1. Dual Momentum (GEM) - Universe A
2. Sector Rotation (momentum ranking) - Universe B
3. RSI-2 mean reversion - Universe E (SPY only)
4. Williams %R - Universe E (SPY only)
5. Golden Cross / Death Cross - Universe E
6. SuperTrend - Universe B (sectors)

**Why start here**:
- ETFs have no survivorship bias
- Clean test of signal alpha
- Build confidence in infrastructure

---

### Phase 3: Large-Cap Strategies (Week 3)

**Focus**: Universe C (Large-Cap Liquid) - some bias but manageable

**Strategies to implement**:
1. Clenow Momentum Ranking
2. Donchian 20/10 Breakout
3. 52-Week High Breakout
4. Elder Impulse System
5. NR7 Narrow Range Breakout

**Universe Construction**:
- Pull S&P 500 constituents as of 2015-01-01
- Filter for market cap > $50B
- Filter for liquidity > $100M daily volume
- Fix universe for entire backtest (no look-ahead)

---

### Phase 4: High-Beta Strategies (Week 4)

**Focus**: Universe D (High-Beta Growth) - higher bias risk, document carefully

**Strategies to implement**:
1. Minervini VCP
2. Momentum Burst
3. Chandelier Exit system
4. Darvas Box

**Universe Construction**:
- At backtest start, screen for beta > 1.3, ATR > 2%
- Take top 50 by dollar volume
- Fix universe for entire backtest
- **Document**: "This universe was selected at 2015-01-01 based on trailing 1-year beta and ATR"

**Bias Mitigation**:
- Also test on Universe C (lower bias) for comparison
- If strategy only works on hand-picked names, it's not robust

---

### Phase 5: Comparison and Analysis (Week 5)

**Deliverables**:
1. Run all strategies with consistent parameters
2. Generate comparison table (Sharpe, CAGR, Max DD, Win Rate)
3. Identify top 5 performers
4. Run robustness tests:
   - Different time periods
   - Different universes
   - With/without regime filter
5. Document learnings

---

## Part 7: Metrics and Evaluation

### Primary Metrics

| Metric | Target | Notes |
|--------|--------|-------|
| Sharpe Ratio | > 0.8 | Risk-adjusted return |
| CAGR | > 12% | Beat passive after costs |
| Max Drawdown | < 25% | Survivable for real trading |
| Win Rate | Any | Lower OK if R:R > 2 |
| Profit Factor | > 1.5 | Gross profit / gross loss |
| Time in Market | < 80% | Some cash buffer |

### Secondary Metrics

- Average trade duration (should be days-weeks)
- Number of trades per year (too many = high friction)
- Worst single trade (outlier risk)
- Longest drawdown period (recovery time)
- Performance by regime (bull vs bear)

### Comparison Framework

```markdown
| Strategy | Universe | Sharpe | CAGR | MaxDD | Trades/Yr | Avg Days |
|----------|----------|--------|------|-------|-----------|----------|
| Clenow   | C        | 1.2    | 18%  | 22%   | 52        | 14       |
| Donchian | E        | 0.9    | 14%  | 18%   | 12        | 45       |
| ...      | ...      | ...    | ...  | ...   | ...       | ...      |
| SPY B&H  | -        | 0.6    | 10%  | 34%   | 0         | -        |
```

---

## Part 8: Bias Mitigation Checklist

### Before Each Backtest

- [ ] Universe defined at backtest START date, not current
- [ ] No future information in universe selection
- [ ] Indicators use only past data (no look-ahead)
- [ ] Entry on next bar's open (not same bar close)
- [ ] Slippage and commission included
- [ ] Delisted stocks handled (if applicable)

### Documentation Required

For each strategy, document:
1. **Universe rationale**: Why these stocks/ETFs?
2. **Parameter choices**: Why these values?
3. **Known biases**: What biases exist and why acceptable?
4. **Out-of-sample period**: What period is truly out-of-sample?

---

## Part 9: Risk Considerations

### What Could Go Wrong

1. **Curve fitting**: Strategy works on backtest, fails live
   - Mitigation: Walk-forward validation, simple rules, few parameters

2. **Regime change**: Strategy worked 2015-2020, fails 2021+
   - Mitigation: Test on multiple sub-periods, use regime filters

3. **Execution gap**: Can't get fills at backtest prices
   - Mitigation: Conservative slippage (0.1%), volume filters

4. **Survivorship bias**: Only testing winners
   - Mitigation: Use ETFs where possible, document bias

5. **Overfitting to specific tickers**: Works on NVDA, not others
   - Mitigation: Test on full universe, not cherry-picked stocks

---

## Part 10: Success Criteria

### Minimum Bar to Pass

A strategy is considered viable if:
1. Sharpe > 0.8 (meaningfully better than market)
2. CAGR > SPY buy-and-hold by 2%+
3. Max DD < 30% (or < SPY's max DD)
4. Works on intended universe (not just 1-2 stocks)
5. Consistent across sub-periods (no cliff in 2022)

### Bonus Points

- Works on multiple universes
- Simple rules (< 5 parameters)
- Logical edge hypothesis
- Regime filter improves results

---

## Summary: Priority Order

### Must Implement First (Lowest Bias)
1. **Dual Momentum (GEM)** - ETFs only, well-documented
2. **Sector Rotation** - Sector ETFs, pure signal alpha
3. **RSI-2 on SPY** - Single instrument, no stock picking
4. **Donchian on SPY** - Classic trend following

### Implement Second (Moderate Bias)
5. **Clenow Momentum** - Large-cap universe
6. **52-Week High Breakout** - Large-cap universe
7. **Elder Impulse** - Large-cap universe
8. **SuperTrend** - Sectors or SPY

### Implement Third (Higher Bias, Needs Care)
9. **Minervini VCP** - High-beta universe
10. **Momentum Burst** - High-beta universe
11. **Chandelier Exit** - High-beta universe

### Research Only (Complex/Unclear)
- NR7 (high whipsaw risk)
- Darvas Box (subjective elements)
- TSI/KST (less documented)

---

## Next Steps

1. **Approve this plan** (or suggest modifications)
2. **Set up infrastructure** (Phase 1)
3. **Start with ETF strategies** (Phase 2)
4. **Iterate based on results**
