"""RSI(5) E<35 X>55 - Training Period Only (2018-2020)"""
from AlgorithmImports import *

class RSI5E35X55Train(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2020, 12, 31)
        self.set_cash(100000)

        self.rsi_period = 5
        self.rsi_entry = 35
        self.rsi_exit = 55

        self.position_size_dollars = 20000
        self.stop_loss_pct = 0.05
        self.max_holding_days = 5
        self.max_positions = 5

        self.entry_prices = {}
        self.entry_times = {}
        self.positions_count = 0

        self.tickers = ["TSLA", "NVDA", "AMD"]
        self.symbols = []
        self.indicators = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)
            self.indicators[symbol] = {
                "rsi": self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY),
            }
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.set_warm_up(210, Resolution.DAILY)
        self.set_benchmark("SPY")

        self.schedule.on(self.date_rules.every_day(), self.time_rules.before_market_close("SPY", 5), self.check_time_stops)

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Regime filter - bear market, exit all
        if self.spy not in data or not self.spy_sma.is_ready or data[self.spy].close <= self.spy_sma.current.value:
            for s in self.symbols:
                if self.portfolio[s].invested:
                    self.liquidate(s)
            self.positions_count = 0
            self.entry_prices.clear()
            self.entry_times.clear()
            return

        for symbol in self.symbols:
            if symbol not in data or data[symbol] is None:
                continue
            rsi = self.indicators[symbol]["rsi"]
            if not rsi.is_ready:
                continue
            rsi_value = rsi.current.value
            price = data[symbol].close

            if self.portfolio[symbol].invested:
                if rsi_value > self.rsi_exit or (symbol in self.entry_prices and (price - self.entry_prices[symbol]) / self.entry_prices[symbol] < -self.stop_loss_pct):
                    self.liquidate(symbol)
                    if symbol in self.entry_prices: del self.entry_prices[symbol]
                    if symbol in self.entry_times: del self.entry_times[symbol]
                    self.positions_count = max(0, self.positions_count - 1)
            elif self.positions_count < self.max_positions and rsi_value < self.rsi_entry:
                shares = int(self.position_size_dollars / price)
                if shares > 0:
                    self.market_order(symbol, shares)
                    self.entry_prices[symbol] = price
                    self.entry_times[symbol] = self.time
                    self.positions_count += 1

    def check_time_stops(self):
        for symbol in list(self.entry_times.keys()):
            if (self.time - self.entry_times[symbol]).days >= self.max_holding_days:
                self.liquidate(symbol)
                if symbol in self.entry_prices: del self.entry_prices[symbol]
                if symbol in self.entry_times: del self.entry_times[symbol]
                self.positions_count = max(0, self.positions_count - 1)

    def on_end_of_algorithm(self):
        self.log(f"RSI(5) E<35 X>55 (2018-2020): ${self.portfolio.total_portfolio_value:,.2f}")
