# Universe Generation System

## Overview

A hybrid quantitative + qualitative system for generating a momentum-suitable stock universe.
Designed to capture stocks with characteristics similar to the successful hand-picked universe,
but using **rules-based selection** to minimize hindsight bias.

---

## Phase 1: Quantitative Screening (Automated)

### 1.1 Liquidity & Size Filters (Hard Requirements)

```python
QUANTITATIVE_FILTERS = {
    # Size - large enough to matter, small enough to have growth
    "market_cap_min": 20_000_000_000,      # $20B minimum
    "market_cap_max": 3_000_000_000_000,   # $3T max (avoid mega-cap concentration)

    # Liquidity - must be tradeable without market impact
    "avg_daily_volume_min": 200_000_000,   # $200M daily dollar volume
    "bid_ask_spread_max": 0.05,            # 5 bps max spread

    # Index membership (institutional quality signal)
    "index_member": ["SP500", "NASDAQ100"],

    # History - enough data for analysis
    "years_public_min": 3,
}
```

### 1.2 Financial Quality Filters

```python
QUALITY_FILTERS = {
    # Profitability
    "gross_margin_min": 0.30,              # 30%+ gross margin
    "operating_margin_min": 0.10,          # 10%+ operating margin
    "fcf_positive_years": 3,               # FCF positive 3 of last 5 years

    # Growth
    "revenue_growth_3y_cagr_min": 0.05,    # 5%+ revenue CAGR
    "revenue_growth_3y_cagr_max": 1.00,    # <100% (avoid unsustainable)

    # Balance Sheet
    "debt_to_equity_max": 2.0,             # Reasonable leverage
    "current_ratio_min": 1.0,              # Can pay short-term obligations

    # Returns
    "roe_min": 0.12,                       # 12%+ ROE
    "roic_min": 0.10,                      # 10%+ ROIC
}
```

### 1.3 Momentum Suitability Filters

```python
MOMENTUM_FILTERS = {
    # Volatility - enough movement to generate alpha
    "beta_min": 0.8,                       # Not too defensive
    "beta_max": 2.5,                       # Not too volatile
    "annual_volatility_min": 0.20,         # 20%+ annualized vol
    "annual_volatility_max": 0.80,         # <80% (avoid blow-up risk)

    # Trend characteristics
    "positive_months_pct_min": 0.50,       # More up months than down
    "max_drawdown_5y_max": 0.70,           # <70% max DD in 5 years
}
```

### 1.4 Sector Diversification Constraints

```python
SECTOR_CONSTRAINTS = {
    "tech_max": 0.50,                      # Max 50% in technology
    "financials_max": 0.20,                # Max 20% in financials
    "healthcare_max": 0.20,
    "consumer_max": 0.20,
    "industrials_max": 0.20,
    "min_sectors": 4,                      # At least 4 sectors represented
    "max_single_stock": 0.10,              # No stock >10% of universe
}
```

---

## Phase 2: Qualitative Assessment (LLM-Assisted)

### 2.1 Competitive Moat Analysis

**Prompt Template for Claude:**

```
Analyze {COMPANY} ({TICKER}) for competitive moat strength.

Rate each moat type 0-10:
1. Network Effects: Do more users make the product more valuable?
2. Switching Costs: How hard is it for customers to leave?
3. Cost Advantages: Does scale provide meaningful cost benefits?
4. Intangible Assets: Patents, brands, regulatory licenses?
5. Efficient Scale: Natural monopoly characteristics?

For each, provide:
- Score (0-10)
- Evidence (specific examples)
- Durability (how long will this moat last?)

Output JSON format:
{
  "ticker": "AAPL",
  "moat_scores": {
    "network_effects": 8,
    "switching_costs": 9,
    "cost_advantages": 7,
    "intangible_assets": 9,
    "efficient_scale": 5
  },
  "overall_moat": 8.5,
  "durability_years": 10,
  "key_risks": ["...", "..."],
  "reasoning": "..."
}
```

**Minimum Score: 6.0/10 overall moat to qualify**

### 2.2 Secular Tailwind Assessment

**Prompt Template:**

```
Analyze {COMPANY} ({TICKER}) for exposure to secular growth trends.

Consider these mega-trends:
1. AI / Machine Learning
2. Cloud Computing / Digital Transformation
3. Clean Energy / Electrification
4. Healthcare Innovation / Aging Demographics
5. Fintech / Digital Payments
6. Cybersecurity
7. E-commerce / Digital Advertising
8. Automation / Robotics

For each relevant trend:
- Exposure level (High/Medium/Low/None)
- Revenue % tied to this trend
- Growth trajectory (Accelerating/Stable/Decelerating)

Output JSON:
{
  "ticker": "MSFT",
  "tailwinds": [
    {"trend": "AI/ML", "exposure": "High", "revenue_pct": 15, "trajectory": "Accelerating"},
    {"trend": "Cloud", "exposure": "High", "revenue_pct": 40, "trajectory": "Stable"}
  ],
  "headwinds": [
    {"risk": "PC market decline", "severity": "Medium"}
  ],
  "net_tailwind_score": 8,
  "reasoning": "..."
}
```

