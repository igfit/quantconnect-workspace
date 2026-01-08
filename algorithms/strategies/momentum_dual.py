from AlgorithmImports import *

class DualMomentumSector(QCAlgorithm):
    """
    Dual Momentum Strategy (Absolute + Relative)

    1. Relative momentum: Rank sectors by 3-month return
    2. Absolute momentum: Only invest if top sector > T-bills (positive momentum)
    3. If no positive momentum, go to bonds (AGG)

    Classic Gary Antonacci approach adapted for sectors
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        self.sectors = [
            "XLK", "XLF", "XLV", "XLY", "XLP",
            "XLE", "XLI", "XLB", "XLU", "XLRE", "XLC",
        ]

        # Safe haven when momentum is negative
        self.bonds = self.add_equity("AGG", Resolution.DAILY).symbol

        self.top_n = 3
        self.lookback = 63  # 3 months

        self.symbols = {}
        self.roc_ind = {}

        for ticker in self.sectors:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.roc_ind[ticker] = self.rocp(symbol, self.lookback, Resolution.DAILY)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(self.lookback + 10, Resolution.DAILY)

        self.schedule.on(self.date_rules.month_start(),
                        self.time_rules.after_market_open("XLK", 30),
                        self.rebalance)

    def rebalance(self):
        if self.is_warming_up:
            return

        momentum_scores = {}
        for ticker in self.sectors:
            if self.roc_ind[ticker].is_ready:
                momentum_scores[ticker] = self.roc_ind[ticker].current.value

        if len(momentum_scores) < self.top_n:
            return

        ranked = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)

        # Absolute momentum check: Is best sector positive?
        if ranked[0][1] <= 0:
            # All sectors negative - go to bonds
            self.liquidate()
            self.set_holdings(self.bonds, 1.0)
            self.debug("Negative momentum - 100% bonds")
            return

        # Select top N with positive momentum only
        top_sectors = []
        for ticker, mom in ranked[:self.top_n]:
            if mom > 0:
                top_sectors.append(ticker)

        if len(top_sectors) == 0:
            self.liquidate()
            self.set_holdings(self.bonds, 1.0)
            return

        # Liquidate bonds and non-top sectors
        if self.portfolio[self.bonds].invested:
            self.liquidate(self.bonds)

        for ticker in self.sectors:
            if ticker not in top_sectors:
                symbol = self.symbols[ticker]
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol)

        weight = 1.0 / len(top_sectors)
        for ticker in top_sectors:
            self.set_holdings(self.symbols[ticker], weight)

        self.debug(f"Top sectors: {top_sectors}")

    def on_data(self, data):
        pass
