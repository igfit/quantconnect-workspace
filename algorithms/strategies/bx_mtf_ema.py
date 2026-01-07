from AlgorithmImports import *
import numpy as np


class BXMTFEma(QCAlgorithm):
    """
    BX Daily with Weekly EMA Crossover Filter - TSLA

    Simpler weekly filter: just EMA(5) > EMA(20) = bullish trend
    Much faster to compute and respond to trend changes.

    Entry: Daily BX turns bullish AND weekly EMA(5) > EMA(20)
    Exit: Daily BX turns bearish
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.ticker = "TSLA"
        self.symbol = self.add_equity(self.ticker, Resolution.DAILY).symbol

        # Daily BX params
        self.daily_l1, self.daily_l2, self.daily_l3 = 5, 20, 15

        # Daily EMAs for BX
        self.daily_ema_fast = self.ema(self.symbol, self.daily_l1, Resolution.DAILY)
        self.daily_ema_slow = self.ema(self.symbol, self.daily_l2, Resolution.DAILY)
        self.daily_ema_diff_window = RollingWindow[float](self.daily_l3 + 1)

        # Weekly EMA filter (simple crossover)
        self.weekly_bars = RollingWindow[TradeBar](25)
        self.consolidate(self.symbol, Calendar.Weekly, self.on_weekly_bar)
        self.weekly_ema_fast = None
        self.weekly_ema_slow = None

        self.daily_bx = None
        self.prev_daily_bx = None
        self.set_warm_up(100, Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_weekly_bar(self, bar):
        self.weekly_bars.add(bar)
        if self.weekly_bars.count >= 20:
            closes = [self.weekly_bars[i].close for i in range(self.weekly_bars.count)][::-1]
            self.weekly_ema_fast = self.calc_ema(closes, 5)
            self.weekly_ema_slow = self.calc_ema(closes, 20)

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

        rsi = self.calc_rsi([self.daily_ema_diff_window[i] for i in range(self.daily_ema_diff_window.count)][::-1], self.daily_l3)
        if rsi is None:
            return
        self.daily_bx = rsi - 50

        # Weekly EMA filter: fast > slow = uptrend
        weekly_uptrend = (self.weekly_ema_fast is not None and
                         self.weekly_ema_slow is not None and
                         self.weekly_ema_fast > self.weekly_ema_slow)

        if self.prev_daily_bx is not None:
            turned_bullish = self.prev_daily_bx < 0 and self.daily_bx >= 0
            turned_bearish = self.prev_daily_bx >= 0 and self.daily_bx < 0

            if turned_bullish and weekly_uptrend:
                if not self.portfolio[self.symbol].invested:
                    self.set_holdings(self.symbol, 1.0)
                    self.debug(f"{self.time}: BUY - Daily BX: {self.daily_bx:.1f}, Weekly EMA5>20")

            elif turned_bearish and self.portfolio[self.symbol].invested:
                self.liquidate(self.symbol)
                self.debug(f"{self.time}: SELL - Daily BX: {self.daily_bx:.1f}")

        self.prev_daily_bx = self.daily_bx

    def on_end_of_algorithm(self):
        self.log(f"Final: ${self.portfolio.total_portfolio_value:,.2f}")
