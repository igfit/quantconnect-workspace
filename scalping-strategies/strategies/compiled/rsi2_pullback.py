"""
RSI(2) Pullback Strategy

Buy extreme oversold (RSI(2) < 10) in uptrending stocks.

Rationale:
Extreme short-term oversold conditions in trending stocks create bounce
opportunities. RSI(2) < 10 indicates capitulation selling that typically
reverses within 1-5 days. The 200 SMA filter ensures we only buy pullbacks
in uptrends, not falling knives in downtrends.

Strategy Type: mean_reversion
Resolution: Daily
Academic basis: Larry Connors - "Short-Term Trading Strategies That Work"

Entry:
  - Price > 200 SMA (uptrend filter)
  - RSI(2) < 10 (extreme oversold)

Exit:
  - RSI(2) > 70 (mean reverted)
  - OR 5 days elapsed (time stop)
  - OR -3% from entry (hard stop)
"""

from AlgorithmImports import *


class RSI2Pullback(QCAlgorithm):
    """
    RSI(2) Pullback Mean Reversion Strategy

    Buys extreme short-term oversold conditions in trending stocks.
    High win rate (~70-80%), small gains per trade.
    """

    def initialize(self):
        # Backtest period - Training (2018-2020)
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2020, 12, 31)
        self.set_cash(100000)

        # Strategy parameters
        self.rsi_period = 2
        self.rsi_oversold = 10      # Entry threshold
        self.rsi_exit = 70          # Exit threshold
        self.sma_period = 200       # Trend filter

        # Risk management
        self.position_size_dollars = 20000
        self.stop_loss_pct = 0.03   # 3% hard stop
        self.max_holding_days = 5   # Time stop
        self.max_positions = 5

        # Track positions
        self.entry_prices = {}
        self.entry_times = {}
        self.positions_count = 0

        # Universe - high-beta stocks
        self.tickers = ["TSLA", "NVDA", "AMD"]
        self.symbols = []
        self.indicators = {}

        # Setup universe and indicators
        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)

            # Setup indicators
            self.indicators[symbol] = {
                "rsi": self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY),
                "sma": self.sma(symbol, self.sma_period, Resolution.DAILY),
            }

            # Set slippage and fees
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        # Warmup
        self.set_warm_up(self.sma_period + 10, Resolution.DAILY)

        # Benchmark
        self.add_equity("SPY", Resolution.DAILY)
        self.set_benchmark("SPY")

        # Schedule end-of-day check for time stops
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close("SPY", 5),
            self.check_time_stops
        )

    def on_data(self, data):
        """Main trading logic"""
        if self.is_warming_up:
            return

        for symbol in self.symbols:
            if symbol not in data or data[symbol] is None:
                continue

            # Get indicator values
            rsi = self.indicators[symbol]["rsi"]
            sma = self.indicators[symbol]["sma"]

            if not rsi.is_ready or not sma.is_ready:
                continue

            rsi_value = rsi.current.value
            sma_value = sma.current.value
            price = data[symbol].close

            # Check exit conditions first
            if self.portfolio[symbol].invested:
                should_exit, reason = self._check_exit(symbol, data, rsi_value)
                if should_exit:
                    self._exit_position(symbol, reason)

            # Check entry conditions
            elif self.positions_count < self.max_positions:
                if self._check_entry(symbol, price, rsi_value, sma_value):
                    self._enter_position(symbol, price)

    def _check_entry(self, symbol, price: float, rsi: float, sma: float) -> bool:
        """
        Check entry conditions:
        1. Price > 200 SMA (uptrend)
        2. RSI(2) < 10 (extreme oversold)
        """
        # Uptrend filter
        if price <= sma:
            return False

        # Extreme oversold
        if rsi >= self.rsi_oversold:
            return False

        self.debug(f"{self.time.date()}: {symbol} ENTRY SIGNAL - RSI(2)={rsi:.1f}, Price={price:.2f} > SMA={sma:.2f}")
        return True

    def _check_exit(self, symbol, data, rsi: float) -> tuple:
        """
        Check exit conditions:
        1. RSI(2) > 70 (mean reverted)
        2. Stop loss hit (-3%)
        3. Time stop (5 days)
        """
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

    def _enter_position(self, symbol, price: float):
        """Enter a new position"""
        shares = int(self.position_size_dollars / price)

        if shares > 0:
            self.market_order(symbol, shares)
            self.entry_prices[symbol] = price
            self.entry_times[symbol] = self.time
            self.positions_count += 1

            self.debug(f"{self.time.date()}: ENTRY {symbol} @ ${price:.2f}, {shares} shares")

    def _exit_position(self, symbol, reason: str):
        """Exit position"""
        if self.portfolio[symbol].invested:
            entry = self.entry_prices.get(symbol, 0)
            current = self.securities[symbol].price
            pnl_pct = (current - entry) / entry if entry > 0 else 0

            self.liquidate(symbol)

            self.debug(f"{self.time.date()}: EXIT {symbol} - {reason}, P&L: {pnl_pct:.1%}")

            # Cleanup
            if symbol in self.entry_prices:
                del self.entry_prices[symbol]
            if symbol in self.entry_times:
                del self.entry_times[symbol]
            self.positions_count = max(0, self.positions_count - 1)

    def check_time_stops(self):
        """Check for time-based exits"""
        for symbol in list(self.entry_times.keys()):
            if symbol in self.entry_times:
                days_held = (self.time - self.entry_times[symbol]).days
                if days_held >= self.max_holding_days:
                    self._exit_position(symbol, f"Time stop ({days_held} days)")

    def on_end_of_algorithm(self):
        """Log final results"""
        self.log(f"RSI(2) Pullback Strategy")
        self.log(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
        self.log(f"Return: {(self.portfolio.total_portfolio_value / 100000 - 1) * 100:.1f}%")
