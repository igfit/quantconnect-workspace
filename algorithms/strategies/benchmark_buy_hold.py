"""
Benchmark: Buy and Hold SPY + QQQ

Simple buy-and-hold strategy to benchmark against active strategies.
Invests 50% in SPY and 50% in QQQ at the start.

Period: 2020-01-01 to 2024-12-31
Initial Capital: $100,000
"""

from AlgorithmImports import *


class BenchmarkBuyHold(QCAlgorithm):
    """
    Buy and Hold Benchmark

    Buys SPY and QQQ on first day and holds for entire backtest.
    Used to benchmark active strategies against passive investing.
    """

    def initialize(self):
        # Match strategy factory settings
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Add securities
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol

        # Set benchmark
        self.set_benchmark(self.spy)

        # Track if we've bought
        self.invested = False

    def on_data(self, data):
        if self.invested:
            return

        # Wait for both symbols to have data
        if not data.contains_key(self.spy) or not data.contains_key(self.qqq):
            return

        # Invest 50% in each
        self.set_holdings(self.spy, 0.5)
        self.set_holdings(self.qqq, 0.5)

        self.invested = True
        self.log(f"BENCHMARK: Bought SPY and QQQ (50/50 split)")
