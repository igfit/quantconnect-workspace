from AlgorithmImports import *
import numpy as np


class BXDailyTSLA(QCAlgorithm):
    """
    BX Trender Daily-Only on TSLA - Baseline comparison

    Entry: Daily BX turns bullish (crosses above 0)
    Exit: Daily BX turns bearish (crosses below 0)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.ticker = "TSLA"
        self.symbol = self.add_equity(self.ticker, Resolution.DAILY).symbol

        # BX params
        self.short_l1, self.short_l2, self.short_l3 = 5, 20, 15

        # Daily EMAs
        self.daily_ema_fast = self.ema(self.symbol, self.short_l1, Resolution.DAILY)
        self.daily_ema_slow = self.ema(self.symbol, self.short_l2, Resolution.DAILY)
        self.daily_ema_diff_window = RollingWindow[float](self.short_l3 + 1)

        self.daily_bx = None
        self.prev_daily_bx = None
        self.set_warm_up(100, Resolution.DAILY)
        self.set_benchmark("SPY")

    def calc_rsi(self, values, period):
        if len(values) < period + 1:
            return None
        changes = [values[i] - values[i-1] for i in range(1, len(values))]
        gains = [c if c > 0 else 0 for c in changes[-period:]]
        losses = [-c if c < 0 else 0 for c in changes[-period:]]
        avg_gain, avg_loss = np.mean(gains), np.mean(losses)
        if avg_loss == 0:
            return 100
        return 100 - (100 / (1 + avg_gain / avg_loss))

    def on_data(self, data):
        if self.is_warming_up or self.symbol not in data:
            return
        if not self.daily_ema_fast.is_ready or not self.daily_ema_slow.is_ready:
            return

        ema_diff = self.daily_ema_fast.current.value - self.daily_ema_slow.current.value
        self.daily_ema_diff_window.add(ema_diff)
        if not self.daily_ema_diff_window.is_ready:
            return

        rsi = self.calc_rsi([self.daily_ema_diff_window[i] for i in range(self.daily_ema_diff_window.count)][::-1], self.short_l3)
        if rsi is None:
            return
        self.daily_bx = rsi - 50

        if self.prev_daily_bx is not None:
            turned_bullish = self.prev_daily_bx < 0 and self.daily_bx >= 0
            turned_bearish = self.prev_daily_bx >= 0 and self.daily_bx < 0

            if turned_bullish:
                if not self.portfolio[self.symbol].invested:
                    self.set_holdings(self.symbol, 1.0)
                    self.debug(f"{self.time}: BUY TSLA - BX: {self.daily_bx:.1f}")
            elif turned_bearish and self.portfolio[self.symbol].invested:
                self.liquidate(self.symbol)
                self.debug(f"{self.time}: SELL TSLA - BX: {self.daily_bx:.1f}")

        self.prev_daily_bx = self.daily_bx

    def on_end_of_algorithm(self):
        self.log(f"Final: ${self.portfolio.total_portfolio_value:,.2f}")
