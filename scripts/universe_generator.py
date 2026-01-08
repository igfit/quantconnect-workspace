#!/usr/bin/env python3
"""
Universe Generator - Systematic stock selection for momentum strategies

This script implements a hybrid quantitative + qualitative approach to
generate a trading universe, using Claude for qualitative assessments.

Usage:
    python universe_generator.py --year 2024 --size 30
    python universe_generator.py --review  # Annual review mode
"""

import json
import os
from dataclasses import dataclass
from typing import Optional

# Configuration
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

@dataclass
class QuantFilters:
    """Hard quantitative filters - must pass all"""
    market_cap_min: float = 20e9           # $20B
    market_cap_max: float = 3e12           # $3T
    avg_daily_volume_min: float = 200e6    # $200M
    gross_margin_min: float = 0.30         # 30%
    revenue_growth_min: float = 0.05       # 5% CAGR
    roe_min: float = 0.12                  # 12%
    debt_to_equity_max: float = 2.0
    years_public_min: int = 3

@dataclass
class QualFilters:
    """Qualitative score thresholds"""
    moat_score_min: float = 6.0
    tailwind_score_min: float = 5.0
    management_score_min: float = 6.0
    disruption_risk_max: float = 7.0

@dataclass
class SectorConstraints:
    """Prevent over-concentration"""
    tech_max: float = 0.50
    financials_max: float = 0.20
    healthcare_max: float = 0.20
    consumer_max: float = 0.20
    industrials_max: float = 0.20
    energy_max: float = 0.15
    min_sectors: int = 4

@dataclass
class Stock:
    """Stock with all scores"""
    ticker: str
    sector: str
    market_cap: float

    # Quantitative
    gross_margin: float = 0
    revenue_growth: float = 0
    roe: float = 0
    roic: float = 0
    debt_to_equity: float = 0

    # Qualitative (from LLM)
    moat_score: float = 0
    tailwind_score: float = 0
    management_score: float = 0
    disruption_risk: float = 0

    # Momentum
    momentum_12m: float = 0
    momentum_6m: float = 0

    # Final
    composite_score: float = 0


def get_moat_analysis_prompt(ticker: str, company_name: str) -> str:
    """Generate prompt for moat analysis"""
    return f"""Analyze {company_name} ({ticker}) for competitive moat strength.

Rate each moat type 0-10 (10 = strongest):
1. Network Effects: Do more users make the product more valuable?
2. Switching Costs: How hard is it for customers to leave?
3. Cost Advantages: Does scale provide meaningful cost benefits?
4. Intangible Assets: Patents, brands, regulatory licenses?
5. Efficient Scale: Natural monopoly characteristics?

Consider real evidence, not just theory. Be critical.

Output ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "ticker": "{ticker}",
  "moat_scores": {{
    "network_effects": <0-10>,
    "switching_costs": <0-10>,
    "cost_advantages": <0-10>,
    "intangible_assets": <0-10>,
    "efficient_scale": <0-10>
  }},
  "overall_moat": <weighted average 0-10>,
  "durability_years": <how long will moat last>,
  "key_risks": ["risk1", "risk2"],
  "reasoning": "<2-3 sentence summary>"
}}"""


def get_tailwind_analysis_prompt(ticker: str, company_name: str) -> str:
    """Generate prompt for secular tailwind analysis"""
    return f"""Analyze {company_name} ({ticker}) for exposure to secular growth trends.

Consider these mega-trends:
1. AI / Machine Learning
2. Cloud Computing / Digital Transformation
3. Clean Energy / Electrification
4. Healthcare Innovation / Aging Demographics
5. Fintech / Digital Payments
6. Cybersecurity
7. E-commerce / Digital Advertising
8. Automation / Robotics

Also consider headwinds (declining trends hurting the business).

Output ONLY valid JSON:
{{
  "ticker": "{ticker}",
  "tailwinds": [
    {{"trend": "<name>", "exposure": "High/Medium/Low", "revenue_pct": <0-100>}}
  ],
  "headwinds": [
    {{"risk": "<description>", "severity": "High/Medium/Low"}}
  ],
  "net_tailwind_score": <0-10, 10=strongest tailwinds>,
  "reasoning": "<2-3 sentence summary>"
}}"""


def get_management_analysis_prompt(ticker: str, company_name: str) -> str:
    """Generate prompt for management quality analysis"""
    return f"""Analyze {company_name} ({ticker}) management quality.

Evaluate:
1. Capital Allocation History (acquisitions, buybacks, dividends track record)
2. Execution Track Record (hitting guidance, delivering products on time)
3. Insider Ownership & Alignment (do executives own meaningful stock?)
4. Communication Transparency (honest about challenges?)
5. Strategic Vision (clear long-term strategy?)

Check for red flags:
- Excessive related-party transactions
- Aggressive accounting practices
- High executive turnover
- Overpromising / underdelivering pattern

Output ONLY valid JSON:
{{
  "ticker": "{ticker}",
  "management_score": <0-10>,
  "capital_allocation": <0-10>,
  "execution": <0-10>,
  "alignment": <0-10>,
  "transparency": <0-10>,
  "red_flags": ["flag1", "flag2"] or [],
  "reasoning": "<2-3 sentence summary>"
}}"""


