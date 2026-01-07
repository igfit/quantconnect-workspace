from AlgorithmImports import *
import numpy as np


class BXConnorsNVDA(QCAlgorithm):
    """
    BX Connors on NVDA - Testing robustness on different high-beta stock
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.ticker = "NVDA"
        self.symbol = self.add_equity(self.ticker, Resolution.DAILY).symbol

        self.short_l1, self.short_l2, self.short_l3 = 5, 10, 8
        self.med_l1, self.med_l2, self.med_l3 = 5, 20, 15
        self.roc_period = 1
        self.roc_lookback = 100

        self.weight_bx_short = 0.25
        self.weight_bx_medium = 0.35
        self.weight_streak = 0.20
        self.weight_roc = 0.20

        self.ema_fast_short = self.ema(self.symbol, self.short_l1, Resolution.DAILY)
        self.ema_slow_short = self.ema(self.symbol, self.short_l2, Resolution.DAILY)
        self.ema_fast_med = self.ema(self.symbol, self.med_l1, Resolution.DAILY)
        self.ema_slow_med = self.ema(self.symbol, self.med_l2, Resolution.DAILY)

        self.diff_window_short = RollingWindow[float](self.short_l3 + 1)
        self.diff_window_med = RollingWindow[float](self.med_l3 + 1)
        self.close_window = RollingWindow[float](self.roc_lookback + 2)
        self.roc_window = RollingWindow[float](self.roc_lookback)

        self.streak = 0
        self.streak_window = RollingWindow[float](15)
        self.prev_close = None
        self.composite = None
        self.prev_composite = None

        self.set_warm_up(150, Resolution.DAILY)
        self.set_benchmark("SPY")

    def calc_rsi(self, values, period):
        if len(values) < period + 1:
            return None
        changes = [values[i] - values[i - 1] for i in range(1, len(values))]
        gains = [c if c > 0 else 0 for c in changes[-period:]]
        losses = [-c if c < 0 else 0 for c in changes[-period:]]
        avg_gain, avg_loss = np.mean(gains), np.mean(losses)
        if avg_loss == 0:
            return 100 if avg_gain > 0 else 50
        return 100 - (100 / (1 + avg_gain / avg_loss))

    def calc_bx(self, diff_window, l3):
        if not diff_window.is_ready:
            return None
        diff_vals = [diff_window[i] for i in range(diff_window.count)]
        diff_vals.reverse()
        rsi = self.calc_rsi(diff_vals, l3)
        return rsi if rsi else None

    def calc_streak_rsi(self):
        if self.streak_window.count < 3:
            return 50
        streak_vals = [self.streak_window[i] for i in range(min(self.streak_window.count, 10))]
        streak_vals.reverse()
        rsi = self.calc_rsi(streak_vals, 2)
        return rsi if rsi else 50

    def calc_roc_percentile(self):
        if self.roc_window.count < 10:
            return 50
        roc_vals = [self.roc_window[i] for i in range(self.roc_window.count)]
        current_roc = roc_vals[0]
        count_below = sum(1 for r in roc_vals if r < current_roc)
        return (count_below / len(roc_vals)) * 100

    def on_data(self, data):
        if self.is_warming_up or self.symbol not in data:
            return
        if data[self.symbol] is None:
            return

        close = data[self.symbol].close
        self.close_window.add(close)

        if self.prev_close is not None:
            if close > self.prev_close:
                self.streak = max(1, self.streak + 1) if self.streak > 0 else 1
            elif close < self.prev_close:
                self.streak = min(-1, self.streak - 1) if self.streak < 0 else -1
            self.streak_window.add(self.streak)

        if self.close_window.count >= 2:
            roc = (close - self.close_window[1]) / self.close_window[1] * 100
            self.roc_window.add(roc)

        self.prev_close = close

        if not self.ema_fast_short.is_ready or not self.ema_slow_short.is_ready:
            return
        if not self.ema_fast_med.is_ready or not self.ema_slow_med.is_ready:
            return

        diff_short = self.ema_fast_short.current.value - self.ema_slow_short.current.value
        diff_med = self.ema_fast_med.current.value - self.ema_slow_med.current.value

        self.diff_window_short.add(diff_short)
        self.diff_window_med.add(diff_med)

        bx_short = self.calc_bx(self.diff_window_short, self.short_l3)
        bx_med = self.calc_bx(self.diff_window_med, self.med_l3)
        streak_rsi = self.calc_streak_rsi()
        roc_pctl = self.calc_roc_percentile()

        if bx_short is None or bx_med is None:
            return

        self.composite = (
            self.weight_bx_short * bx_short +
            self.weight_bx_medium * bx_med +
            self.weight_streak * streak_rsi +
            self.weight_roc * roc_pctl
        )

        if self.prev_composite is not None:
            turned_bullish = self.prev_composite < 50 and self.composite >= 50
            turned_bearish = self.prev_composite >= 50 and self.composite < 50

            if turned_bullish and not self.portfolio[self.symbol].invested:
                self.set_holdings(self.symbol, 1.0)
                self.debug(f"{self.time}: BUY {self.ticker}")
            elif turned_bearish and self.portfolio[self.symbol].invested:
                self.liquidate(self.symbol)
                self.debug(f"{self.time}: SELL {self.ticker}")

        self.prev_composite = self.composite

    def on_end_of_algorithm(self):
        self.log(f"BX-Connors NVDA Final: ${self.portfolio.total_portfolio_value:,.2f}")
