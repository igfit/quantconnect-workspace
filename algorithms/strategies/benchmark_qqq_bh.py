from AlgorithmImports import *

class BenchmarkQQQBuyHold(QCAlgorithm):
    """QQQ Buy-and-Hold Benchmark (2020-2024)"""

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.symbol = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

    def on_data(self, data):
        if not self.portfolio.invested:
            self.set_holdings(self.symbol, 1.0)

    def on_end_of_algorithm(self):
        self.log(f"QQQ Buy-Hold Final: ${self.portfolio.total_portfolio_value:,.2f}")