def get_disruption_analysis_prompt(ticker: str, company_name: str) -> str:
    """Generate prompt for disruption risk analysis"""
    return f"""Analyze {company_name} ({ticker}) for disruption risk over the next 5 years.

Consider:
1. Technology Disruption: Could new tech make their business obsolete?
2. Regulatory Risk: Antitrust, new regulations, policy changes?
3. Competitive Threats: New entrants, intensifying competition?
4. Business Model Risk: Is the model sustainable? Margin pressure?
5. Geopolitical Risk: Supply chain, China exposure, trade wars?

For each material risk, estimate probability and severity.

Output ONLY valid JSON:
{{
  "ticker": "{ticker}",
  "disruption_risks": [
    {{
      "type": "<category>",
      "description": "<specific risk>",
      "probability": <0.0-1.0>,
      "severity": "High/Medium/Low"
    }}
  ],
  "overall_disruption_risk": <0-10, 10=highest risk>,
  "time_horizon_concern": "<when risk most acute>",
  "reasoning": "<2-3 sentence summary>"
}}"""


def calculate_composite_score(stock: Stock) -> float:
    """
    Calculate composite score combining all factors.

    Weights:
    - Quantitative: 40%
    - Qualitative: 40%
    - Momentum: 20%
    """
    def normalize(value, min_val, max_val):
        return max(0, min(1, (value - min_val) / (max_val - min_val)))

    # Quantitative (40%)
    quant_score = (
        normalize(stock.revenue_growth, 0, 0.30) * 0.10 +
        normalize(stock.gross_margin, 0.30, 0.80) * 0.08 +
        normalize(stock.roe, 0.10, 0.40) * 0.08 +
        normalize(stock.roic, 0.10, 0.35) * 0.08 +
        normalize(1 - stock.debt_to_equity/3, 0, 1) * 0.06
    )

    # Qualitative (40%)
    qual_score = (
        stock.moat_score / 10 * 0.15 +
        stock.tailwind_score / 10 * 0.10 +
        stock.management_score / 10 * 0.10 +
        (10 - stock.disruption_risk) / 10 * 0.05
    )

    # Momentum (20%)
    mom_score = (
        normalize(stock.momentum_12m, -0.20, 0.50) * 0.10 +
        normalize(stock.momentum_6m, -0.15, 0.40) * 0.10
    )

    return quant_score + qual_score + mom_score


def get_annual_review_prompt(current_universe: list, year: int) -> str:
    """Generate prompt for annual universe review"""
    tickers = ", ".join(current_universe)
    return f"""You are conducting the annual investment universe review for {year}.

Current Universe ({len(current_universe)} stocks):
{tickers}

Please analyze each stock and provide:

1. STOCKS TO REMOVE (if any):
   - Which stocks no longer meet quality criteria?
   - Has the competitive moat weakened significantly?
   - Any major red flags emerged?

2. STOCKS TO ADD (if any):
   - Which stocks newly qualify based on our criteria?
   - Strong moat, secular tailwinds, quality management
   - Market cap >$20B, profitable, reasonable growth

3. SECTOR BALANCE:
   - Is tech over-concentrated (>50%)?
   - Are we missing exposure to important sectors?

Criteria reminder:
- Moat score >= 6.0
- Tailwind score >= 5.0
- Management score >= 6.0
- Disruption risk <= 7.0
- Profitable with >30% gross margin
- Revenue growth >5%

Output structured JSON:
{{
  "review_year": {year},
  "stocks_to_remove": [
    {{"ticker": "XXX", "reason": "...", "replacement": "YYY"}}
  ],
  "stocks_to_add": [
    {{"ticker": "ZZZ", "score_estimate": 7.5, "rationale": "..."}}
  ],
  "stocks_to_keep": [
    {{"ticker": "AAA", "notes": "Still strong"}}
  ],
  "sector_adjustments": "...",
  "overall_assessment": "..."
}}"""


# Example usage and testing
if __name__ == "__main__":
    print("=" * 70)
    print("Universe Generator - Systematic Stock Selection")
    print("=" * 70)

    # Example: Current hand-picked universe characteristics
    current_universe = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META",
        "TSLA", "AMD", "NFLX", "ADBE", "CRM",
        "ORCL", "SHOP", "NOW", "AVGO", "QCOM",
        "COST", "HD", "TXN", "LLY", "UNH",
        "JPM", "GS", "MA", "V", "CAT", "DE"
    ]

    print(f"\nCurrent universe: {len(current_universe)} stocks")
    print(f"Stocks: {', '.join(current_universe)}")

    print("\n" + "-" * 70)
    print("EXAMPLE LLM PROMPTS")
    print("-" * 70)

    print("\n1. MOAT ANALYSIS PROMPT (for AAPL):")
    print(get_moat_analysis_prompt("AAPL", "Apple Inc")[:500] + "...")

    print("\n2. TAILWIND ANALYSIS PROMPT (for MSFT):")
    print(get_tailwind_analysis_prompt("MSFT", "Microsoft Corp")[:500] + "...")

    print("\n3. ANNUAL REVIEW PROMPT:")
    print(get_annual_review_prompt(current_universe, 2025)[:800] + "...")

    print("\n" + "=" * 70)
    print("To run with actual API calls, set ANTHROPIC_API_KEY environment variable")
    print("=" * 70)
