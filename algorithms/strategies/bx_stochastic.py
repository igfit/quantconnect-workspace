from AlgorithmImports import *
import numpy as np


class BXStochastic(QCAlgorithm):
    """
    BX Stochastic - Apply Stochastic formula to BX values

    Modification: Instead of BX = RSI - 50, calculate Stochastic of BX values
    Hypothesis: Creates more extreme signals with clear overbought/oversold zones,
                better for mean reversion opportunities within trends

    Entry: StochBX crosses above 20 from below (oversold)
    Exit: StochBX crosses below 80 from above (overbought)

    Alternative signals tested:
    - Zero crossing (like standard BX)
    - 30/70 levels
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.ticker = "TSLA"
        self.symbol = self.add_equity(self.ticker, Resolution.DAILY).symbol

        # BX params
        self.l1, self.l2, self.l3 = 5, 20, 15
        self.stoch_period = 14  # Lookback for Stochastic calculation

        # Indicators
        self.ema_fast = self.ema(self.symbol, self.l1, Resolution.DAILY)
        self.ema_slow = self.ema(self.symbol, self.l2, Resolution.DAILY)

        # Rolling windows
        self.ema_diff_window = RollingWindow[float](self.l3 + 1)
        self.bx_window = RollingWindow[float](self.stoch_period)

        # Thresholds (configurable)
        self.oversold = 20
        self.overbought = 80

        self.stoch_bx = None
        self.prev_stoch_bx = None
        self.raw_bx = None

        self.set_warm_up(150, Resolution.DAILY)
        self.set_benchmark("SPY")

    def calc_rsi(self, values, period):
        """Calculate RSI from a list of values"""
        if len(values) < period + 1:
            return None
        changes = [values[i] - values[i - 1] for i in range(1, len(values))]
        gains = [c if c > 0 else 0 for c in changes[-period:]]
        losses = [-c if c < 0 else 0 for c in changes[-period:]]
        avg_gain, avg_loss = np.mean(gains), np.mean(losses)
        if avg_loss == 0:
            return 100 if avg_gain > 0 else 50
        return 100 - (100 / (1 + avg_gain / avg_loss))

    def calc_stochastic(self, values, current_val):
        """
        Calculate Stochastic: (current - lowest) / (highest - lowest) * 100
        """
        if len(values) < 2:
            return None
        lowest = min(values)
        highest = max(values)
        if highest == lowest:
            return 50  # No range, return middle
        return ((current_val - lowest) / (highest - lowest)) * 100

    def on_data(self, data):
        if self.is_warming_up or self.symbol not in data:
            return
        if not self.ema_fast.is_ready or not self.ema_slow.is_ready:
            return

        # Calculate EMA difference
        ema_diff = self.ema_fast.current.value - self.ema_slow.current.value
        self.ema_diff_window.add(ema_diff)

        if not self.ema_diff_window.is_ready:
            return

        # Calculate raw BX
        diff_vals = [self.ema_diff_window[i] for i in range(self.ema_diff_window.count)]
        diff_vals.reverse()

        rsi = self.calc_rsi(diff_vals, self.l3)
        if rsi is None:
            return

        self.raw_bx = rsi - 50  # Standard BX value (-50 to +50)
        self.bx_window.add(self.raw_bx)

        if not self.bx_window.is_ready:
            return

        # Calculate Stochastic of BX values
        bx_vals = [self.bx_window[i] for i in range(self.bx_window.count)]
        self.stoch_bx = self.calc_stochastic(bx_vals, self.raw_bx)

        if self.stoch_bx is None:
            return

        if self.prev_stoch_bx is not None:
            # Oversold breakout entry (crosses above 20)
            crossed_above_oversold = self.prev_stoch_bx < self.oversold and self.stoch_bx >= self.oversold
            # Overbought breakdown exit (crosses below 80)
            crossed_below_overbought = self.prev_stoch_bx >= self.overbought and self.stoch_bx < self.overbought

            if crossed_above_oversold:
                if not self.portfolio[self.symbol].invested:
                    self.set_holdings(self.symbol, 1.0)
                    self.debug(f"{self.time}: BUY {self.ticker} - StochBX: {self.stoch_bx:.1f}, RawBX: {self.raw_bx:.1f}")
            elif crossed_below_overbought and self.portfolio[self.symbol].invested:
                self.liquidate(self.symbol)
                self.debug(f"{self.time}: SELL {self.ticker} - StochBX: {self.stoch_bx:.1f}, RawBX: {self.raw_bx:.1f}")

        self.prev_stoch_bx = self.stoch_bx

    def on_end_of_algorithm(self):
        self.log(f"BX-Stochastic Final: ${self.portfolio.total_portfolio_value:,.2f}")
