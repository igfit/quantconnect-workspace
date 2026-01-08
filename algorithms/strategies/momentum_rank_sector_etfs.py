from AlgorithmImports import *

class MomentumRankSectorETFs(QCAlgorithm):
    """
    Momentum Ranking on Sector ETFs (No Single-Stock Bias)

    CONCEPT:
    - Use 11 sector ETFs instead of individual stocks
    - Rank by 3-month momentum
    - Hold TOP 3 sectors at 33% each
    - Monthly rebalance

    WHY THIS REMOVES BIAS:
    - Can't cherry-pick individual winners like NVDA
    - Sector rotation is a real, documented strategy
    - Tests if momentum signal works at sector level
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # 11 S&P Sector ETFs (SPDR)
        self.sectors = [
            "XLK",  # Technology
            "XLF",  # Financials
            "XLV",  # Healthcare
            "XLY",  # Consumer Discretionary
            "XLP",  # Consumer Staples
            "XLE",  # Energy
            "XLI",  # Industrials
            "XLB",  # Materials
            "XLU",  # Utilities
            "XLRE", # Real Estate
            "XLC",  # Communication Services
        ]

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
        top_sectors = [t[0] for t in ranked[:self.top_n]]

        for ticker in self.sectors:
            if ticker not in top_sectors:
                symbol = self.symbols[ticker]
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol)

        weight = 1.0 / self.top_n
        for ticker in top_sectors:
            symbol = self.symbols[ticker]
            self.set_holdings(symbol, weight)

        self.debug(f"Top {self.top_n} sectors: {top_sectors}")

    def on_data(self, data):
        pass
