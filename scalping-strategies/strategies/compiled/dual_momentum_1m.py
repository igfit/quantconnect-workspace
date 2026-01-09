"""
Dual Momentum Strategy - 1-Month Lookback Variant

Testing shorter lookback period (21 trading days vs 63)
Hypothesis: Shorter lookback may capture faster momentum shifts
Risk: More noise, more whipsaws
"""

from AlgorithmImports import *


class DualMomentum1M(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.lookback = 21  # 1 month instead of 3
        self.rsi_period = 14
        self.rsi_threshold = 50
        self.trailing_stop_pct = 0.10

        self.position_size_dollars = 20000
        self.max_positions = 5

        self.entry_prices = {}
        self.highest_prices = {}
        self.positions_count = 0

        self.tickers = ["TSLA", "NVDA", "AMD"]
        self.symbols = []
        self.indicators = {}
        self.price_history = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)
            self.indicators[symbol] = {
                "rsi": self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY),
            }
            self.price_history[symbol] = []
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_prices = []
        self.set_warm_up(250, Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_data(self, data):
        if self.is_warming_up:
            return

        if self.spy in data and data[self.spy] is not None:
            self.spy_prices.append(data[self.spy].close)
            if len(self.spy_prices) > self.lookback + 5:
                self.spy_prices = self.spy_prices[-self.lookback-5:]

        for symbol in self.symbols:
            if symbol in data and data[symbol] is not None:
                self.price_history[symbol].append(data[symbol].close)
                if len(self.price_history[symbol]) > self.lookback + 5:
                    self.price_history[symbol] = self.price_history[symbol][-self.lookback-5:]

        if self.spy not in data or data[self.spy] is None or not self.spy_sma.is_ready or data[self.spy].close <= self.spy_sma.current.value:
            for s in self.symbols:
                if self.portfolio[s].invested:
                    self.liquidate(s)
            self.positions_count = 0
            self.entry_prices.clear()
            self.highest_prices.clear()
            return

        spy_momentum = 0
        if len(self.spy_prices) >= self.lookback:
            spy_momentum = (self.spy_prices[-1] / self.spy_prices[-self.lookback]) - 1

        for symbol in self.symbols:
            if symbol not in data or data[symbol] is None:
                continue
            if len(self.price_history[symbol]) < self.lookback:
                continue

            rsi = self.indicators[symbol]["rsi"]
            if not rsi.is_ready:
                continue

            price = data[symbol].close
            rsi_value = rsi.current.value
            prices = self.price_history[symbol]
            stock_momentum = (prices[-1] / prices[-self.lookback]) - 1

            absolute_momentum = stock_momentum > 0
            relative_momentum = stock_momentum > spy_momentum

            if self.portfolio[symbol].invested:
                if symbol in self.highest_prices:
                    self.highest_prices[symbol] = max(self.highest_prices[symbol], price)
                trailing_stop_price = self.highest_prices.get(symbol, price) * (1 - self.trailing_stop_pct)

                if not absolute_momentum or price < trailing_stop_price:
                    self.liquidate(symbol)
                    if symbol in self.entry_prices: del self.entry_prices[symbol]
                    if symbol in self.highest_prices: del self.highest_prices[symbol]
                    self.positions_count = max(0, self.positions_count - 1)

            elif self.positions_count < self.max_positions:
                if absolute_momentum and relative_momentum and rsi_value > self.rsi_threshold:
                    shares = int(self.position_size_dollars / price)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.highest_prices[symbol] = price
                        self.positions_count += 1

    def on_end_of_algorithm(self):
        self.log(f"Dual Momentum 1M: ${self.portfolio.total_portfolio_value:,.2f}")
