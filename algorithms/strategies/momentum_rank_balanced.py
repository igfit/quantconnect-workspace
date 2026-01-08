from AlgorithmImports import *

class MomentumRankBalanced(QCAlgorithm):
    """
    Momentum Ranking on Balanced Basket (Equal Sector Weights)

    CONCEPT:
    - 20 stocks: 2 per sector (not tech-heavy)
    - Rank by 3-month momentum
    - Hold TOP 5 at 20% each
    - Monthly rebalance

    BASKET (2 per sector - no cherry-picking):
    - Tech: CSCO, INTC (NOT NVDA/META - older, slower growth)
    - Financials: WFC, C (NOT JPM/GS - less stellar)
    - Healthcare: PFE, MRK (pharma, not biotech)
    - Consumer Disc: F, GM (autos, cyclical)
    - Consumer Staples: KO, PEP
    - Energy: XOM, CVX
    - Industrials: MMM, RTX
    - Materials: DOW, NEM
    - Utilities: DUK, SO
    - Real Estate: AMT, PLD
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Balanced basket - 2 per sector, avoiding obvious winners
        self.basket = [
            # Tech (older, slower growth - not AI winners)
            "CSCO", "INTC",
            # Financials (regional/diversified, not investment banks)
            "WFC", "C",
            # Healthcare (big pharma, not biotech)
            "PFE", "MRK",
            # Consumer Discretionary (autos - cyclical)
            "F", "GM",
            # Consumer Staples
            "KO", "PEP",
            # Energy
            "XOM", "CVX",
            # Industrials
            "MMM", "RTX",
            # Materials
            "DOW", "NEM",
            # Utilities
            "DUK", "SO",
            # Real Estate
            "AMT", "PLD",
        ]

        self.top_n = 5
        self.lookback = 63

        self.symbols = {}
        self.roc_ind = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.roc_ind[ticker] = self.rocp(symbol, self.lookback, Resolution.DAILY)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(self.lookback + 10, Resolution.DAILY)

        self.schedule.on(self.date_rules.month_start(),
                        self.time_rules.after_market_open("CSCO", 30),
                        self.rebalance)

    def rebalance(self):
        if self.is_warming_up:
            return

        momentum_scores = {}
        for ticker in self.basket:
            if self.roc_ind[ticker].is_ready:
                momentum_scores[ticker] = self.roc_ind[ticker].current.value

        if len(momentum_scores) < self.top_n:
            return

        ranked = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        top_tickers = [t[0] for t in ranked[:self.top_n]]

        for ticker in self.basket:
            if ticker not in top_tickers:
                symbol = self.symbols[ticker]
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol)

        weight = 1.0 / self.top_n
        for ticker in top_tickers:
            symbol = self.symbols[ticker]
            self.set_holdings(symbol, weight)

        self.debug(f"Top {self.top_n} (balanced): {top_tickers}")

    def on_data(self, data):
        pass
