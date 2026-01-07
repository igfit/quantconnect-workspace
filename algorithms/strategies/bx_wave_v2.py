from AlgorithmImports import *
import numpy as np


class BXWaveV2Strategy(QCAlgorithm):
    """
    Combined BX Trender + WaveTrend Strategy V2 (Looser Conditions)

    Strategy:
        - BX Trender acts as a FILTER (only trade when bullish)
        - WaveTrend provides ENTRY timing (any cross up)
        - Exit when BX turns bearish OR WaveTrend crosses down

    This version is less restrictive than v1 to generate more trades.

    Universe: SPY
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        # Add equity
        self.symbol = self.add_equity("SPY", Resolution.DAILY).symbol

        # BX Trender parameters
        self.short_l1 = 5
        self.short_l2 = 20
        self.short_l3 = 15

        # WaveTrend parameters
        self.n1 = 10
        self.n2 = 21

        # EMAs for BX Trender
        self.ema_fast = self.ema(self.symbol, self.short_l1, Resolution.DAILY)
        self.ema_slow = self.ema(self.symbol, self.short_l2, Resolution.DAILY)

        # Rolling windows for BX Trender
        self.ema_diff_window = RollingWindow[float](self.short_l3 + 1)

        # Rolling windows for WaveTrend
        self.hlc3_window = RollingWindow[float](50)
        self.d_window = RollingWindow[float](50)
        self.ci_window = RollingWindow[float](50)
        self.wt1_window = RollingWindow[float](5)

        # Previous values
        self.prev_short_xt = None
        self.prev_wt1 = None
        self.prev_wt2 = None

        # Warm up
        self.set_warm_up(200, Resolution.DAILY)

        # Set benchmark
        self.set_benchmark("SPY")

    def calculate_rsi(self, values, period):
        """Calculate RSI on a series of values"""
        if len(values) < period + 1:
            return None

        changes = []
        vals = list(values)[:period + 1]
        vals.reverse()

        for i in range(1, len(vals)):
            changes.append(vals[i] - vals[i-1])

        gains = [c if c > 0 else 0 for c in changes]
        losses = [-c if c < 0 else 0 for c in changes]

        avg_gain = np.mean(gains) if gains else 0
        avg_loss = np.mean(losses) if losses else 0

        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def calculate_ema(self, values, period):
        """Calculate EMA of a list of values"""
        if len(values) < period:
            return None
        multiplier = 2 / (period + 1)
        ema = values[0]
        for val in values[1:]:
            ema = (val - ema) * multiplier + ema
        return ema

    def on_data(self, data):
        if self.is_warming_up:
            return

        if self.symbol not in data or data[self.symbol] is None:
            return

        if not self.ema_fast.is_ready or not self.ema_slow.is_ready:
            return

        bar = data[self.symbol]

        # ========== BX TRENDER CALCULATION ==========
        ema_diff = self.ema_fast.current.value - self.ema_slow.current.value
        self.ema_diff_window.add(ema_diff)

        short_xt = None
        if self.ema_diff_window.is_ready:
            short_rsi = self.calculate_rsi(
                [self.ema_diff_window[i] for i in range(self.ema_diff_window.count)],
                self.short_l3
            )
            if short_rsi is not None:
                short_xt = short_rsi - 50

        # ========== WAVETREND CALCULATION ==========
        hlc3 = (bar.high + bar.low + bar.close) / 3
        self.hlc3_window.add(hlc3)

        wt1 = None
        wt2 = None

        if self.hlc3_window.count >= self.n1 + self.n2:
            hlc3_vals = [self.hlc3_window[i] for i in range(min(self.hlc3_window.count, 50))]
            hlc3_vals.reverse()

            esa = self.calculate_ema(hlc3_vals[-self.n1-10:], self.n1)
            if esa is not None:
                diff = abs(hlc3 - esa)
                self.d_window.add(diff)

                if self.d_window.count >= self.n1:
                    d_vals = [self.d_window[i] for i in range(min(self.d_window.count, 20))]
                    d_vals.reverse()
                    d = self.calculate_ema(d_vals, self.n1)

                    if d is not None and d != 0:
                        ci = (hlc3 - esa) / (0.015 * d)
                        self.ci_window.add(ci)

                        if self.ci_window.count >= self.n2:
                            ci_vals = [self.ci_window[i] for i in range(min(self.ci_window.count, 30))]
                            ci_vals.reverse()
                            wt1 = self.calculate_ema(ci_vals, self.n2)

                            if wt1 is not None:
                                self.wt1_window.add(wt1)
                                if self.wt1_window.count >= 4:
                                    wt1_vals = [self.wt1_window[i] for i in range(4)]
                                    wt2 = np.mean(wt1_vals)

        # ========== COMBINED TRADING LOGIC V2 ==========
        if short_xt is None or wt1 is None or wt2 is None:
            self.prev_short_xt = short_xt
            self.prev_wt1 = wt1
            self.prev_wt2 = wt2
            return

        if self.prev_short_xt is not None and self.prev_wt1 is not None and self.prev_wt2 is not None:
            # BX Trender state (FILTER)
            bx_bullish = short_xt >= 0
            bx_just_turned_bearish = self.prev_short_xt >= 0 and short_xt < 0

            # WaveTrend state (TIMING)
            wt_cross_up = self.prev_wt1 <= self.prev_wt2 and wt1 > wt2
            wt_cross_down = self.prev_wt1 >= self.prev_wt2 and wt1 < wt2

            # BUY: BX is bullish AND WaveTrend crosses up
            buy_signal = bx_bullish and wt_cross_up

            # SELL: BX turns bearish OR WaveTrend crosses down
            sell_signal = bx_just_turned_bearish or wt_cross_down

            if buy_signal and not self.portfolio[self.symbol].invested:
                self.set_holdings(self.symbol, 1.0)
                self.debug(f"{self.time}: BUY - BX bullish ({short_xt:.1f}) + WT cross up ({wt1:.1f})")

            elif sell_signal and self.portfolio[self.symbol].invested:
                reason = "BX bearish" if bx_just_turned_bearish else "WT cross down"
                self.debug(f"{self.time}: SELL - {reason} (BX: {short_xt:.1f}, WT: {wt1:.1f})")
                self.liquidate(self.symbol)

        self.prev_short_xt = short_xt
        self.prev_wt1 = wt1
        self.prev_wt2 = wt2

    def on_end_of_algorithm(self):
        self.log(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
