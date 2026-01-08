"""
Universe E: Single Instrument

RATIONALE:
Some strategies are designed for single instruments. Testing on SPY/QQQ
measures pure signal alpha vs buy-and-hold. No stock picking involved.

LIQUIDITY: SPY and QQQ are the most liquid ETFs in the world
BIAS RISK: Zero (these ETFs will exist as long as US markets exist)

USE FOR:
- RSI-2 mean reversion
- Williams %R
- IBS (Internal Bar Strength) strategy
- Overnight edge
- Turn of month
- Golden cross / death cross
- Any indicator timing strategy
"""

from typing import List, Dict

# Single instrument universe
SINGLE_INSTRUMENT_UNIVERSE: Dict[str, Dict] = {
    "SPY": {
        "name": "S&P 500 ETF",
        "inception": "1993-01-22",
        "description": "Most liquid equity ETF, tracks S&P 500",
        "avg_daily_volume_millions": 80,
        "expense_ratio": 0.0945,
    },
    "QQQ": {
        "name": "Nasdaq 100 ETF",
        "inception": "1999-03-10",
        "description": "Tech-heavy large cap ETF, tracks Nasdaq 100",
        "avg_daily_volume_millions": 50,
        "expense_ratio": 0.20,
    },
    "IWM": {
        "name": "Russell 2000 ETF",
        "inception": "2000-05-22",
        "description": "Small cap ETF, more volatile than SPY",
        "avg_daily_volume_millions": 25,
        "expense_ratio": 0.19,
    },
    "DIA": {
        "name": "Dow Jones ETF",
        "inception": "1998-01-14",
        "description": "Blue chip 30 stocks, price-weighted",
        "avg_daily_volume_millions": 5,
        "expense_ratio": 0.16,
    },
}


def get_single_instrument_symbols(instrument: str = "SPY") -> List[str]:
    """
    Get single instrument for Universe E.

    Args:
        instrument: Which instrument to return ("SPY", "QQQ", "IWM", "DIA")

    Returns:
        List containing single ticker symbol
    """
    if instrument not in SINGLE_INSTRUMENT_UNIVERSE:
        raise ValueError(f"Unknown instrument: {instrument}. Available: {list(SINGLE_INSTRUMENT_UNIVERSE.keys())}")
    return [instrument]


def get_spy_only() -> List[str]:
    """Get SPY for pure S&P 500 signal alpha test"""
    return ["SPY"]


def get_qqq_only() -> List[str]:
    """Get QQQ for tech-heavy signal alpha test"""
    return ["QQQ"]


def get_spy_qqq() -> List[str]:
    """Get both SPY and QQQ for comparative testing"""
    return ["SPY", "QQQ"]


# Strategy recommendations for single instruments
STRATEGY_RECOMMENDATIONS = {
    "SPY": {
        "recommended_strategies": [
            "RSI-2 mean reversion",
            "Williams %R",
            "Golden/Death cross",
            "Turn of month",
            "Overnight edge",
            "IBS strategy",
        ],
        "notes": "SPY is less volatile than QQQ, may have lower returns but more consistent signals",
    },
    "QQQ": {
        "recommended_strategies": [
            "RSI-2 mean reversion",
            "Momentum burst",
            "Trend following",
            "Breakout strategies",
        ],
        "notes": "QQQ is more volatile, trend-following strategies may work better",
    },
    "IWM": {
        "recommended_strategies": [
            "Mean reversion",
            "January effect",
            "Small cap momentum",
        ],
        "notes": "IWM has different characteristics than large-cap ETFs",
    },
}


# Benchmark buy-and-hold returns (for reference)
BENCHMARK_RETURNS = {
    # 10-year CAGR estimates (2015-2024)
    "SPY": {"cagr_10yr": 12.0, "sharpe_10yr": 0.65, "max_dd": 34.0},
    "QQQ": {"cagr_10yr": 18.0, "sharpe_10yr": 0.75, "max_dd": 35.0},
    "IWM": {"cagr_10yr": 8.0, "sharpe_10yr": 0.45, "max_dd": 42.0},
    "DIA": {"cagr_10yr": 11.0, "sharpe_10yr": 0.60, "max_dd": 32.0},
}


def get_benchmark_stats(symbol: str) -> Dict:
    """Get benchmark buy-and-hold statistics for comparison"""
    if symbol not in BENCHMARK_RETURNS:
        raise ValueError(f"No benchmark data for: {symbol}")
    return BENCHMARK_RETURNS[symbol]


if __name__ == "__main__":
    print("Single Instrument Universe")
    print("=" * 50)

    print(f"\nAvailable instruments:")
    for ticker, info in SINGLE_INSTRUMENT_UNIVERSE.items():
        print(f"  {ticker}: {info['name']}")

    print(f"\nSPY benchmark stats:")
    print(get_benchmark_stats("SPY"))

    print(f"\nQQQ benchmark stats:")
    print(get_benchmark_stats("QQQ"))

    print(f"\nRecommended strategies for SPY:")
    print(STRATEGY_RECOMMENDATIONS["SPY"]["recommended_strategies"])
