"""
Dual Momentum VolSize Expanded - TRAINING (2018-2020)
Walk-forward validation
"""

from AlgorithmImports import *


class DualMomentumVolSizeExpandedTrain(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2020, 12, 31)
        self.set_cash(100000)

        self.lookback = 63
        self.rsi_period = 14
        self.rsi_threshold = 50
        self.trailing_stop_pct = 0.10
        self.atr_period = 14
        self.base_risk_per_trade = 1500
        self.max_positions = 6

        self.entry_prices = {}
        self.highest_prices = {}
        self.positions_count = 0

        self.tickers = ["TSLA", "NVDA", "AMD", "META", "GOOGL", "AMZN"]
        self.symbols = []
        self.indicators = {}
        self.price_history = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)
            self.indicators[symbol] = {
                "rsi": self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY),
                "atr": self.atr(symbol, self.atr_period, MovingAverageType.WILDERS, Resolution.DAILY),
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

    def calculate_position_size(self, symbol, price, atr_value):
        if atr_value <= 0:
            return 0
        risk_per_share = 2 * atr_value
        shares = int(self.base_risk_per_trade / risk_per_share)
        max_value = self.portfolio.total_portfolio_value * 0.15
        max_shares = int(max_value / price)
        return min(shares, max_shares)

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

            ind = self.indicators[symbol]
            if not ind["rsi"].is_ready or not ind["atr"].is_ready:
                continue

            price = data[symbol].close
            rsi_value = ind["rsi"].current.value
            atr_value = ind["atr"].current.value
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
                    shares = self.calculate_position_size(symbol, price, atr_value)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.highest_prices[symbol] = price
                        self.positions_count += 1

    def on_end_of_algorithm(self):
        self.log(f"VolSize Expanded TRAIN: ${self.portfolio.total_portfolio_value:,.2f}")