**Minimum Score: 5.0/10 net tailwind score**

### 2.3 Management Quality Assessment

**Prompt Template:**

```
Analyze {COMPANY} ({TICKER}) management quality.

Evaluate:
1. Capital Allocation History (acquisitions, buybacks, dividends)
2. Execution Track Record (hitting guidance, delivering products)
3. Insider Ownership & Alignment
4. Communication Transparency
5. Strategic Vision & Adaptability
6. Compensation Structure (aligned with shareholders?)

Red Flags to Check:
- Excessive related-party transactions
- Frequent strategy pivots
- High executive turnover
- Aggressive accounting
- Overpromising/underdelivering pattern

Output JSON:
{
  "ticker": "AMZN",
  "management_score": 9,
  "capital_allocation": 8,
  "execution": 9,
  "alignment": 9,
  "transparency": 7,
  "red_flags": [],
  "key_strengths": ["Long-term focus", "Operational excellence"],
  "reasoning": "..."
}
```

**Minimum Score: 6.0/10 management quality**

### 2.4 Disruption Risk Assessment

**Prompt Template:**

```
Analyze {COMPANY} ({TICKER}) for disruption risk.

Consider:
1. Technology Disruption: Could new tech make their business obsolete?
2. Regulatory Risk: Antitrust, new regulations, policy changes?
3. Competitive Threats: New entrants, changing competitive dynamics?
4. Business Model Risk: Is the business model sustainable?
5. Geopolitical Risk: Supply chain, market access issues?

For each risk:
- Probability (next 5 years)
- Severity if occurs
- Company's defensive position

Output JSON:
{
  "ticker": "META",
  "disruption_risks": [
    {"type": "Regulatory", "probability": 0.6, "severity": "High", "defense": "Medium"},
    {"type": "Technology", "probability": 0.4, "severity": "High", "defense": "High"}
  ],
  "overall_disruption_risk": 6,  // 10 = highest risk
  "time_horizon_concern": "5-10 years",
  "reasoning": "..."
}
```

**Maximum Score: 7.0/10 (higher = more risk, exclude if >7)**

---

## Phase 3: Composite Scoring & Selection

### 3.1 Scoring Formula

```python
def calculate_composite_score(stock):
    """
    Combine quantitative and qualitative factors into single score.
    """
    # Quantitative factors (40% weight)
    quant_score = (
        normalize(stock.revenue_growth, 0, 0.30) * 0.10 +
        normalize(stock.gross_margin, 0.30, 0.80) * 0.08 +
        normalize(stock.roe, 0.10, 0.40) * 0.08 +
        normalize(stock.roic, 0.10, 0.35) * 0.08 +
        normalize(1 - stock.debt_to_equity/3, 0, 1) * 0.06
    )

    # Qualitative factors (40% weight) - from LLM
    qual_score = (
        stock.moat_score / 10 * 0.15 +
        stock.tailwind_score / 10 * 0.10 +
        stock.management_score / 10 * 0.10 +
        (10 - stock.disruption_risk) / 10 * 0.05
    )

    # Momentum factors (20% weight)
    mom_score = (
        normalize(stock.momentum_12m, -0.20, 0.50) * 0.10 +
        normalize(stock.momentum_6m, -0.15, 0.40) * 0.05 +
        normalize(stock.relative_strength_vs_spy, 0.8, 1.5) * 0.05
    )

    return quant_score + qual_score + mom_score
```

### 3.2 Selection Algorithm

```python
def generate_universe(date, target_size=30):
    """
    Generate universe for a given date.
    """
    # Step 1: Apply quantitative filters
    candidates = apply_quantitative_filters(all_stocks, date)
    print(f"After quant filters: {len(candidates)} stocks")

    # Step 2: Get LLM qualitative assessments
    for stock in candidates:
        stock.moat_score = get_llm_moat_assessment(stock)
        stock.tailwind_score = get_llm_tailwind_assessment(stock)
        stock.management_score = get_llm_management_assessment(stock)
        stock.disruption_risk = get_llm_disruption_assessment(stock)

    # Step 3: Apply qualitative filters
    candidates = [s for s in candidates if
                  s.moat_score >= 6.0 and
                  s.tailwind_score >= 5.0 and
                  s.management_score >= 6.0 and
                  s.disruption_risk <= 7.0]
    print(f"After qual filters: {len(candidates)} stocks")

    # Step 4: Calculate composite scores
    for stock in candidates:
        stock.composite_score = calculate_composite_score(stock)

    # Step 5: Apply sector constraints
    candidates.sort(key=lambda x: -x.composite_score)
    universe = apply_sector_constraints(candidates, target_size)

    return universe
```

---

## Phase 4: Annual Review Process

