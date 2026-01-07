from AlgorithmImports import *


class BuyAndHoldBenchmark(QCAlgorithm):
    """
    Buy and Hold Benchmark Strategy

    Strategy:
        - Buy and hold a single asset for the entire backtest period
        - Used to benchmark active strategies against passive investing

    Parameters:
        - ticker: Symbol to buy and hold (default: SPY)

    Universe: Single asset
    Rebalance: None (buy once at start)
    """

    def initialize(self):
        # Backtest period (same as MA Crossover)
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        # Configurable ticker - change this for different benchmarks
        self.ticker = self.get_parameter("ticker", "SPY")

        # Add the equity
        self.equity = self.add_equity(self.ticker, Resolution.DAILY)

        # Flag to track if we've entered
        self.invested = False

    def on_data(self, data):
        """Buy and hold - invest 100% on first valid data"""
        if self.invested:
            return

        if self.ticker in data and data[self.ticker] is not None:
            self.set_holdings(self.ticker, 1.0)
            self.invested = True
            self.debug(f"{self.time}: Bought 100% {self.ticker} at ${data[self.ticker].close:.2f}")

    def on_end_of_algorithm(self):
        """Log final portfolio value"""
        self.log(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
