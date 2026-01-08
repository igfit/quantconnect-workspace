"""
Core Indicator Utilities

Helper functions and classes for working with QuantConnect indicators.
These are used across multiple strategies in the factory.
"""

from typing import Dict, Optional, Any
from AlgorithmImports import *


class IndicatorHelper:
    """
    Helper class for managing indicators in a strategy.

    Usage:
        self.helper = IndicatorHelper(self)
        self.helper.add_sma(symbol, "sma50", 50)
        self.helper.add_rsi(symbol, "rsi14", 14)

        if self.helper.is_ready(symbol):
            sma_val = self.helper.get(symbol, "sma50")
    """

    def __init__(self, algorithm: QCAlgorithm):
        """
        Initialize helper with reference to algorithm.

        Args:
            algorithm: The QCAlgorithm instance
        """
        self.algo = algorithm
        self.indicators: Dict[str, Dict[str, Any]] = {}  # {symbol: {name: indicator}}
        self.prev_values: Dict[str, Dict[str, float]] = {}  # For crossover detection

    def add_sma(self, symbol, name: str, period: int, resolution: Resolution = Resolution.DAILY):
        """Add a Simple Moving Average indicator"""
        self._ensure_symbol(symbol)
        self.indicators[symbol][name] = self.algo.sma(symbol, period, resolution)
        return self.indicators[symbol][name]

    def add_ema(self, symbol, name: str, period: int, resolution: Resolution = Resolution.DAILY):
        """Add an Exponential Moving Average indicator"""
        self._ensure_symbol(symbol)
        self.indicators[symbol][name] = self.algo.ema(symbol, period, resolution)
        return self.indicators[symbol][name]

    def add_rsi(self, symbol, name: str, period: int = 14, resolution: Resolution = Resolution.DAILY):
        """Add an RSI indicator"""
        self._ensure_symbol(symbol)
        self.indicators[symbol][name] = self.algo.rsi(symbol, period, MovingAverageType.WILDERS, resolution)
        return self.indicators[symbol][name]

    def add_roc(self, symbol, name: str, period: int, resolution: Resolution = Resolution.DAILY):
        """Add a Rate of Change indicator"""
        self._ensure_symbol(symbol)
        self.indicators[symbol][name] = self.algo.roc(symbol, period, resolution)
        return self.indicators[symbol][name]

    def add_atr(self, symbol, name: str, period: int = 14, resolution: Resolution = Resolution.DAILY):
        """Add an Average True Range indicator"""
        self._ensure_symbol(symbol)
        self.indicators[symbol][name] = self.algo.atr(symbol, period, resolution)
        return self.indicators[symbol][name]

    def add_macd(self, symbol, name: str, fast: int = 12, slow: int = 26, signal: int = 9,
                 resolution: Resolution = Resolution.DAILY):
        """Add a MACD indicator"""
        self._ensure_symbol(symbol)
        self.indicators[symbol][name] = self.algo.macd(symbol, fast, slow, signal, resolution)
        return self.indicators[symbol][name]

    def add_bb(self, symbol, name: str, period: int = 20, k: float = 2,
               resolution: Resolution = Resolution.DAILY):
        """Add Bollinger Bands indicator"""
        self._ensure_symbol(symbol)
        self.indicators[symbol][name] = self.algo.bb(symbol, period, k, resolution)
        return self.indicators[symbol][name]

    def add_adx(self, symbol, name: str, period: int = 14):
        """Add ADX indicator"""
        self._ensure_symbol(symbol)
        self.indicators[symbol][name] = self.algo.adx(symbol, period)
        return self.indicators[symbol][name]

    def add_stoch(self, symbol, name: str, period: int = 14, k_period: int = 3, d_period: int = 3,
                  resolution: Resolution = Resolution.DAILY):
        """Add Stochastic indicator"""
        self._ensure_symbol(symbol)
        self.indicators[symbol][name] = self.algo.sto(symbol, period, k_period, d_period, resolution)
        return self.indicators[symbol][name]

    def add_mom(self, symbol, name: str, period: int, resolution: Resolution = Resolution.DAILY):
        """Add Momentum indicator"""
        self._ensure_symbol(symbol)
        self.indicators[symbol][name] = self.algo.mom(symbol, period, resolution)
        return self.indicators[symbol][name]

    def add_williams_r(self, symbol, name: str, period: int = 14, resolution: Resolution = Resolution.DAILY):
        """Add Williams %R indicator"""
        self._ensure_symbol(symbol)
        self.indicators[symbol][name] = self.algo.wilr(symbol, period, resolution)
        return self.indicators[symbol][name]

    def add_donchian(self, symbol, name: str, period: int = 20, resolution: Resolution = Resolution.DAILY):
        """Add Donchian Channel indicator"""
        self._ensure_symbol(symbol)
        self.indicators[symbol][name] = self.algo.dchl(symbol, period, period, resolution)
        return self.indicators[symbol][name]

    def get(self, symbol, name: str) -> Optional[float]:
        """Get current indicator value"""
        indicators = self.indicators.get(symbol, {})
        if name not in indicators:
            return None

        ind = indicators[name]
        if hasattr(ind, 'current'):
            return float(ind.current.value)
        return None

    def get_raw(self, symbol, name: str):
        """Get the raw indicator object"""
        return self.indicators.get(symbol, {}).get(name)

    def is_ready(self, symbol) -> bool:
        """Check if all indicators for symbol are ready"""
        indicators = self.indicators.get(symbol, {})
        for ind in indicators.values():
            if hasattr(ind, 'is_ready') and not ind.is_ready:
                return False
        return True

    def update_prev_values(self, symbol):
        """Store current values for next-bar crossover detection"""
        if symbol not in self.prev_values:
            self.prev_values[symbol] = {}

        for name, ind in self.indicators.get(symbol, {}).items():
            if hasattr(ind, 'is_ready') and ind.is_ready:
                self.prev_values[symbol][name] = float(ind.current.value)

        # Also store price
        if symbol in self.algo.securities:
            self.prev_values[symbol]["price"] = float(self.algo.securities[symbol].price)

    def get_prev(self, symbol, name: str) -> Optional[float]:
        """Get previous bar's indicator value"""
        return self.prev_values.get(symbol, {}).get(name)

    def crosses_above(self, symbol, indicator_name: str, threshold: float) -> bool:
        """Check if indicator crossed above threshold"""
        curr = self.get(symbol, indicator_name)
        prev = self.get_prev(symbol, indicator_name)

        if curr is None or prev is None:
            return False

        return prev <= threshold < curr

    def crosses_below(self, symbol, indicator_name: str, threshold: float) -> bool:
        """Check if indicator crossed below threshold"""
        curr = self.get(symbol, indicator_name)
        prev = self.get_prev(symbol, indicator_name)

        if curr is None or prev is None:
            return False

        return prev >= threshold > curr

    def indicator_crosses_above(self, symbol, ind1_name: str, ind2_name: str) -> bool:
        """Check if indicator1 crossed above indicator2"""
        curr1 = self.get(symbol, ind1_name)
        prev1 = self.get_prev(symbol, ind1_name)
        curr2 = self.get(symbol, ind2_name)
        prev2 = self.get_prev(symbol, ind2_name)

        if any(v is None for v in [curr1, prev1, curr2, prev2]):
            return False

        return prev1 <= prev2 and curr1 > curr2

    def indicator_crosses_below(self, symbol, ind1_name: str, ind2_name: str) -> bool:
        """Check if indicator1 crossed below indicator2"""
        curr1 = self.get(symbol, ind1_name)
        prev1 = self.get_prev(symbol, ind1_name)
        curr2 = self.get(symbol, ind2_name)
        prev2 = self.get_prev(symbol, ind2_name)

        if any(v is None for v in [curr1, prev1, curr2, prev2]):
            return False

        return prev1 >= prev2 and curr1 < curr2

    def _ensure_symbol(self, symbol):
        """Ensure symbol exists in indicators dict"""
        if symbol not in self.indicators:
            self.indicators[symbol] = {}


