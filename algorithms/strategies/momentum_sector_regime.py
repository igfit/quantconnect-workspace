from AlgorithmImports import *

class MomentumSectorRegimeFilter(QCAlgorithm):
    """
    Sector ETF Momentum + Regime Filter
    Only invest when SPY > 200 SMA (bull market)
    Go to cash in bear markets
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        self.sectors = [
            "XLK", "XLF", "XLV", "XLY", "XLP",
            "XLE", "XLI", "XLB", "XLU", "XLRE", "XLC",
        ]

        self.top_n = 3
        self.lookback = 63

        self.symbols = {}
        self.roc_ind = {}

        for ticker in self.sectors:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.roc_ind[ticker] = self.rocp(symbol, self.lookback, Resolution.DAILY)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(210, Resolution.DAILY)

        self.schedule.on(self.date_rules.month_start(),
                        self.time_rules.after_market_open("XLK", 30),
                        self.rebalance)

    def rebalance(self):
        if self.is_warming_up:
            return

        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        # Bear market - go to cash
        if not bull_market:
            self.liquidate()
            self.debug("BEAR MARKET - All cash")
            return

        momentum_scores = {}
        for ticker in self.sectors:
            if self.roc_ind[ticker].is_ready:
                momentum_scores[ticker] = self.roc_ind[ticker].current.value

        if len(momentum_scores) < self.top_n:
            return

        ranked = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        top_sectors = [t[0] for t in ranked[:self.top_n]]

        for ticker in self.sectors:
            if ticker not in top_sectors:
                symbol = self.symbols[ticker]
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol)

        weight = 1.0 / self.top_n
        for ticker in top_sectors:
            self.set_holdings(self.symbols[ticker], weight)

        self.debug(f"BULL: Top {self.top_n}: {top_sectors}")

    def on_data(self, data):
        pass
