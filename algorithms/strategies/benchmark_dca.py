"""
Benchmark: Monthly DCA into SPY + QQQ

Dollar-cost averaging strategy - invests fixed amount monthly.
Splits investment 50/50 between SPY and QQQ.

Period: 2020-01-01 to 2024-12-31
Initial Capital: $100,000 (invested gradually via DCA)
Monthly Investment: $1,667 (~$100k over 5 years = 60 months)
"""

from AlgorithmImports import *


class BenchmarkDCA(QCAlgorithm):
    """
    Monthly DCA Benchmark

    Invests a fixed amount on the first trading day of each month.
    Splits 50/50 between SPY and QQQ.
    Used to benchmark active strategies against passive DCA.
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

        # DCA settings
        # $100k over 60 months = ~$1,667/month
        self.monthly_investment = 1667
        self.last_investment_month = -1

        # Schedule monthly investment on first trading day
        self.schedule.on(
            self.date_rules.month_start(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.invest_monthly
        )

    def invest_monthly(self):
        """Invest fixed amount on first trading day of month"""
        current_month = self.time.month

        # Avoid double-investing in same month
        if current_month == self.last_investment_month:
            return

        # Check if we have enough cash
        if self.portfolio.cash < self.monthly_investment:
            return

        # Calculate shares to buy for each (50/50 split)
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
            self.log(f"DCA: Bought {spy_shares} SPY + {qqq_shares} QQQ (${self.monthly_investment})")

    def on_data(self, data):
        """Not used - we use scheduled events for DCA"""
        pass
