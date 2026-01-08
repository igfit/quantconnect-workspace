from AlgorithmImports import *

class AdaptiveLookbackMomentumNoNVDA(QCAlgorithm):
    """
    Adaptive Lookback Momentum - WITHOUT NVDA (robustness test)

    Original achieved 51.34% CAGR, 1.23 Sharpe WITH NVDA.
    Testing if strategy is robust without the dominant performer.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe - mega-caps EXCLUDING NVDA
        self.tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "TSLA", "AMD", "AVGO", "CRM", "ORCL",
            "ADBE", "NFLX", "CSCO", "INTC", "QCOM",
            "TXN", "NOW", "UBER", "SHOP"
        ]

        self.symbols = {}
        for ticker in self.tickers:
            self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol

        self.vix = self.add_data(CBOE, "VIX", Resolution.DAILY).symbol

        self.momentum_short = {}
        self.momentum_long = {}
        for ticker, symbol in self.symbols.items():
            self.momentum_short[ticker] = self.momp(symbol, 63, Resolution.DAILY)
            self.momentum_long[ticker] = self.momp(symbol, 126, Resolution.DAILY)

        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        self.vix_threshold = 25
        self.top_n = 5
        self.set_benchmark("SPY")
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol

        self.schedule.on(
            self.date_rules.month_start(1),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )
        self.set_warm_up(140, Resolution.DAILY)

    def rebalance(self):
        if self.is_warming_up:
            return

        vix_value = self.securities[self.vix].price if self.securities[self.vix].price > 0 else 20
        use_short_lookback = vix_value > self.vix_threshold
        momentum_dict = self.momentum_short if use_short_lookback else self.momentum_long

        candidates = []
        for ticker, symbol in self.symbols.items():
            if not momentum_dict[ticker].is_ready or not self.sma50_ind[ticker].is_ready:
                continue
            price = self.securities[symbol].price
            sma50 = self.sma50_ind[ticker].current.value
            momentum = momentum_dict[ticker].current.value
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
