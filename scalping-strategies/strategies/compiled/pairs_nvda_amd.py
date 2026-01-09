"""
Pairs Trading Strategy: NVDA/AMD

Mean reversion on NVDA/AMD spread for market-neutral returns.

Rationale:
NVDA and AMD are highly correlated stocks in the semiconductor sector.
When the spread between them deviates beyond 2 standard deviations from
the 60-day mean, we expect mean reversion. This is market-neutral -
we're long one and short the other.

Entry (Long Spread - long NVDA, short AMD):
  - Z-score > 2.0 (spread too wide)

Entry (Short Spread - short NVDA, long AMD):
  - Z-score < -2.0 (spread too narrow)

Exit:
  - Z-score crosses 0.5 toward 0 (mean reverted)
  - OR |Z-score| > 3.5 (stop loss - spread diverging)
  - OR 20 days elapsed (time stop)

Academic basis: Gatev, Goetzmann & Rouwenhorst (2006)
"""

from AlgorithmImports import *
from collections import deque
import math


class PairsNVDAAMD(QCAlgorithm):
    """
    Pairs Trading Strategy for NVDA/AMD

    Market-neutral strategy exploiting mean reversion in correlated stocks.
    """

    def initialize(self):
        # Backtest period - Training
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2020, 12, 31)
        self.set_cash(100000)

        # Pair configuration
        self.symbol_a_ticker = "NVDA"
        self.symbol_b_ticker = "AMD"

        # Z-score parameters
        self.lookback = 60              # Days for spread statistics
        self.entry_zscore = 2.0         # Enter when |z| > 2
        self.exit_zscore = 0.5          # Exit when |z| < 0.5
        self.stop_zscore = 3.5          # Stop when |z| > 3.5

        # Risk management
        self.position_dollars_per_leg = 25000  # $25K per leg = $50K total
        self.max_holding_days = 20

        # State
        self.prices_a = deque(maxlen=self.lookback + 10)
        self.prices_b = deque(maxlen=self.lookback + 10)
        self.spreads = deque(maxlen=self.lookback + 10)
        self.hedge_ratio = 1.0
        self.current_zscore = 0.0
        self.spread_mean = 0.0
        self.spread_std = 1.0
        self.is_ready = False

        self.entry_time = None
        self.position_type = None  # "long_spread" or "short_spread"

        # Add securities
        self.symbol_a = self.add_equity(self.symbol_a_ticker, Resolution.DAILY).symbol
        self.symbol_b = self.add_equity(self.symbol_b_ticker, Resolution.DAILY).symbol

        # Set models
        for symbol in [self.symbol_a, self.symbol_b]:
            self.securities[symbol].set_slippage_model(ConstantSlippageModel(0.001))
            self.securities[symbol].set_fee_model(InteractiveBrokersFeeModel())

        # Warmup
        self.set_warm_up(self.lookback + 10, Resolution.DAILY)

        # Benchmark
        self.add_equity("SPY", Resolution.DAILY)
        self.set_benchmark("SPY")

        # Schedule time stops
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close("SPY", 5),
            self.check_time_stop
        )

    def on_data(self, data):
        """Main trading logic"""
        if self.is_warming_up:
            return

        # Check data availability
        if self.symbol_a not in data or self.symbol_b not in data:
            return
        if data[self.symbol_a] is None or data[self.symbol_b] is None:
            return

        price_a = data[self.symbol_a].close
        price_b = data[self.symbol_b].close

        # Update spread statistics
        self._update_spread_stats(price_a, price_b)

        if not self.is_ready:
            return

        # Check if we have a position
        has_position = (
            self.portfolio[self.symbol_a].invested or
            self.portfolio[self.symbol_b].invested
        )

        if has_position:
            # Check exit conditions
            should_exit, reason = self._check_exit()
            if should_exit:
                self._exit_position(reason)
        else:
            # Check entry conditions
            self._check_entry(price_a, price_b)

    def _update_spread_stats(self, price_a: float, price_b: float):
        """Update spread statistics"""
        self.prices_a.append(price_a)
        self.prices_b.append(price_b)

        # Calculate hedge ratio using regression
        if len(self.prices_a) >= 20:
            self.hedge_ratio = self._calculate_hedge_ratio()

        # Calculate spread
        spread = price_a - self.hedge_ratio * price_b
        self.spreads.append(spread)

        # Need enough data
        if len(self.spreads) < self.lookback:
            return

        self.is_ready = True

        # Calculate mean and std
        spreads_list = list(self.spreads)[-self.lookback:]
        self.spread_mean = sum(spreads_list) / len(spreads_list)

        variance = sum((s - self.spread_mean) ** 2 for s in spreads_list) / len(spreads_list)
        self.spread_std = math.sqrt(variance) if variance > 0 else 0.0001

        # Calculate z-score
        current_spread = spreads_list[-1]
        self.current_zscore = (current_spread - self.spread_mean) / self.spread_std

    def _calculate_hedge_ratio(self) -> float:
        """Calculate hedge ratio via simple regression"""
        prices_a = list(self.prices_a)[-self.lookback:]
        prices_b = list(self.prices_b)[-self.lookback:]

        n = len(prices_a)
        mean_a = sum(prices_a) / n
        mean_b = sum(prices_b) / n

        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(prices_a, prices_b)) / n
        var_b = sum((b - mean_b) ** 2 for b in prices_b) / n

        if var_b == 0:
            return 1.0

        return cov / var_b

    def _check_entry(self, price_a: float, price_b: float):
        """Check entry conditions"""
        z = self.current_zscore

        if z > self.entry_zscore:
            # Spread too wide - expect it to narrow
            # Short spread: Short A (NVDA), Long B (AMD)
            self._enter_position("short_spread", price_a, price_b)

        elif z < -self.entry_zscore:
            # Spread too narrow - expect it to widen
            # Long spread: Long A (NVDA), Short B (AMD)
            self._enter_position("long_spread", price_a, price_b)

    def _enter_position(self, position_type: str, price_a: float, price_b: float):
        """Enter a pairs position"""
        shares_a = int(self.position_dollars_per_leg / price_a)
        shares_b = int(self.position_dollars_per_leg / price_b)

        if shares_a == 0 or shares_b == 0:
            return

        if position_type == "long_spread":
            # Long A, Short B
            self.market_order(self.symbol_a, shares_a)
            self.market_order(self.symbol_b, -shares_b)
            self.debug(f"{self.time.date()}: LONG SPREAD - Long {self.symbol_a_ticker} {shares_a}, Short {self.symbol_b_ticker} {shares_b}, Z={self.current_zscore:.2f}")

        else:  # short_spread
            # Short A, Long B
            self.market_order(self.symbol_a, -shares_a)
            self.market_order(self.symbol_b, shares_b)
            self.debug(f"{self.time.date()}: SHORT SPREAD - Short {self.symbol_a_ticker} {shares_a}, Long {self.symbol_b_ticker} {shares_b}, Z={self.current_zscore:.2f}")

        self.position_type = position_type
        self.entry_time = self.time

    def _check_exit(self) -> tuple:
        """Check exit conditions"""
        z = self.current_zscore

        # Mean reversion exit
        if self.position_type == "long_spread" and z > -self.exit_zscore:
            return True, f"Mean reverted (z={z:.2f})"

        if self.position_type == "short_spread" and z < self.exit_zscore:
            return True, f"Mean reverted (z={z:.2f})"

        # Stop loss - spread diverging
        if abs(z) > self.stop_zscore:
            return True, f"Stop loss (z={z:.2f})"

        return False, ""

    def _exit_position(self, reason: str):
        """Exit the pairs position"""
        self.liquidate(self.symbol_a)
        self.liquidate(self.symbol_b)

        self.debug(f"{self.time.date()}: EXIT PAIRS - {reason}")

        self.position_type = None
        self.entry_time = None

    def check_time_stop(self):
        """Check time-based exit"""
        if self.entry_time is None:
            return

        days_held = (self.time - self.entry_time).days
        if days_held >= self.max_holding_days:
            self._exit_position(f"Time stop ({days_held} days)")

    def on_end_of_algorithm(self):
        """Log results"""
        self.log(f"Pairs Trading: {self.symbol_a_ticker}/{self.symbol_b_ticker}")
        self.log(f"Final Value: ${self.portfolio.total_portfolio_value:,.2f}")
        self.log(f"Final Hedge Ratio: {self.hedge_ratio:.3f}")
