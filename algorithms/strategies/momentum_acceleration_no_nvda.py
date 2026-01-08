from AlgorithmImports import *

class MomentumAccelerationNoNVDA(QCAlgorithm):
    """
    Momentum Acceleration - WITHOUT NVDA (robustness test)

    Original achieved 44.12% CAGR, 1.111 Sharpe WITH NVDA.
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

        self.momentum_ind = {}
        for ticker, symbol in self.symbols.items():
            self.momentum_ind[ticker] = self.momp(symbol, 63, Resolution.DAILY)

        self.momentum_history = {}
        for ticker in self.tickers:
            self.momentum_history[ticker] = RollingWindow[float](25)

        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        self.top_n = 5
        self.set_benchmark("SPY")
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol

        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.after_market_open(self.spy, 5),
            self.update_momentum_history
        )

        self.schedule.on(
            self.date_rules.month_start(1),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )
        self.set_warm_up(100, Resolution.DAILY)

    def update_momentum_history(self):
        if self.is_warming_up:
            return
        for ticker in self.tickers:
            if self.momentum_ind[ticker].is_ready:
                self.momentum_history[ticker].add(self.momentum_ind[ticker].current.value)

    def rebalance(self):
        if self.is_warming_up:
            return

        candidates = []
        for ticker, symbol in self.symbols.items():
            if not self.momentum_ind[ticker].is_ready or not self.sma50_ind[ticker].is_ready:
                continue
            if not self.momentum_history[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma50 = self.sma50_ind[ticker].current.value
            current_mom = self.momentum_ind[ticker].current.value
            past_mom = self.momentum_history[ticker][20] if self.momentum_history[ticker].count > 20 else current_mom
            acceleration = current_mom - past_mom

            if current_mom > 0 and acceleration > 0 and price > sma50:
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'momentum': current_mom,
                    'acceleration': acceleration
                })

        if len(candidates) == 0:
            return

        sorted_candidates = sorted(candidates, key=lambda x: x['acceleration'], reverse=True)
        top_stocks = sorted_candidates[:min(self.top_n, len(sorted_candidates))]

        top_tickers = [s['ticker'] for s in top_stocks]
        for ticker, symbol in self.symbols.items():
            if ticker not in top_tickers and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        weight = 0.95 / len(top_stocks)
        for stock in top_stocks:
            self.set_holdings(stock['symbol'], weight)

    def on_data(self, data):
        pass
