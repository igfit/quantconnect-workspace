"""
Benchmark: Monthly DCA into SPY + QQQ - OOS (2015-2019)
"""

from AlgorithmImports import *


class BenchmarkDCAOOS(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2019, 12, 31)
        self.set_cash(100000)

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.set_benchmark(self.spy)

        self.monthly_investment = 1667
        self.last_investment_month = -1

        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.invest_monthly
        )

    def invest_monthly(self):
        current_month = self.time.month
        if current_month == self.last_investment_month:
            return
        if self.portfolio.cash < self.monthly_investment:
            return

        investment_per_symbol = self.monthly_investment / 2
        spy_price = self.securities[self.spy].price
        qqq_price = self.securities[self.qqq].price

        if spy_price > 0 and qqq_price > 0:
            spy_shares = int(investment_per_symbol / spy_price)
            qqq_shares = int(investment_per_symbol / qqq_price)
            if spy_shares > 0:
                self.market_order(self.spy, spy_shares)
            if qqq_shares > 0:
                self.market_order(self.qqq, qqq_shares)
            self.last_investment_month = current_month

    def on_data(self, data):
        pass
