"""
Connors RSI Strategy

Multi-factor mean reversion using Connors RSI composite indicator.

Rationale:
Connors RSI combines three factors: RSI(3) for short-term momentum,
StreakRSI for consecutive up/down day behavior, and PercentRank for
position within recent range. This multi-factor approach is more
robust than single indicators and has been extensively backtested
by Connors Research.

Formula: ConnorsRSI = (RSI(3) + StreakRSI(2) + PercentRank(100)) / 3

Entry:
  - Price > 200 SMA (uptrend)
  - Connors RSI < 15 (composite oversold)

Exit:
  - Connors RSI > 70 (mean reverted)
  - OR 5 days elapsed (time stop)
  - OR -4% from entry (hard stop)
"""

from AlgorithmImports import *
from collections import deque


class ConnorsRSIStrategy(QCAlgorithm):
    """
    Connors RSI Mean Reversion Strategy

    Multi-factor approach for robust mean reversion signals.
    """

    def initialize(self):
        # Backtest period - Training
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2020, 12, 31)
        self.set_cash(100000)

        # Connors RSI parameters
        self.rsi_period = 3
        self.streak_period = 2
        self.rank_period = 100
        self.sma_period = 200

        # Thresholds
        self.entry_threshold = 15   # Connors RSI < 15 to enter
        self.exit_threshold = 70    # Connors RSI > 70 to exit

        # Risk management
        self.position_size_dollars = 20000
        self.stop_loss_pct = 0.04   # 4% hard stop (wider for this strategy)
        self.max_holding_days = 5
        self.max_positions = 5

        # Track positions
        self.entry_prices = {}
        self.entry_times = {}
        self.positions_count = 0

        # Universe
        self.tickers = ["TSLA", "NVDA", "AMD"]
        self.symbols = []
        self.indicators = {}

        # Custom state for Connors RSI calculation
        self.connors_state = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)

            # Standard indicators
            self.indicators[symbol] = {
                "rsi": self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY),
                "sma": self.sma(symbol, self.sma_period, Resolution.DAILY),
            }

            # Connors RSI state
            self.connors_state[symbol] = {
                "streak": 0,
                "prev_close": None,
                "closes": deque(maxlen=self.rank_period + 10),
                "streak_history": deque(maxlen=self.streak_period + 10),
                "connors_rsi": 50.0,
                "is_ready": False,
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

            price = data[symbol].close

            # Update Connors RSI
            self._update_connors_rsi(symbol, price)

            state = self.connors_state[symbol]
            if not state["is_ready"]:
                continue

            rsi = self.indicators[symbol]["rsi"]
            sma = self.indicators[symbol]["sma"]

            if not rsi.is_ready or not sma.is_ready:
                continue

            connors_rsi = state["connors_rsi"]
            sma_value = sma.current.value

            # Check exit first
            if self.portfolio[symbol].invested:
                should_exit, reason = self._check_exit(symbol, data, connors_rsi)
                if should_exit:
                    self._exit_position(symbol, reason)

            # Check entry
            elif self.positions_count < self.max_positions:
                if self._check_entry(symbol, price, connors_rsi, sma_value):
                    self._enter_position(symbol, price)

    def _update_connors_rsi(self, symbol, close: float):
        """Update Connors RSI calculation"""
        state = self.connors_state[symbol]
        rsi = self.indicators[symbol]["rsi"]

        # Update streak
        prev = state["prev_close"]
        if prev is not None:
            if close > prev:
                state["streak"] = max(1, state["streak"] + 1) if state["streak"] > 0 else 1
            elif close < prev:
                state["streak"] = min(-1, state["streak"] - 1) if state["streak"] < 0 else -1
            else:
                state["streak"] = 0

        state["prev_close"] = close
        state["closes"].append(close)
        state["streak_history"].append(state["streak"])

        # Need enough data
        if len(state["closes"]) < self.rank_period or not rsi.is_ready:
            return

        state["is_ready"] = True

        # Component 1: RSI(3)
        rsi_component = rsi.current.value

        # Component 2: StreakRSI
        streak_rsi = self._calculate_streak_rsi(state)

        # Component 3: PercentRank
        percent_rank = self._calculate_percent_rank(state, close)

        # Connors RSI = average of three
        state["connors_rsi"] = (rsi_component + streak_rsi + percent_rank) / 3

    def _calculate_streak_rsi(self, state) -> float:
        """Calculate RSI of streak values"""
        if len(state["streak_history"]) < self.streak_period + 1:
            return 50.0

        streaks = list(state["streak_history"])[-self.streak_period - 1:]
        gains = []
        losses = []

        for i in range(1, len(streaks)):
            change = streaks[i] - streaks[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_loss = sum(losses) / len(losses) if losses else 0.0001

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _calculate_percent_rank(self, state, close: float) -> float:
        """Calculate percent rank of current close"""
        closes = list(state["closes"])
        if len(closes) < 2:
            return 50.0

        count_below = sum(1 for c in closes[:-1] if c < close)
        return (count_below / (len(closes) - 1)) * 100

    def _check_entry(self, symbol, price: float, connors_rsi: float, sma: float) -> bool:
        """Check entry conditions"""
        # Uptrend filter
        if price <= sma:
            return False

        # Connors RSI oversold
        if connors_rsi >= self.entry_threshold:
            return False

        self.debug(f"{self.time.date()}: {symbol} ENTRY SIGNAL - ConnorsRSI={connors_rsi:.1f}")
        return True

    def _check_exit(self, symbol, data, connors_rsi: float) -> tuple:
        """Check exit conditions"""
        price = data[symbol].close

        # Connors RSI exit
        if connors_rsi > self.exit_threshold:
            return True, f"ConnorsRSI exit ({connors_rsi:.1f})"

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
        self.log(f"Connors RSI Strategy")
        self.log(f"Final Value: ${self.portfolio.total_portfolio_value:,.2f}")
