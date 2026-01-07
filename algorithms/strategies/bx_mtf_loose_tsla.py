from AlgorithmImports import *
import numpy as np


class BXMTFLooseTSLA(QCAlgorithm):
    """
    BX Multi-Timeframe on TSLA - Looser Conditions

    Entry: Daily BX turns bullish AND weekly BX is positive (filter)
    Exit: Daily BX turns bearish (regardless of weekly)

    Key difference from strict MTF:
    - Weekly only needs to be positive (not require alignment)
    - If weekly not ready, skip check (allow trading)
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

        # Weekly consolidation
        self.weekly_bars = RollingWindow[TradeBar](25)
        self.consolidate(self.symbol, Calendar.Weekly, self.on_weekly_bar)

        self.daily_bx = self.weekly_bx = self.prev_daily_bx = None
        self.set_warm_up(150, Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_weekly_bar(self, bar):
        self.weekly_bars.add(bar)
        if self.weekly_bars.count >= 25:
            self.weekly_bx = self.calculate_bx([self.weekly_bars[i].close for i in range(min(self.weekly_bars.count, 25))][::-1])

    def calculate_bx(self, closes):
        if len(closes) < 25:
            return None
        ema_diffs = []
        for i in range(len(closes) - max(self.short_l1, self.short_l2)):
            fast = self.calc_ema(closes[:self.short_l1 + i + 1], self.short_l1)
            slow = self.calc_ema(closes[:self.short_l2 + i + 1], self.short_l2)
            if fast and slow:
                ema_diffs.append(fast - slow)
        if len(ema_diffs) < self.short_l3 + 1:
            return None
        rsi = self.calc_rsi(ema_diffs[-self.short_l3-1:], self.short_l3)
        return (rsi - 50) if rsi else None

    def calc_ema(self, values, period):
        if len(values) < period:
            return None
        m = 2 / (period + 1)
        ema = values[0]
        for v in values[1:]:
            ema = (v - ema) * m + ema
        return ema

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

        # Weekly filter: if weekly is ready and positive, or weekly not ready (allow trading)
        weekly_ok = self.weekly_bx is None or self.weekly_bx >= 0

        if self.prev_daily_bx is not None:
            turned_bullish = self.prev_daily_bx < 0 and self.daily_bx >= 0
            turned_bearish = self.prev_daily_bx >= 0 and self.daily_bx < 0

            if turned_bullish and weekly_ok:
                if not self.portfolio[self.symbol].invested:
                    self.set_holdings(self.symbol, 1.0)
                    wk_str = f"{self.weekly_bx:.1f}" if self.weekly_bx else "N/A"
                    self.debug(f"{self.time}: BUY TSLA - Daily: {self.daily_bx:.1f}, Weekly: {wk_str}")
            elif turned_bearish and self.portfolio[self.symbol].invested:
                self.liquidate(self.symbol)
                self.debug(f"{self.time}: SELL TSLA - Daily: {self.daily_bx:.1f}")

        self.prev_daily_bx = self.daily_bx

    def on_end_of_algorithm(self):
        self.log(f"Final: ${self.portfolio.total_portfolio_value:,.2f}")
