"""
Gap Fade Strategy (Intraday)

Fade overnight gaps > 2% expecting partial fill within the trading day.

Rationale:
Large overnight gaps often overshoot fair value due to after-hours illiquidity.
Without fundamental news, these gaps tend to partially fill as regular market
hours bring more liquidity. We fade the gap direction and exit at partial fill
or end of day.

Entry (Gap Up):
  - Open > Previous Close * 1.02 (2%+ gap up)
  - Short at open, expecting fade

Entry (Gap Down):
  - Open < Previous Close * 0.98 (2%+ gap down)
  - Long at open, expecting bounce

Exit:
  - 50% of gap filled
  - OR end of day (flat overnight)
  - OR 1.5% stop loss

Resolution: MINUTE (intraday strategy)
"""

from AlgorithmImports import *


class GapFadeStrategy(QCAlgorithm):
    """
    Gap Fade Intraday Strategy

    Fades large overnight gaps expecting mean reversion during the day.
    """

    def initialize(self):
        # Backtest period
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2020, 12, 31)
        self.set_cash(100000)

        # Strategy parameters
        self.gap_threshold = 0.02       # 2% minimum gap
        self.fill_target = 0.50         # Exit at 50% gap fill
        self.stop_loss_pct = 0.015      # 1.5% stop

        # Risk management
        self.position_size_dollars = 15000
        self.max_positions = 3

        # State
        self.prev_closes = {}
        self.entry_prices = {}
        self.gap_directions = {}        # 1 for gap up (we short), -1 for gap down (we long)
        self.gap_sizes = {}
        self.positions_count = 0
        self.traded_today = set()       # Prevent multiple entries per day

        # Universe - high-beta, liquid stocks for intraday
        self.tickers = ["TSLA", "NVDA", "AMD"]
        self.symbols = []

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.MINUTE)
            symbol = equity.symbol
            self.symbols.append(symbol)

            # Tighter slippage for intraday
            equity.set_slippage_model(ConstantSlippageModel(0.0002))  # 2 bps
            equity.set_fee_model(InteractiveBrokersFeeModel())

        # No warmup needed for this strategy
        self.set_warm_up(5, Resolution.DAILY)

        # Benchmark
        self.add_equity("SPY", Resolution.MINUTE)
        self.set_benchmark("SPY")

        # Schedule: Store previous close at end of day
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close("SPY", 1),
            self.store_closes
        )

        # Schedule: Force close all positions at end of day
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

    def store_closes(self):
        """Store previous day's close for gap calculation"""
        for symbol in self.symbols:
            if symbol in self.securities and self.securities[symbol].price > 0:
                self.prev_closes[symbol] = self.securities[symbol].price

    def reset_daily_tracking(self):
        """Reset daily tracking variables"""
        self.traded_today.clear()

    def on_data(self, data):
        """Main trading logic"""
        if self.is_warming_up:
            return

        # Only trade in first 30 minutes after open
        if self.time.hour >= 10 or (self.time.hour == 9 and self.time.minute >= 45):
            # After first 30 min, only monitor exits
            self._check_exits(data)
            return

        for symbol in self.symbols:
            if symbol not in data or data[symbol] is None:
                continue

            # Skip if already traded this symbol today
            if symbol in self.traded_today:
                continue

            # Skip if no previous close
            if symbol not in self.prev_closes:
                continue

            price = data[symbol].close
            prev_close = self.prev_closes[symbol]

            # Check if we have a position
            if self.portfolio[symbol].invested:
                self._check_exit(symbol, data)
            elif self.positions_count < self.max_positions:
                self._check_entry(symbol, price, prev_close)

    def _check_entry(self, symbol, price: float, prev_close: float):
        """Check for gap entry opportunity"""
        gap_pct = (price - prev_close) / prev_close

        if abs(gap_pct) < self.gap_threshold:
            return

        if gap_pct > self.gap_threshold:
            # Gap up - short it (expect fade)
            self._enter_position(symbol, price, "short", gap_pct)

        elif gap_pct < -self.gap_threshold:
            # Gap down - long it (expect bounce)
            self._enter_position(symbol, price, "long", gap_pct)

    def _enter_position(self, symbol, price: float, direction: str, gap_pct: float):
        """Enter position"""
        shares = int(self.position_size_dollars / price)

        if shares == 0:
            return

        if direction == "short":
            self.market_order(symbol, -shares)
            self.gap_directions[symbol] = 1  # Gap up, we're short
        else:
            self.market_order(symbol, shares)
            self.gap_directions[symbol] = -1  # Gap down, we're long

        self.entry_prices[symbol] = price
        self.gap_sizes[symbol] = abs(gap_pct)
        self.positions_count += 1
        self.traded_today.add(symbol)

        self.debug(f"{self.time}: GAP FADE ENTRY {symbol} - {direction.upper()} @ ${price:.2f}, Gap: {gap_pct:.1%}")

    def _check_exits(self, data):
        """Check exits for all positions"""
        for symbol in self.symbols:
            if self.portfolio[symbol].invested:
                self._check_exit(symbol, data)

    def _check_exit(self, symbol, data):
        """Check exit conditions for a position"""
        if symbol not in data or data[symbol] is None:
            return

        price = data[symbol].close
        entry = self.entry_prices.get(symbol)
        gap_dir = self.gap_directions.get(symbol)
        gap_size = self.gap_sizes.get(symbol)

        if entry is None or gap_dir is None:
            return

        # Calculate how much of gap has filled
        if gap_dir == 1:  # We're short (fading gap up)
            # Gap fills as price drops toward prev close
            fill_pct = (entry - price) / (entry * gap_size) if gap_size > 0 else 0
            pnl_pct = (entry - price) / entry  # Profit when price drops
        else:  # We're long (fading gap down)
            # Gap fills as price rises toward prev close
            fill_pct = (price - entry) / (entry * gap_size) if gap_size > 0 else 0
            pnl_pct = (price - entry) / entry  # Profit when price rises

        # Exit at target fill
        if fill_pct >= self.fill_target:
            self._exit_position(symbol, f"Target fill ({fill_pct:.0%})")
            return

        # Stop loss
        if pnl_pct < -self.stop_loss_pct:
            self._exit_position(symbol, f"Stop loss ({pnl_pct:.1%})")
            return

    def _exit_position(self, symbol, reason: str):
        """Exit position"""
        if self.portfolio[symbol].invested:
            entry = self.entry_prices.get(symbol, 0)
            current = self.securities[symbol].price
            pnl_pct = (current - entry) / entry if entry > 0 else 0

            # Adjust P&L sign for shorts
            if self.gap_directions.get(symbol) == 1:
                pnl_pct = -pnl_pct

            self.liquidate(symbol)

            self.debug(f"{self.time}: GAP FADE EXIT {symbol} - {reason}, P&L: {pnl_pct:.1%}")

            # Cleanup
            if symbol in self.entry_prices:
                del self.entry_prices[symbol]
            if symbol in self.gap_directions:
                del self.gap_directions[symbol]
            if symbol in self.gap_sizes:
                del self.gap_sizes[symbol]
            self.positions_count = max(0, self.positions_count - 1)

    def close_all_positions(self):
        """Close all positions at end of day"""
        for symbol in self.symbols:
            if self.portfolio[symbol].invested:
                self._exit_position(symbol, "End of day")

    def on_end_of_algorithm(self):
        """Log results"""
        self.log(f"Gap Fade Strategy (Intraday)")
        self.log(f"Final Value: ${self.portfolio.total_portfolio_value:,.2f}")
