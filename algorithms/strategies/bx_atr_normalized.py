from AlgorithmImports import *
import numpy as np


class BXATRNormalized(QCAlgorithm):
    """
    BX Trender with ATR Normalization - Volatility-Adjusted Version

    Modification: Normalize EMA difference by ATR before applying RSI
    Hypothesis: Makes signals comparable across different volatility regimes,
                reduces whipsaws during high-volatility periods

    Entry: Normalized BX crosses above 0
    Exit: Normalized BX crosses below 0
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.ticker = "TSLA"
        self.symbol = self.add_equity(self.ticker, Resolution.DAILY).symbol

        # BX params
        self.l1, self.l2, self.l3 = 5, 20, 15
        self.atr_period = 14

        # Indicators
        self.ema_fast = self.ema(self.symbol, self.l1, Resolution.DAILY)
        self.ema_slow = self.ema(self.symbol, self.l2, Resolution.DAILY)
        self.atr_indicator = self.atr(self.symbol, self.atr_period, MovingAverageType.SIMPLE, Resolution.DAILY)

        # Rolling windows for calculations
        self.normalized_diff_window = RollingWindow[float](self.l3 + 1)

        self.bx = None
        self.prev_bx = None

        self.set_warm_up(100, Resolution.DAILY)
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

    def on_data(self, data):
        if self.is_warming_up or self.symbol not in data:
            return
        if not self.ema_fast.is_ready or not self.ema_slow.is_ready or not self.atr_indicator.is_ready:
            return

        # Key difference: normalize EMA difference by ATR
        atr_val = self.atr_indicator.current.value
        if atr_val <= 0:
            return

        ema_diff = self.ema_fast.current.value - self.ema_slow.current.value
        normalized_diff = ema_diff / atr_val  # Normalize by ATR

        self.normalized_diff_window.add(normalized_diff)
        if not self.normalized_diff_window.is_ready:
            return

        # Calculate RSI on normalized differences
        diff_vals = [self.normalized_diff_window[i] for i in range(self.normalized_diff_window.count)]
        diff_vals.reverse()  # Oldest first

        rsi = self.calc_rsi(diff_vals, self.l3)
        if rsi is None:
            return

        self.bx = rsi - 50

        if self.prev_bx is not None:
            turned_bullish = self.prev_bx < 0 and self.bx >= 0
            turned_bearish = self.prev_bx >= 0 and self.bx < 0

            if turned_bullish:
                if not self.portfolio[self.symbol].invested:
                    self.set_holdings(self.symbol, 1.0)
                    self.debug(f"{self.time}: BUY {self.ticker} - BX-ATR: {self.bx:.1f}")
            elif turned_bearish and self.portfolio[self.symbol].invested:
                self.liquidate(self.symbol)
                self.debug(f"{self.time}: SELL {self.ticker} - BX-ATR: {self.bx:.1f}")

        self.prev_bx = self.bx

    def on_end_of_algorithm(self):
        self.log(f"BX-ATR Final: ${self.portfolio.total_portfolio_value:,.2f}")
