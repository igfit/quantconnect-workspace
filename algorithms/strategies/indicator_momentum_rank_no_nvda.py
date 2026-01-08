from AlgorithmImports import *

class IndicatorMomentumRankNoNVDA(QCAlgorithm):
    """
    Momentum Ranking Strategy (Top 5 Concentrated) - NO NVDA

    Robustness test: Same as momentum_rank but excluding NVDA
    to verify signal edge vs stock alpha.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # 24-stock basket - NO NVDA
        self.basket = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",  # No NVDA
            "AVGO", "AMD", "NFLX", "CRM", "NOW", "ADBE", "ORCL",
            "V", "MA", "JPM", "GS",
            "LLY", "UNH", "ABBV",
            "COST", "HD", "CAT", "GE", "HON"
        ]

        self.top_n = 5
        self.lookback = 63  # ~3 months

        self.symbols = {}
        self.roc_ind = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.roc_ind[ticker] = self.rocp(symbol, self.lookback, Resolution.DAILY)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(self.lookback + 10, Resolution.DAILY)

        # Monthly rebalance
        self.schedule.on(self.date_rules.month_start(),
                        self.time_rules.after_market_open("AAPL", 30),
                        self.rebalance)

    def rebalance(self):
        if self.is_warming_up:
            return

        # Get momentum scores
        momentum_scores = {}
        for ticker in self.basket:
            if self.roc_ind[ticker].is_ready:
                momentum_scores[ticker] = self.roc_ind[ticker].current.value

        if len(momentum_scores) < self.top_n:
            return

        # Rank by momentum (highest first)
        ranked = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        top_tickers = [t[0] for t in ranked[:self.top_n]]

        # Liquidate stocks not in top N
        for ticker in self.basket:
            if ticker not in top_tickers:
                symbol = self.symbols[ticker]
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol)

        # Equal weight top N
        weight = 1.0 / self.top_n
        for ticker in top_tickers:
            symbol = self.symbols[ticker]
            self.set_holdings(symbol, weight)

        self.debug(f"Top {self.top_n} (no NVDA): {top_tickers}")

    def on_data(self, data):
        pass  # All logic in scheduled rebalance
