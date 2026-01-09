"""
Bollinger Band Mean Reversion Strategy

Buy at lower Bollinger Band with RSI confirmation, exit at middle band.

Rationale:
Bollinger Bands capture 95% of price action within 2 standard deviations.
When price touches the lower band AND RSI confirms oversold, we have
a high-probability mean reversion setup. Exit at middle band captures
the reversion without waiting for overbought conditions.

Entry:
  - Price > 200 SMA (uptrend)
  - Price <= Lower Bollinger Band
  - RSI(14) < 35 (confirming oversold)

Exit:
  - Price >= Middle Bollinger Band
  - OR 7 days elapsed (time stop)
  - OR -3% from entry (hard stop)
"""

from AlgorithmImports import *


class BollingerMeanReversion(QCAlgorithm):
    """
    Bollinger Band Mean Reversion Strategy

    Buys at lower band, exits at middle band for consistent small wins.
    """

    def initialize(self):
        # Backtest period - Training
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2020, 12, 31)
        self.set_cash(100000)

        # Bollinger Band parameters
        self.bb_period = 20
        self.bb_std = 2.0
        self.rsi_period = 14
        self.rsi_threshold = 35
        self.sma_period = 200

        # Risk management
        self.position_size_dollars = 20000
        self.stop_loss_pct = 0.03
        self.max_holding_days = 7
        self.max_positions = 5

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
                "bb": self.bb(symbol, self.bb_period, self.bb_std, MovingAverageType.SIMPLE, Resolution.DAILY),
                "rsi": self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY),
                "sma": self.sma(symbol, self.sma_period, Resolution.DAILY),
            }

            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        # Warmup
        self.set_warm_up(self.sma_period + 10, Resolution.DAILY)

        # Benchmark
        self.add_equity("SPY", Resolution.DAILY)
        self.set_benchmark("SPY")

        # Schedule time stops
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

            # Get indicators
            bb = self.indicators[symbol]["bb"]
            rsi = self.indicators[symbol]["rsi"]
            sma = self.indicators[symbol]["sma"]

            if not bb.is_ready or not rsi.is_ready or not sma.is_ready:
                continue

            price = data[symbol].close
            lower_band = bb.lower_band.current.value
            middle_band = bb.middle_band.current.value
            rsi_value = rsi.current.value
            sma_value = sma.current.value

            # Check exit first
            if self.portfolio[symbol].invested:
                should_exit, reason = self._check_exit(symbol, price, middle_band)
                if should_exit:
                    self._exit_position(symbol, reason)

            # Check entry
            elif self.positions_count < self.max_positions:
                if self._check_entry(symbol, price, lower_band, rsi_value, sma_value):
                    self._enter_position(symbol, price)

    def _check_entry(
        self,
        symbol,
        price: float,
        lower_band: float,
        rsi: float,
        sma: float
    ) -> bool:
        """
        Check entry conditions:
        1. Price > 200 SMA (uptrend)
        2. Price <= Lower BB
        3. RSI < 35 (confirming oversold)
        """
        # Uptrend filter
        if price <= sma:
            return False

        # Price at or below lower band
        if price > lower_band:
            return False

        # RSI confirmation
        if rsi >= self.rsi_threshold:
            return False

        self.debug(f"{self.time.date()}: {symbol} ENTRY SIGNAL - Price={price:.2f} <= LowerBB={lower_band:.2f}, RSI={rsi:.1f}")
        return True

    def _check_exit(self, symbol, price: float, middle_band: float) -> tuple:
        """
        Check exit conditions:
        1. Price >= Middle BB (mean reverted)
        2. Stop loss hit
        """
        # Mean reversion target
        if price >= middle_band:
            return True, f"Middle BB exit (${price:.2f} >= ${middle_band:.2f})"

        # Stop loss
        if symbol in self.entry_prices:
            entry = self.entry_prices[symbol]
            pnl_pct = (price - entry) / entry

            if pnl_pct < -self.stop_loss_pct:
                return True, f"Stop loss ({pnl_pct:.1%})"

        return False, ""

    def _enter_position(self, symbol, price: float):
        """Enter position"""
        shares = int(self.position_size_dollars / price)

        if shares > 0:
            self.market_order(symbol, shares)
            self.entry_prices[symbol] = price
            self.entry_times[symbol] = self.time
            self.positions_count += 1

            self.debug(f"{self.time.date()}: ENTRY {symbol} @ ${price:.2f}")

    def _exit_position(self, symbol, reason: str):
        """Exit position"""
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
        """Check time-based exits"""
        for symbol in list(self.entry_times.keys()):
            if symbol in self.entry_times:
                days_held = (self.time - self.entry_times[symbol]).days
                if days_held >= self.max_holding_days:
                    self._exit_position(symbol, f"Time stop ({days_held} days)")

    def on_end_of_algorithm(self):
        """Log results"""
        self.log(f"Bollinger Mean Reversion Strategy")
        self.log(f"Final Value: ${self.portfolio.total_portfolio_value:,.2f}")
