from AlgorithmImports import *
import numpy as np


class BXTrenderStrategy(QCAlgorithm):
    """
    BX Trender Strategy

    Strategy:
        - Go long when BX Trender turns from red to green (bearish to bullish)
        - Exit when BX Trender turns from green to red (bullish to bearish)

    Based on Bharat Jhunjhunwala's indicator from IFTA Journal.

    Parameters:
        - short_l1: 5 (fast EMA for short-term)
        - short_l2: 20 (slow EMA for short-term)
        - short_l3: 15 (RSI period for short-term)
        - long_l1: 20 (EMA for long-term)
        - long_l2: 15 (RSI period for long-term)

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
        self.long_l1 = 20
        self.long_l2 = 15

        # Create EMAs for BX Trender calculation
        self.ema_fast = self.ema(self.symbol, self.short_l1, Resolution.DAILY)
        self.ema_slow = self.ema(self.symbol, self.short_l2, Resolution.DAILY)
        self.ema_long = self.ema(self.symbol, self.long_l1, Resolution.DAILY)

        # Rolling windows for manual RSI calculation on EMA differences
        self.ema_diff_window = RollingWindow[float](self.short_l3 + 1)
        self.ema_long_window = RollingWindow[float](self.long_l2 + 1)

        # Store previous BX Trender values for crossover detection
        self.prev_short_xt = None
        self.prev_long_xt = None

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

    def on_data(self, data):
        if self.is_warming_up:
            return

        if not self.ema_fast.is_ready or not self.ema_slow.is_ready or not self.ema_long.is_ready:
            return

        # Calculate EMA difference for short-term component
        ema_diff = self.ema_fast.current.value - self.ema_slow.current.value
        self.ema_diff_window.add(ema_diff)

        # Store long EMA value
        self.ema_long_window.add(self.ema_long.current.value)

        if not self.ema_diff_window.is_ready or not self.ema_long_window.is_ready:
            return

        # Calculate short-term X-Trender: RSI(EMA_diff, 15) - 50
        short_rsi = self.calculate_rsi(
            [self.ema_diff_window[i] for i in range(self.ema_diff_window.count)],
            self.short_l3
        )

        # Calculate long-term X-Trender: RSI(EMA_long, 15) - 50
        long_rsi = self.calculate_rsi(
            [self.ema_long_window[i] for i in range(self.ema_long_window.count)],
            self.long_l2
        )

        if short_rsi is None or long_rsi is None:
            return

        short_xt = short_rsi - 50
        long_xt = long_rsi - 50

        # Detect crossovers (signal changes)
        if self.prev_short_xt is not None:
            # Bullish signal: short-term crosses above zero (red to green)
            prev_bearish = self.prev_short_xt < 0
            curr_bullish = short_xt >= 0

            # Bearish signal: short-term crosses below zero (green to red)
            prev_bullish = self.prev_short_xt >= 0
            curr_bearish = short_xt < 0

            if prev_bearish and curr_bullish:
                if not self.portfolio[self.symbol].invested:
                    self.set_holdings(self.symbol, 1.0)
                    self.debug(f"{self.time}: BUY - BX Trender turned bullish (short_xt: {short_xt:.2f})")

            elif prev_bullish and curr_bearish:
                if self.portfolio[self.symbol].invested:
                    self.liquidate(self.symbol)
                    self.debug(f"{self.time}: SELL - BX Trender turned bearish (short_xt: {short_xt:.2f})")

        self.prev_short_xt = short_xt
        self.prev_long_xt = long_xt

    def on_end_of_algorithm(self):
        self.log(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
