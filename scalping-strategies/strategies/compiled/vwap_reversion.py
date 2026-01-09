"""
VWAP Reversion Strategy (Intraday)

Buy below VWAP with RSI confirmation, exit at VWAP.

Rationale:
VWAP represents the average price weighted by volume - essentially where
institutional money traded. When price falls significantly below VWAP (1.5%+)
with oversold RSI, institutions often step in to buy, pushing price back to VWAP.

Entry:
  - Price < VWAP * 0.985 (1.5%+ below VWAP)
  - RSI(7) < 30 (oversold confirmation)

Exit:
  - Price >= VWAP (mean reverted)
  - OR end of day (flat overnight)
  - OR 2% stop loss

Resolution: MINUTE (intraday strategy)
"""

from AlgorithmImports import *


class VWAPReversionStrategy(QCAlgorithm):
    """
    VWAP Reversion Intraday Strategy

    Buys oversold conditions below VWAP, exits at VWAP.
    """

    def initialize(self):
        # Backtest period
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2020, 12, 31)
        self.set_cash(100000)

        # Strategy parameters
        self.vwap_deviation = 0.015     # 1.5% below VWAP to enter
        self.rsi_period = 7
        self.rsi_oversold = 30
        self.stop_loss_pct = 0.02       # 2% stop

        # Risk management
        self.position_size_dollars = 15000
        self.max_positions = 3

        # State
        self.entry_prices = {}
        self.positions_count = 0
        self.traded_today = {}          # Track entries per symbol per day

        # Universe
        self.tickers = ["TSLA", "NVDA", "AMD"]
        self.symbols = []
        self.indicators = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.MINUTE)
            symbol = equity.symbol
            self.symbols.append(symbol)

            # VWAP resets daily automatically in QC
            self.indicators[symbol] = {
                "vwap": self.vwap(symbol),
                "rsi": self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.MINUTE),
            }

            # Tight slippage for intraday
            equity.set_slippage_model(ConstantSlippageModel(0.0002))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        # Warmup for RSI
        self.set_warm_up(timedelta(minutes=30))

        # Benchmark
        self.add_equity("SPY", Resolution.MINUTE)
        self.set_benchmark("SPY")

        # Schedule: Close all at end of day
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close("SPY", 5),
            self.close_all_positions
        )

        # Schedule: Reset daily tracking
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open("SPY", 1),
            self.reset_daily_tracking
        )

    def reset_daily_tracking(self):
        """Reset daily tracking"""
        self.traded_today.clear()

    def on_data(self, data):
        """Main trading logic"""
        if self.is_warming_up:
            return

        # Don't trade in first 15 minutes (VWAP not stable)
        if self.time.hour == 9 and self.time.minute < 45:
            return

        # Don't enter new positions in last hour
        if self.time.hour >= 15:
            self._check_all_exits(data)
            return

        for symbol in self.symbols:
            if symbol not in data or data[symbol] is None:
                continue

            # Check if we have a position
            if self.portfolio[symbol].invested:
                self._check_exit(symbol, data)
            elif self.positions_count < self.max_positions:
                # Limit entries per symbol per day
                today_key = f"{symbol}_{self.time.date()}"
                if self.traded_today.get(today_key, 0) < 2:  # Max 2 entries per symbol per day
                    self._check_entry(symbol, data)

    def _check_entry(self, symbol, data):
        """Check entry conditions"""
        vwap = self.indicators[symbol]["vwap"]
        rsi = self.indicators[symbol]["rsi"]

        if not vwap.is_ready or not rsi.is_ready:
            return

        price = data[symbol].close
        vwap_value = vwap.current.value
        rsi_value = rsi.current.value

        # Skip if VWAP is invalid
        if vwap_value <= 0:
            return

        # Calculate deviation from VWAP
        deviation = (price - vwap_value) / vwap_value

        # Entry: Price significantly below VWAP AND oversold
        if deviation < -self.vwap_deviation and rsi_value < self.rsi_oversold:
            self._enter_position(symbol, price, vwap_value, deviation, rsi_value)

    def _enter_position(self, symbol, price: float, vwap: float, deviation: float, rsi: float):
        """Enter long position"""
        shares = int(self.position_size_dollars / price)

        if shares == 0:
            return

        self.market_order(symbol, shares)
        self.entry_prices[symbol] = price
        self.positions_count += 1

        # Track daily entries
        today_key = f"{symbol}_{self.time.date()}"
        self.traded_today[today_key] = self.traded_today.get(today_key, 0) + 1

        self.debug(f"{self.time}: VWAP ENTRY {symbol} @ ${price:.2f}, VWAP=${vwap:.2f}, Dev={deviation:.1%}, RSI={rsi:.1f}")

    def _check_all_exits(self, data):
        """Check exits for all positions"""
        for symbol in self.symbols:
            if self.portfolio[symbol].invested:
                self._check_exit(symbol, data)

    def _check_exit(self, symbol, data):
        """Check exit conditions"""
        if symbol not in data or data[symbol] is None:
            return

        vwap = self.indicators[symbol]["vwap"]
        if not vwap.is_ready:
            return

        price = data[symbol].close
        vwap_value = vwap.current.value
        entry = self.entry_prices.get(symbol)

        if entry is None:
            return

        # Exit at VWAP (mean reverted)
        if price >= vwap_value:
            self._exit_position(symbol, f"VWAP target (${price:.2f} >= ${vwap_value:.2f})")
            return

        # Stop loss
        pnl_pct = (price - entry) / entry
        if pnl_pct < -self.stop_loss_pct:
            self._exit_position(symbol, f"Stop loss ({pnl_pct:.1%})")
            return

    def _exit_position(self, symbol, reason: str):
        """Exit position"""
        if self.portfolio[symbol].invested:
            entry = self.entry_prices.get(symbol, 0)
            current = self.securities[symbol].price
            pnl_pct = (current - entry) / entry if entry > 0 else 0

            self.liquidate(symbol)

            self.debug(f"{self.time}: VWAP EXIT {symbol} - {reason}, P&L: {pnl_pct:.1%}")

            if symbol in self.entry_prices:
                del self.entry_prices[symbol]
            self.positions_count = max(0, self.positions_count - 1)

    def close_all_positions(self):
        """Close all positions at end of day"""
        for symbol in self.symbols:
            if self.portfolio[symbol].invested:
                self._exit_position(symbol, "End of day")

    def on_end_of_algorithm(self):
        """Log results"""
        self.log(f"VWAP Reversion Strategy (Intraday)")
        self.log(f"Final Value: ${self.portfolio.total_portfolio_value:,.2f}")
