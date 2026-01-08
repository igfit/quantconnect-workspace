from AlgorithmImports import *

class MomentumFactorETFs(QCAlgorithm):
    """
    Momentum Ranking on Factor ETFs

    Testing if momentum works on style/factor ETFs:
    - Value, Growth, Size, Quality, Momentum, Low Vol, Dividend

    No sector bias - pure factor rotation
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Factor ETFs (iShares and others)
        self.factors = [
            "IWD",   # Value (Russell 1000 Value)
            "IWF",   # Growth (Russell 1000 Growth)
            "IWM",   # Small Cap (Russell 2000)
            "QUAL",  # Quality
            "MTUM",  # Momentum
            "USMV",  # Low Volatility
            "DVY",   # Dividend
            "VTV",   # Value (Vanguard)
            "VUG",   # Growth (Vanguard)
            "VLUE",  # Value Factor
        ]

        self.top_n = 3
        self.lookback = 63

        self.symbols = {}
        self.roc_ind = {}

        for ticker in self.factors:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.roc_ind[ticker] = self.rocp(symbol, self.lookback, Resolution.DAILY)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(self.lookback + 10, Resolution.DAILY)

        self.schedule.on(self.date_rules.month_start(),
                        self.time_rules.after_market_open("IWF", 30),
                        self.rebalance)

    def rebalance(self):
        if self.is_warming_up:
            return

        momentum_scores = {}
        for ticker in self.factors:
            if self.roc_ind[ticker].is_ready:
                momentum_scores[ticker] = self.roc_ind[ticker].current.value

        if len(momentum_scores) < self.top_n:
            return

        ranked = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        top_factors = [t[0] for t in ranked[:self.top_n]]

        for ticker in self.factors:
            if ticker not in top_factors:
                symbol = self.symbols[ticker]
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol)

        weight = 1.0 / self.top_n
        for ticker in top_factors:
            self.set_holdings(self.symbols[ticker], weight)

        self.debug(f"Top factors: {top_factors}")

    def on_data(self, data):
        pass
