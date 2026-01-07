from AlgorithmImports import *
import numpy as np


class BXMTFDebug(QCAlgorithm):
    """
    BX Multi-Timeframe Debug - Track weekly BX values

    This version logs weekly BX calculations to diagnose
    why MTF strategy wasn't generating trades.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.ticker = "TSLA"
        self.symbol = self.add_equity(self.ticker, Resolution.DAILY).symbol

        # BX params (standard)
        self.short_l1, self.short_l2, self.short_l3 = 5, 20, 15

        # Daily EMAs
        self.daily_ema_fast = self.ema(self.symbol, self.short_l1, Resolution.DAILY)
        self.daily_ema_slow = self.ema(self.symbol, self.short_l2, Resolution.DAILY)
        self.daily_ema_diff_window = RollingWindow[float](self.short_l3 + 1)

        # Weekly consolidation - FIXED: Need L2 + L3 + 1 = 36 bars minimum
        self.min_weekly_bars = self.short_l2 + self.short_l3 + 1  # 20 + 15 + 1 = 36
        self.weekly_bars = RollingWindow[TradeBar](self.min_weekly_bars + 5)  # Extra buffer
        self.consolidate(self.symbol, Calendar.Weekly, self.on_weekly_bar)

        self.daily_bx = self.weekly_bx = self.prev_daily_bx = None
        self.weekly_calc_count = 0
        self.set_warm_up(100, Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_weekly_bar(self, bar):
        self.weekly_bars.add(bar)

        # Debug: Log weekly bar count
        if self.weekly_bars.count % 10 == 0:
            self.debug(f"Weekly bars collected: {self.weekly_bars.count}")

        if self.weekly_bars.count >= self.min_weekly_bars:
            closes = [self.weekly_bars[i].close for i in range(self.weekly_bars.count)][::-1]
            old_bx = self.weekly_bx
            self.weekly_bx = self.calculate_bx(closes)

            # Debug: Log weekly BX calculation
            self.weekly_calc_count += 1
            if self.weekly_calc_count <= 10 or self.weekly_calc_count % 20 == 0:
                bx_str = f"{self.weekly_bx:.2f}" if self.weekly_bx is not None else "None"
                self.debug(f"Week {self.weekly_calc_count}: Weekly BX = {bx_str}, closes={len(closes)}")

    def calculate_bx(self, closes):
        """Calculate BX value from a list of closes"""
        min_len = self.short_l2 + self.short_l3 + 1
        if len(closes) < min_len:
            return None

        ema_diffs = []
        # Start from when we have enough data for slow EMA
        for i in range(len(closes) - self.short_l2 + 1):
            end_idx = self.short_l2 + i
            if end_idx > len(closes):
                break
            subset = closes[:end_idx]
            fast = self.calc_ema(subset, self.short_l1)
            slow = self.calc_ema(subset, self.short_l2)
            if fast is not None and slow is not None:
                ema_diffs.append(fast - slow)

        if len(ema_diffs) < self.short_l3 + 1:
            return None

        rsi = self.calc_rsi(ema_diffs, self.short_l3)
        return (rsi - 50) if rsi is not None else None

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
        bar = data[self.symbol]
        if bar is None:
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

        weekly_bullish = self.weekly_bx is not None and self.weekly_bx >= 0

        if self.prev_daily_bx is not None:
            turned_bullish = self.prev_daily_bx < 0 and self.daily_bx >= 0
            turned_bearish = self.prev_daily_bx >= 0 and self.daily_bx < 0

            if turned_bullish:
                wk_str = f"{self.weekly_bx:.1f}" if self.weekly_bx is not None else "None"
                if weekly_bullish:
                    if not self.portfolio[self.symbol].invested:
                        self.set_holdings(self.symbol, 1.0)
                        self.debug(f"{self.time}: BUY - Daily: {self.daily_bx:.1f}, Weekly: {wk_str}")
                else:
                    self.debug(f"{self.time}: SKIP BUY - Daily bullish but Weekly: {wk_str}")

            elif turned_bearish and self.portfolio[self.symbol].invested:
                self.liquidate(self.symbol)
                self.debug(f"{self.time}: SELL - Daily: {self.daily_bx:.1f}")

        self.prev_daily_bx = self.daily_bx

    def on_end_of_algorithm(self):
        self.log(f"Final: ${self.portfolio.total_portfolio_value:,.2f}")
        self.log(f"Weekly BX calculations performed: {self.weekly_calc_count}")