# ============================================================================
# Standalone Helper Functions
# ============================================================================

def calculate_roc(prices: list, period: int) -> Optional[float]:
    """
    Calculate Rate of Change.

    Args:
        prices: List of prices (oldest first)
        period: Lookback period

    Returns:
        ROC as percentage (e.g., 0.05 = 5%)
    """
    if len(prices) < period + 1:
        return None

    current = prices[-1]
    past = prices[-(period + 1)]

    if past == 0:
        return None

    return (current - past) / past


def calculate_atr_pct(atr_value: float, price: float) -> float:
    """
    Calculate ATR as percentage of price.

    Args:
        atr_value: ATR indicator value
        price: Current price

    Returns:
        ATR as percentage (e.g., 0.02 = 2%)
    """
    if price <= 0:
        return 0
    return atr_value / price


def is_above_sma(price: float, sma_value: float) -> bool:
    """Check if price is above SMA"""
    return price > sma_value


def crosses_above(current: float, previous: float, threshold: float) -> bool:
    """Check if value crossed above threshold"""
    return previous <= threshold < current


def crosses_below(current: float, previous: float, threshold: float) -> bool:
    """Check if value crossed below threshold"""
    return previous >= threshold > current


def calculate_momentum_score(roc_values: Dict[str, float]) -> Dict[str, int]:
    """
    Rank symbols by momentum (ROC).

    Args:
        roc_values: Dict of {symbol: roc_value}

    Returns:
        Dict of {symbol: rank} where 1 = highest momentum
    """
    # Sort by ROC descending
    sorted_symbols = sorted(roc_values.items(), key=lambda x: x[1], reverse=True)

    ranks = {}
    for rank, (symbol, _) in enumerate(sorted_symbols, 1):
        ranks[symbol] = rank

    return ranks


def calculate_relative_strength(price: float, benchmark_price: float,
                                 price_prev: float, benchmark_prev: float) -> float:
    """
    Calculate relative strength vs benchmark.

    Args:
        price: Current price
        benchmark_price: Current benchmark price
        price_prev: Previous price (e.g., 20 days ago)
        benchmark_prev: Previous benchmark price

    Returns:
        Relative strength (>1 = outperforming, <1 = underperforming)
    """
    if benchmark_prev == 0 or price_prev == 0:
        return 1.0

    stock_return = price / price_prev
    benchmark_return = benchmark_price / benchmark_prev

    if benchmark_return == 0:
        return 1.0

    return stock_return / benchmark_return
