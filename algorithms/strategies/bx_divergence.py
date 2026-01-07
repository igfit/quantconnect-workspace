from AlgorithmImports import *
import numpy as np


class BXDivergence(QCAlgorithm):
    """
    BX with Divergence Detection - Catch reversals earlier

    Modification: Track BX vs price divergences for enhanced entry/exit signals

    Divergence Types:
    - Bullish: Price makes lower low, BX makes higher low (momentum improving)
    - Bearish: Price makes higher high, BX makes lower high (momentum weakening)

    Entry:
    - Standard: BX crosses above 0
    - Enhanced: Bullish divergence detected + BX > -30

    Exit:
    - Standard: BX crosses below 0
    - Enhanced: Bearish divergence detected + BX < 30

    Hypothesis: Divergences predict reversals before zero-cross,
                allowing earlier entries and protecting gains
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.ticker = "TSLA"
        self.symbol = self.add_equity(self.ticker, Resolution.DAILY).symbol

        # BX params
        self.l1, self.l2, self.l3 = 5, 20, 15

        # Divergence lookback
        self.lookback = 20  # Bars to look for divergence

        # Indicators
        self.ema_fast = self.ema(self.symbol, self.l1, Resolution.DAILY)
        self.ema_slow = self.ema(self.symbol, self.l2, Resolution.DAILY)

        # Rolling windows
        self.diff_window = RollingWindow[float](self.l3 + 1)
        self.bx_window = RollingWindow[float](self.lookback)
        self.close_window = RollingWindow[float](self.lookback)

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

    def find_local_extrema(self, values, window=5):
        """
        Find local highs and lows in a series.
        Returns (highs, lows) as lists of (index, value) tuples.
        """
        highs = []
        lows = []

        if len(values) < window * 2 + 1:
            return highs, lows

        for i in range(window, len(values) - window):
            is_high = all(values[i] >= values[j] for j in range(i - window, i + window + 1))
            is_low = all(values[i] <= values[j] for j in range(i - window, i + window + 1))

            if is_high:
                highs.append((i, values[i]))
            if is_low:
                lows.append((i, values[i]))

        return highs, lows

    def detect_bullish_divergence(self):
        """
        Bullish divergence: Price lower low, BX higher low
        """
        if self.close_window.count < self.lookback or self.bx_window.count < self.lookback:
            return False

        prices = [self.close_window[i] for i in range(self.close_window.count)]
        prices.reverse()
        bx_vals = [self.bx_window[i] for i in range(self.bx_window.count)]
        bx_vals.reverse()

        _, price_lows = self.find_local_extrema(prices, window=3)
        _, bx_lows = self.find_local_extrema(bx_vals, window=3)

        # Need at least 2 lows to compare
        if len(price_lows) < 2 or len(bx_lows) < 2:
            return False

        # Compare most recent two lows
        # Price: lower low (recent < previous)
        # BX: higher low (recent > previous)
        price_lower = price_lows[-1][1] < price_lows[-2][1]
        bx_higher = bx_lows[-1][1] > bx_lows[-2][1]

        return price_lower and bx_higher

    def detect_bearish_divergence(self):
        """
        Bearish divergence: Price higher high, BX lower high
        """
        if self.close_window.count < self.lookback or self.bx_window.count < self.lookback:
            return False

        prices = [self.close_window[i] for i in range(self.close_window.count)]
        prices.reverse()
        bx_vals = [self.bx_window[i] for i in range(self.bx_window.count)]
        bx_vals.reverse()

        price_highs, _ = self.find_local_extrema(prices, window=3)
        bx_highs, _ = self.find_local_extrema(bx_vals, window=3)

        # Need at least 2 highs to compare
        if len(price_highs) < 2 or len(bx_highs) < 2:
            return False

        # Price: higher high (recent > previous)
        # BX: lower high (recent < previous)
        price_higher = price_highs[-1][1] > price_highs[-2][1]
        bx_lower = bx_highs[-1][1] < bx_highs[-2][1]

        return price_higher and bx_lower

    def on_data(self, data):
        if self.is_warming_up or self.symbol not in data:
            return
        if data[self.symbol] is None:
            return
        if not self.ema_fast.is_ready or not self.ema_slow.is_ready:
            return

        close = data[self.symbol].close
        self.close_window.add(close)

        ema_diff = self.ema_fast.current.value - self.ema_slow.current.value
        self.diff_window.add(ema_diff)

        if not self.diff_window.is_ready:
            return

        diff_vals = [self.diff_window[i] for i in range(self.diff_window.count)]
        diff_vals.reverse()

        rsi = self.calc_rsi(diff_vals, self.l3)
        if rsi is None:
            return

        self.bx = rsi - 50
        self.bx_window.add(self.bx)

        if self.prev_bx is not None:
            # Standard zero-cross signals
            turned_bullish = self.prev_bx < 0 and self.bx >= 0
            turned_bearish = self.prev_bx >= 0 and self.bx < 0

            # Divergence-enhanced signals
            bullish_div = self.detect_bullish_divergence()
            bearish_div = self.detect_bearish_divergence()

            # Entry logic: standard OR (bullish divergence with BX > -30)
            should_buy = turned_bullish or (bullish_div and self.bx > -30 and not self.portfolio[self.symbol].invested)

            # Exit logic: standard OR (bearish divergence with BX < 30)
            should_sell = turned_bearish or (bearish_div and self.bx < 30 and self.portfolio[self.symbol].invested)

            if should_buy and not self.portfolio[self.symbol].invested:
                self.set_holdings(self.symbol, 1.0)
                signal_type = "DIVERGENCE" if bullish_div else "CROSSOVER"
                self.debug(f"{self.time}: BUY {self.ticker} [{signal_type}] - BX: {self.bx:.1f}")

            elif should_sell and self.portfolio[self.symbol].invested:
                signal_type = "DIVERGENCE" if bearish_div else "CROSSOVER"
                self.liquidate(self.symbol)
                self.debug(f"{self.time}: SELL {self.ticker} [{signal_type}] - BX: {self.bx:.1f}")

        self.prev_bx = self.bx

    def on_end_of_algorithm(self):
        self.log(f"BX-Divergence Final: ${self.portfolio.total_portfolio_value:,.2f}")