### 4.1 Review Triggers

Run full review when:
1. **Scheduled**: First trading day of each year
2. **Triggered**: Stock drops >50% from 52-week high
3. **Triggered**: Major acquisition/merger announced
4. **Triggered**: Earnings miss >20% + guidance cut

### 4.2 Annual Review Checklist

```markdown
## Annual Universe Review - {YEAR}

### Stocks to REMOVE (failed criteria):
| Ticker | Reason | Replacement Candidate |
|--------|--------|----------------------|
| XXX | Gross margin fell below 30% | YYY |
| ZZZ | Moat score dropped to 5.2 | AAA |

### Stocks to ADD (newly qualified):
| Ticker | Composite Score | Key Strengths |
|--------|-----------------|---------------|
| BBB | 8.2 | Strong AI tailwind, 9.0 moat |

### Stocks to KEEP (re-validated):
| Ticker | Score Change | Notes |
|--------|--------------|-------|
| AAPL | 8.5 → 8.3 | Slight margin compression |

### Sector Allocation Check:
| Sector | Current % | Target Max | Action |
|--------|-----------|------------|--------|
| Tech | 52% | 50% | Reduce by 1 stock |
```

### 4.3 LLM Review Prompt

```
You are reviewing the investment universe for annual rebalancing.

Current Universe: {LIST_OF_TICKERS}
Date: {REVIEW_DATE}

For each stock, assess:
1. Has the competitive moat strengthened or weakened?
2. Any new disruption risks emerged?
3. Is management still executing well?
4. Have secular tailwinds accelerated or faded?

Also suggest:
1. Stocks that should be REMOVED (and why)
2. New stocks that should be ADDED (and why)
3. Sector allocation adjustments needed

Consider recent developments:
- Earnings reports from past year
- Major acquisitions or divestitures
- Competitive landscape changes
- Regulatory developments

Output a structured review with specific recommendations.
```

---

## Phase 5: Implementation

### 5.1 Data Sources

| Data Type | Source | Update Frequency |
|-----------|--------|------------------|
| Price/Volume | QuantConnect, Yahoo Finance | Daily |
| Fundamentals | SEC filings, FactSet, Bloomberg | Quarterly |
| Analyst Estimates | IBES, FactSet | Monthly |
| News/Events | News APIs, SEC filings | Real-time |
| Qualitative | Claude API | On-demand |

### 5.2 Automation Pipeline

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Quant Screen   │────▶│  LLM Analysis   │────▶│  Final Scoring  │
│  (Python/SQL)   │     │  (Claude API)   │     │  & Selection    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
   ~200 stocks            ~80 stocks              30 stocks
   (filters)              (+ scores)             (universe)
```

### 5.3 Cost Estimate

| Component | Cost/Year | Notes |
|-----------|-----------|-------|
| Data feeds | $0-500 | Yahoo Finance free, premium optional |
| Claude API | $50-200 | ~100 analyses/year @ $0.50-2 each |
| Compute | $0-100 | Can run on laptop |
| **Total** | **$50-800** | Mostly API costs |

---

## Appendix: Sample LLM Output

### Example: Moat Analysis for NVDA

```json
{
  "ticker": "NVDA",
  "analysis_date": "2024-01-15",
  "moat_scores": {
    "network_effects": 7,
    "switching_costs": 8,
    "cost_advantages": 9,
    "intangible_assets": 9,
    "efficient_scale": 6
  },
  "overall_moat": 8.5,
  "durability_years": 7,
  "key_risks": [
    "AMD/Intel catching up in AI chips",
    "Custom silicon from hyperscalers (Google TPU, Amazon Inferentia)",
    "China export restrictions limiting TAM"
  ],
  "reasoning": "NVIDIA has built an exceptional moat through CUDA ecosystem lock-in (switching costs), manufacturing scale with TSMC (cost advantages), and AI/ML patents (intangibles). The CUDA software ecosystem is particularly sticky - rewriting ML frameworks for other hardware is costly. However, durability is limited to ~7 years as competitors will eventually close the gap and hyperscalers develop custom chips.",
  "recommendation": "INCLUDE - Strong moat despite risks"
}
```

---

## Key Principles

1. **Rules over discretion**: Every decision has explicit criteria
2. **LLM for judgment, not data**: Use Claude for qualitative assessment, not data retrieval
3. **Annual refresh**: Universe should evolve, not be static
4. **Sector balance**: Prevent over-concentration in any one sector
5. **Transparency**: Document every inclusion/exclusion decision
6. **Backward-compatible**: Can backtest the universe generation rules

---

## Limitations & Honest Acknowledgments

1. **Some hindsight is unavoidable**: We know what characteristics worked
2. **LLM assessments are point-in-time**: Re-run for historical backtests
3. **Quality is subjective**: Different analysts may score differently
4. **Moats can erode quickly**: Annual review may miss fast changes
5. **Not a guarantee**: Even good companies can underperform
