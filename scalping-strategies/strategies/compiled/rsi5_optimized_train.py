"""
RSI(5) Optimized Strategy - TRAINING PERIOD (2018-2020)

Best configuration from parameter study:
- RSI Period: 5 (sweet spot between sensitivity and stability)
- Entry: < 35 (catches moderate oversold, not just extremes)
- Exit: > 55 (quick exit, captures mean reversion)
- Regime: SPY > 200 SMA (avoids bear markets)
- Stop: 5% (accounts for high-beta volatility)
- Time stop: 5 days (forces decision)
"""

from AlgorithmImports import *


class RSI5OptimizedTrain(QCAlgorithm):

    def initialize(self):
        # TRAINING PERIOD ONLY
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2020, 12, 31)
        self.set_cash(100000)

        # OPTIMIZED Parameters from study
        self.rsi_period = 5
        self.rsi_entry = 35
        self.rsi_exit = 55

        # Risk management
        self.position_size_dollars = 20000
        self.stop_loss_pct = 0.05
        self.max_holding_days = 5
        self.max_positions = 5

        self.entry_prices = {}
        self.entry_times = {}
        self.positions_count = 0

        # High-beta universe (best performers in study)
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

        # Regime filter
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

        # Regime filter - exit all if bear market
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
        # RSI exit
        if rsi > self.rsi_exit:
            return True, f"RSI exit ({rsi:.1f})"

        # Stop loss
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
            self.debug(f"{self.time.date()}: ENTRY {symbol} @ ${price:.2f}, RSI={rsi:.1f}")

    def _exit_position(self, symbol, reason: str):
        if self.portfolio[symbol].invested:
            entry = self.entry_prices.get(symbol, 0)
            current = self.securities[symbol].price
            pnl_pct = (current - entry) / entry if entry > 0 else 0

            self.liquidate(symbol)
            self.debug(f"{self.time.date()}: EXIT {symbol} - {reason}, P&L: {pnl_pct:.1%}")

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
                    self._exit_position(symbol, f"Time stop ({days_held} days)")

    def on_end_of_algorithm(self):
        self.log(f"RSI(5) Optimized - TRAINING PERIOD (2018-2020)")
        self.log(f"Final Value: ${self.portfolio.total_portfolio_value:,.2f}")
        ret = (self.portfolio.total_portfolio_value / 100000 - 1) * 100
        self.log(f"Return: {ret:.1f}%")
