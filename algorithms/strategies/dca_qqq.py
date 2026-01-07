from AlgorithmImports import *

class DCAQqq(QCAlgorithm):
    """Monthly DCA into QQQ (2020-2024) - $2,083/month"""

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.symbol = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        self.monthly_amount = 2083

        self.schedule.on(
            self.date_rules.month_start(self.symbol),
            self.time_rules.after_market_open(self.symbol, 30),
            self.monthly_purchase
        )

    def monthly_purchase(self):
        price = self.securities[self.symbol].price
        if price > 0:
            shares = int(self.monthly_amount / price)
            if shares > 0 and self.portfolio.cash >= shares * price:
                self.market_order(self.symbol, shares)

    def on_end_of_algorithm(self):
        self.log(f"DCA QQQ Final: ${self.portfolio.total_portfolio_value:,.2f}")
