"""
RSI Parameter Study

Systematic test of RSI parameters on high-beta stocks with regime filter.
This version tests: RSI(3) with entry<25, exit>55

Parameters being studied:
- RSI Period: 2, 3, 5, 7, 14
- Entry threshold: 10, 15, 20, 25, 30
- Exit threshold: 50, 55, 60, 65, 70

Current test: RSI(3), Entry<25, Exit>55
"""

from AlgorithmImports import *


class RSIParamStudy(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # ===========================================
        # PARAMETERS TO VARY
        # ===========================================
        self.rsi_period = 3           # Test: 2, 3, 5, 7, 14
        self.rsi_entry = 25           # Test: 10, 15, 20, 25, 30
        self.rsi_exit = 55            # Test: 50, 55, 60, 65, 70
        # ===========================================

        self.position_size_dollars = 20000
        self.stop_loss_pct = 0.05
        self.max_holding_days = 5
        self.max_positions = 5
        self.regime_sma_period = 200

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
        self.spy_sma = self.sma(self.spy, self.regime_sma_period, Resolution.DAILY)

        self.set_warm_up(self.regime_sma_period + 10, Resolution.DAILY)
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
                    self._exit_position(symbol, "Bear market")
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
                should_exit, reason = self._check_exit(symbol, data, rsi_value)
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

    def _check_exit(self, symbol, data, rsi: float) -> tuple:
        price = data[symbol].close
        if rsi > self.rsi_exit:
            return True, f"RSI exit ({rsi:.1f})"
        if symbol in self.entry_prices:
            entry = self.entry_prices[symbol]
            if (price - entry) / entry < -self.stop_loss_pct:
                return True, "Stop loss"
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
            if symbol in self.entry_times:
                days_held = (self.time - self.entry_times[symbol]).days
                if days_held >= self.max_holding_days:
                    self._exit_position(symbol, "Time stop")

    def on_end_of_algorithm(self):
        self.log(f"RSI({self.rsi_period}) Entry<{self.rsi_entry} Exit>{self.rsi_exit}")
        self.log(f"Final: ${self.portfolio.total_portfolio_value:,.2f}")
