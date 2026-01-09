"""
RSI + ATR Filtered Strategy

Uses ATR to filter entries - only enter when volatility is elevated.
Theory: Oversold + high volatility = capitulation, better bounce opportunity.

Entry:
  - SPY > 200 SMA (bull market)
  - RSI(5) < 30 (oversold)
  - ATR(14) > ATR SMA(20) (elevated volatility)

Exit:
  - RSI(5) > 55
  - OR trailing stop at 2x ATR
  - OR 7 days max hold
"""

from AlgorithmImports import *


class RSIATRFiltered(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # RSI Parameters
        self.rsi_period = 5
        self.rsi_entry = 30
        self.rsi_exit = 55

        # ATR Parameters
        self.atr_period = 14
        self.atr_sma_period = 20
        self.atr_multiplier_stop = 2.0

        # Risk management
        self.position_size_dollars = 20000
        self.max_holding_days = 7
        self.max_positions = 5

        self.entry_prices = {}
        self.entry_times = {}
        self.entry_atr = {}
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
                "atr": self.atr(symbol, self.atr_period, MovingAverageType.SIMPLE, Resolution.DAILY),
                "atr_sma": None,  # Will track ATR SMA manually
            }

            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        # ATR history for SMA calculation
        self.atr_history = {s: [] for s in self.symbols}

        # Regime filter
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        self.set_warm_up(220, Resolution.DAILY)
        self.set_benchmark("SPY")

        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close("SPY", 5),
            self.check_time_stops
        )

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Update ATR history
        for symbol in self.symbols:
            atr = self.indicators[symbol]["atr"]
            if atr.is_ready:
                self.atr_history[symbol].append(atr.current.value)
                if len(self.atr_history[symbol]) > self.atr_sma_period + 5:
                    self.atr_history[symbol] = self.atr_history[symbol][-self.atr_sma_period-5:]

        # Regime filter
        if not self._is_bull_market(data):
            for symbol in self.symbols:
                if self.portfolio[symbol].invested:
                    self._exit_position(symbol, "Bear market")
            return

        for symbol in self.symbols:
            if symbol not in data or data[symbol] is None:
                continue

            rsi = self.indicators[symbol]["rsi"]
            atr = self.indicators[symbol]["atr"]

            if not rsi.is_ready or not atr.is_ready:
                continue
            if len(self.atr_history[symbol]) < self.atr_sma_period:
                continue

            rsi_value = rsi.current.value
            atr_value = atr.current.value
            atr_sma = sum(self.atr_history[symbol][-self.atr_sma_period:]) / self.atr_sma_period
            price = data[symbol].close

            if self.portfolio[symbol].invested:
                should_exit, reason = self._check_exit(symbol, price, rsi_value, atr_value)
                if should_exit:
                    self._exit_position(symbol, reason)
            elif self.positions_count < self.max_positions:
                # Entry: RSI oversold AND elevated volatility
                if rsi_value < self.rsi_entry and atr_value > atr_sma:
                    self._enter_position(symbol, price, rsi_value, atr_value)

    def _is_bull_market(self, data) -> bool:
        if not self.spy_sma.is_ready:
            return False
        if self.spy not in data or data[self.spy] is None:
            return False
        return data[self.spy].close > self.spy_sma.current.value

    def _check_exit(self, symbol, price: float, rsi: float, atr: float) -> tuple:
        # RSI exit
        if rsi > self.rsi_exit:
            return True, f"RSI exit ({rsi:.1f})"

        # Trailing stop based on entry ATR
        if symbol in self.entry_prices and symbol in self.entry_atr:
            entry = self.entry_prices[symbol]
            entry_atr = self.entry_atr[symbol]
            stop_price = entry - (self.atr_multiplier_stop * entry_atr)

            if price < stop_price:
                return True, f"ATR trailing stop"

        return False, ""

    def _enter_position(self, symbol, price: float, rsi: float, atr: float):
        shares = int(self.position_size_dollars / price)

        if shares > 0:
            self.market_order(symbol, shares)
            self.entry_prices[symbol] = price
            self.entry_times[symbol] = self.time
            self.entry_atr[symbol] = atr
            self.positions_count += 1
            self.debug(f"{self.time.date()}: ENTRY {symbol} @ ${price:.2f}, RSI={rsi:.1f}, ATR=${atr:.2f}")

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
            if symbol in self.entry_atr:
                del self.entry_atr[symbol]
            self.positions_count = max(0, self.positions_count - 1)

    def check_time_stops(self):
        for symbol in list(self.entry_times.keys()):
            if symbol in self.entry_times:
                days_held = (self.time - self.entry_times[symbol]).days
                if days_held >= self.max_holding_days:
                    self._exit_position(symbol, f"Time stop ({days_held} days)")

    def on_end_of_algorithm(self):
        self.log(f"RSI+ATR Filtered Strategy")
        self.log(f"Final: ${self.portfolio.total_portfolio_value:,.2f}")
        ret = (self.portfolio.total_portfolio_value / 100000 - 1) * 100
        self.log(f"Return: {ret:.1f}%")
