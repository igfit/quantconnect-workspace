from AlgorithmImports import *

class MomentumRankValueStocks(QCAlgorithm):
    """
    Momentum Ranking on Value/Dividend Stocks (Anti-Growth)

    CONCEPT:
    - 20 value/dividend stocks (opposite of growth basket)
    - These UNDERPERFORMED 2020-2024
    - If momentum signal works, should still generate alpha
    - Tests true signal edge vs stock selection

    BASKET: High dividend, low growth, value stocks
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Value/Dividend stocks - NOT growth winners
        self.basket = [
            # Telecoms (value traps 2020-2024)
            "T", "VZ",
            # Big Pharma (slow growers)
            "PFE", "BMY", "ABBV",
            # Consumer Staples (defensive)
            "KO", "PG", "CL", "GIS",
            # Utilities (bond proxies)
            "DUK", "SO", "D",
            # REITs
            "O", "VTR",
            # Banks (not investment banks)
            "WFC", "USB", "PNC",
            # Energy (pre-2022 underperformers)
            "XOM", "CVX", "COP",
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
                        self.time_rules.after_market_open("T", 30),
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

        self.debug(f"Top {self.top_n} (value): {top_tickers}")

    def on_data(self, data):
        pass
