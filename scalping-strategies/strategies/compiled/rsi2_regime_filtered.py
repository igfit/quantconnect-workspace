"""
RSI(2) Pullback with Regime Filter

Only trades when SPY > 200 SMA (bull market).
Avoids mean reversion in bear markets where oversold keeps getting more oversold.

Entry:
  - SPY > 200 SMA (bull market regime)
  - RSI(2) < 20 (oversold)

Exit:
  - RSI(2) > 60 (mean reverted)
  - OR 5 days elapsed
  - OR -5% stop loss
"""

from AlgorithmImports import *


class RSI2RegimeFiltered(QCAlgorithm):
    """RSI(2) Pullback with Bull Market Regime Filter"""

    def initialize(self):
        # Full test period (2018-2024)
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Strategy parameters
        self.rsi_period = 2
        self.rsi_oversold = 20
        self.rsi_exit = 60

        # Risk management
        self.position_size_dollars = 20000
        self.stop_loss_pct = 0.05
        self.max_holding_days = 5
        self.max_positions = 5

        # Regime filter
        self.regime_sma_period = 200

        # Track positions
        self.entry_prices = {}
        self.entry_times = {}
        self.positions_count = 0

        # Universe
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

        # SPY for regime filter
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

        # REGIME FILTER: Only trade in bull markets
        if not self._is_bull_market(data):
            # In bear market - close any positions but don't open new ones
            for symbol in self.symbols:
                if self.portfolio[symbol].invested:
                    self._exit_position(symbol, "Bear market regime exit")
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
                if rsi_value < self.rsi_oversold:
                    self._enter_position(symbol, price, rsi_value)

    def _is_bull_market(self, data) -> bool:
        """Check if SPY > 200 SMA (bull market)"""
        if not self.spy_sma.is_ready:
            return False
        if self.spy not in data or data[self.spy] is None:
            return False

        spy_price = data[self.spy].close
        spy_sma_value = self.spy_sma.current.value

        return spy_price > spy_sma_value

    def _check_exit(self, symbol, data, rsi: float) -> tuple:
        price = data[symbol].close

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
        self.log(f"RSI(2) Regime-Filtered (SPY > 200 SMA)")
        self.log(f"Final Value: ${self.portfolio.total_portfolio_value:,.2f}")
        ret = (self.portfolio.total_portfolio_value / 100000 - 1) * 100
        self.log(f"Return: {ret:.1f}%")
