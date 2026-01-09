"""
RSI(2) Pullback V2 - Optimized for High-Beta Stocks

Improved version with looser parameters for volatile stocks like TSLA, NVDA, AMD.

Changes from V1:
- RSI threshold: 20 (was 10) - more trade opportunities
- Stop loss: 5% (was 3%) - accounts for high-beta volatility
- Exit threshold: 60 (was 70) - faster exits
- No SMA filter - high-beta stocks trend strongly, filter hurts

Entry:
  - RSI(2) < 20 (oversold)

Exit:
  - RSI(2) > 60 (mean reverted)
  - OR 5 days elapsed (time stop)
  - OR -5% from entry (hard stop)
"""

from AlgorithmImports import *


class RSI2PullbackV2(QCAlgorithm):
    """
    RSI(2) Pullback V2 - Optimized for High-Beta Stocks
    """

    def initialize(self):
        # Backtest period - Training (2018-2020)
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2020, 12, 31)
        self.set_cash(100000)

        # ADJUSTED Strategy parameters for high-beta stocks
        self.rsi_period = 2
        self.rsi_oversold = 20      # Looser entry (was 10)
        self.rsi_exit = 60          # Faster exit (was 70)

        # ADJUSTED Risk management for volatility
        self.position_size_dollars = 20000
        self.stop_loss_pct = 0.05   # 5% stop (was 3%)
        self.max_holding_days = 5
        self.max_positions = 5

        # Track positions
        self.entry_prices = {}
        self.entry_times = {}
        self.positions_count = 0

        # Universe - high-beta stocks
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

        self.set_warm_up(20, Resolution.DAILY)
        self.add_equity("SPY", Resolution.DAILY)
        self.set_benchmark("SPY")

        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close("SPY", 5),
            self.check_time_stops
        )

    def on_data(self, data):
        if self.is_warming_up:
            return

        for symbol in self.symbols:
            if symbol not in data or data[symbol] is None:
                continue

            rsi = self.indicators[symbol]["rsi"]
            if not rsi.is_ready:
                continue

            rsi_value = rsi.current.value
            price = data[symbol].close

            # Check exit first
            if self.portfolio[symbol].invested:
                should_exit, reason = self._check_exit(symbol, data, rsi_value)
                if should_exit:
                    self._exit_position(symbol, reason)

            # Check entry
            elif self.positions_count < self.max_positions:
                if rsi_value < self.rsi_oversold:
                    self._enter_position(symbol, price, rsi_value)

    def _check_exit(self, symbol, data, rsi: float) -> tuple:
        price = data[symbol].close

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
        self.log(f"RSI(2) Pullback V2 (High-Beta Optimized)")
        self.log(f"Final Value: ${self.portfolio.total_portfolio_value:,.2f}")
        self.log(f"Return: {(self.portfolio.total_portfolio_value / 100000 - 1) * 100:.1f}%")
