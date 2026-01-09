"""
RSI(5) Optimized Strategy - VALIDATION PERIOD (2023-2024)

Final validation - NO PARAMETER CHANGES from training.
This confirms if the strategy is robust on completely unseen data.
"""

from AlgorithmImports import *


class RSI5OptimizedValidate(QCAlgorithm):

    def initialize(self):
        # VALIDATION PERIOD - Final confirmation
        self.set_start_date(2023, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # SAME parameters as training - no changes allowed
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

        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close("SPY", 5),
            self.check_time_stops
        )

    def on_data(self, data):
        if self.is_warming_up:
            return

        if not self._is_bull_market(data):
            for symbol in self.symbols:
                if self.portfolio[symbol].invested:
                    self._exit_position(symbol, "Regime exit")
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
                should_exit, reason = self._check_exit(symbol, price, rsi_value)
                if should_exit:
                    self._exit_position(symbol, reason)
            elif self.positions_count < self.max_positions:
                if rsi_value < self.rsi_entry:
                    self._enter_position(symbol, price, rsi_value)

    def _is_bull_market(self, data) -> bool:
        if not self.spy_sma.is_ready:
            return False
        if self.spy not in data or data[self.spy] is None:
            return False
        return data[self.spy].close > self.spy_sma.current.value

    def _check_exit(self, symbol, price: float, rsi: float) -> tuple:
        if rsi > self.rsi_exit:
            return True, f"RSI exit ({rsi:.1f})"
        if symbol in self.entry_prices:
            entry = self.entry_prices[symbol]
            pnl_pct = (price - entry) / entry
            if pnl_pct < -self.stop_loss_pct:
                return True, f"Stop loss ({pnl_pct:.1%})"
        return False, ""

    def _enter_position(self, symbol, price: float, rsi: float):
        shares = int(self.position_size_dollars / price)
        if shares > 0:
            self.market_order(symbol, shares)
            self.entry_prices[symbol] = price
            self.entry_times[symbol] = self.time
            self.positions_count += 1

    def _exit_position(self, symbol, reason: str):
        if self.portfolio[symbol].invested:
            self.liquidate(symbol)
            if symbol in self.entry_prices:
                del self.entry_prices[symbol]
            if symbol in self.entry_times:
                del self.entry_times[symbol]
            self.positions_count = max(0, self.positions_count - 1)

    def check_time_stops(self):
        for symbol in list(self.entry_times.keys()):
            if (self.time - self.entry_times[symbol]).days >= self.max_holding_days:
                self._exit_position(symbol, f"Time stop")

    def on_end_of_algorithm(self):
        self.log(f"RSI(5) Optimized - VALIDATION PERIOD (2023-2024)")
        self.log(f"Final Value: ${self.portfolio.total_portfolio_value:,.2f}")
        ret = (self.portfolio.total_portfolio_value / 100000 - 1) * 100
        self.log(f"Return: {ret:.1f}%")
