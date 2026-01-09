"""
Benchmark: Buy and Hold SPY + QQQ - OOS (2015-2019)
"""

from AlgorithmImports import *


class BenchmarkBuyHoldOOS(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2019, 12, 31)
        self.set_cash(100000)

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.set_benchmark(self.spy)
        self.invested = False

    def on_data(self, data):
        if self.invested:
            return
        if not data.contains_key(self.spy) or not data.contains_key(self.qqq):
            return
        self.set_holdings(self.spy, 0.5)
        self.set_holdings(self.qqq, 0.5)
        self.invested = True
