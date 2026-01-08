from AlgorithmImports import *

class QualityMomentumNoNVDA(QCAlgorithm):
    """
    Quality Momentum - WITHOUT NVDA (robustness test)

    Original achieved 40.95% CAGR, 1.279 Sharpe WITH NVDA.
    Testing if strategy is robust without the dominant performer.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Quality mega-cap universe - EXCLUDING NVDA
        self.tickers = [
            "AAPL",   # Largest market cap, huge cash flows
            "MSFT",   # Cloud leader, consistent growth
            "GOOGL",  # Search monopoly, AI leader
            "AMZN",   # E-commerce + cloud dominance
            "META",   # Social media monopoly, recovered strongly
            "AVGO",   # Semiconductor giant, stable profits
            "ORCL",   # Enterprise software, consistent
            "CRM",    # CRM leader, growing
            "ADBE",   # Creative software monopoly
            "NFLX",   # Streaming leader (replacing NVDA)
        ]

        self.symbols = {}
        for ticker in self.tickers:
            self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        self.momentum_ind = {}
        for ticker, symbol in self.symbols.items():
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)

        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        self.top_n = 3
        self.set_benchmark("SPY")

        self.schedule.on(
            self.date_rules.month_start(1),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )
        self.set_warm_up(210, Resolution.DAILY)

    def rebalance(self):
        if self.is_warming_up:
            return

        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            self.liquidate()
            return

        candidates = []
        for ticker, symbol in self.symbols.items():
            if not self.momentum_ind[ticker].is_ready or not self.sma50_ind[ticker].is_ready:
                continue
            price = self.securities[symbol].price
            sma50 = self.sma50_ind[ticker].current.value
            momentum = self.momentum_ind[ticker].current.value
            if price > sma50:
                candidates.append({'ticker': ticker, 'symbol': symbol, 'momentum': momentum})

        if len(candidates) < self.top_n:
            return

        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        top_stocks = sorted_candidates[:self.top_n]

        top_tickers = [s['ticker'] for s in top_stocks]
        for ticker, symbol in self.symbols.items():
            if ticker not in top_tickers and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        weight = 0.95 / self.top_n
        for stock in top_stocks:
            self.set_holdings(stock['symbol'], weight)

    def on_data(self, data):
        pass
