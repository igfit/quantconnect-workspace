from AlgorithmImports import *
import numpy as np


class BXMultiTimeframeStrategy(QCAlgorithm):
    """
    Multi-Timeframe BX Trender Strategy

    Strategy:
        - Calculate BX Trender on Daily, Weekly, and Monthly timeframes
        - Enter when Daily BX turns bullish AND higher timeframes confirm
        - Exit when Daily BX turns bearish

    Modes:
        - "daily_only": Just daily BX (baseline)
        - "daily_weekly": Daily + Weekly must be bullish
        - "daily_monthly": Daily + Monthly must be bullish
        - "all_aligned": Daily + Weekly + Monthly must be bullish

    Universe: Configurable single stock
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        # Configuration - change these to test different stocks/modes
        self.ticker = self.get_parameter("ticker", "TSLA")
        self.mode = self.get_parameter("mode", "daily_weekly")  # daily_only, daily_weekly, daily_monthly, all_aligned

        # Add equity
        self.symbol = self.add_equity(self.ticker, Resolution.DAILY).symbol

        # BX Trender parameters
        self.short_l1 = 5
        self.short_l2 = 20
        self.short_l3 = 15

        # Daily EMAs
        self.daily_ema_fast = self.ema(self.symbol, self.short_l1, Resolution.DAILY)
        self.daily_ema_slow = self.ema(self.symbol, self.short_l2, Resolution.DAILY)
        self.daily_ema_diff_window = RollingWindow[float](self.short_l3 + 1)

        # Weekly data consolidation
        self.weekly_bars = RollingWindow[TradeBar](25)
        self.consolidate(self.symbol, Resolution.DAILY, CalendarType.WEEK, self.on_weekly_bar)

        # Monthly data consolidation
        self.monthly_bars = RollingWindow[TradeBar](15)
        self.consolidate(self.symbol, Resolution.DAILY, CalendarType.MONTH, self.on_monthly_bar)

        # BX values for each timeframe
        self.daily_bx = None
        self.weekly_bx = None
        self.monthly_bx = None
        self.prev_daily_bx = None

        # Warm up
        self.set_warm_up(300, Resolution.DAILY)

        # Set benchmark
        self.set_benchmark("SPY")

    def on_weekly_bar(self, bar):
        """Called when a weekly bar is completed"""
        self.weekly_bars.add(bar)
        if self.weekly_bars.count >= 25:
            self.weekly_bx = self.calculate_bx_from_bars(self.weekly_bars)

    def on_monthly_bar(self, bar):
        """Called when a monthly bar is completed"""
        self.monthly_bars.add(bar)
        if self.monthly_bars.count >= 15:
            self.monthly_bx = self.calculate_bx_from_bars(self.monthly_bars)

    def calculate_bx_from_bars(self, bars):
        """Calculate BX Trender from a rolling window of bars"""
        if bars.count < 25:
            return None

        # Get closes
        closes = [bars[i].close for i in range(min(bars.count, 25))]
        closes.reverse()

        # Calculate EMAs
        ema_fast = self.calc_ema(closes, self.short_l1)
        ema_slow = self.calc_ema(closes, self.short_l2)

        if ema_fast is None or ema_slow is None:
            return None

        # Calculate EMA differences for RSI
        ema_diffs = []
        for i in range(len(closes) - max(self.short_l1, self.short_l2)):
            fast = self.calc_ema(closes[:self.short_l1 + i + 1], self.short_l1)
            slow = self.calc_ema(closes[:self.short_l2 + i + 1], self.short_l2)
            if fast and slow:
                ema_diffs.append(fast - slow)

        if len(ema_diffs) < self.short_l3 + 1:
            return None

        # Calculate RSI on EMA differences
        rsi = self.calc_rsi(ema_diffs[-self.short_l3-1:], self.short_l3)
        if rsi is None:
            return None

        return rsi - 50

    def calc_ema(self, values, period):
        """Calculate EMA"""
        if len(values) < period:
            return None
        multiplier = 2 / (period + 1)
        ema = values[0]
        for val in values[1:]:
            ema = (val - ema) * multiplier + ema
        return ema

    def calc_rsi(self, values, period):
        """Calculate RSI"""
        if len(values) < period + 1:
            return None

        changes = [values[i] - values[i-1] for i in range(1, len(values))]
        gains = [c if c > 0 else 0 for c in changes[-period:]]
        losses = [-c if c < 0 else 0 for c in changes[-period:]]

        avg_gain = np.mean(gains) if gains else 0
        avg_loss = np.mean(losses) if losses else 0

        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def on_data(self, data):
        if self.is_warming_up:
            return

        if self.symbol not in data or data[self.symbol] is None:
            return

        if not self.daily_ema_fast.is_ready or not self.daily_ema_slow.is_ready:
            return

        # Calculate Daily BX
        ema_diff = self.daily_ema_fast.current.value - self.daily_ema_slow.current.value
        self.daily_ema_diff_window.add(ema_diff)

        if not self.daily_ema_diff_window.is_ready:
            return

        rsi = self.calc_rsi(
            [self.daily_ema_diff_window[i] for i in range(self.daily_ema_diff_window.count)][::-1],
            self.short_l3
        )
        if rsi is None:
            return

        self.daily_bx = rsi - 50

        # Check conditions based on mode
        daily_bullish = self.daily_bx >= 0
        weekly_bullish = self.weekly_bx is not None and self.weekly_bx >= 0
        monthly_bullish = self.monthly_bx is not None and self.monthly_bx >= 0

        # Determine if we should be in the market
        should_be_long = False

        if self.mode == "daily_only":
            should_be_long = daily_bullish
        elif self.mode == "daily_weekly":
            should_be_long = daily_bullish and weekly_bullish
        elif self.mode == "daily_monthly":
            should_be_long = daily_bullish and monthly_bullish
        elif self.mode == "all_aligned":
            should_be_long = daily_bullish and weekly_bullish and monthly_bullish

        # Trading logic
        if self.prev_daily_bx is not None:
            daily_just_turned_bullish = self.prev_daily_bx < 0 and self.daily_bx >= 0
            daily_just_turned_bearish = self.prev_daily_bx >= 0 and self.daily_bx < 0

            # Enter on daily bullish turn when higher timeframes confirm
            if daily_just_turned_bullish and should_be_long:
                if not self.portfolio[self.symbol].invested:
                    self.set_holdings(self.symbol, 1.0)
                    self.debug(f"{self.time}: BUY {self.ticker} - Daily BX: {self.daily_bx:.1f}, Weekly: {self.weekly_bx}, Monthly: {self.monthly_bx}")

            # Exit on daily bearish turn
            elif daily_just_turned_bearish:
                if self.portfolio[self.symbol].invested:
                    self.liquidate(self.symbol)
                    self.debug(f"{self.time}: SELL {self.ticker} - Daily BX turned bearish")

        self.prev_daily_bx = self.daily_bx

    def on_end_of_algorithm(self):
        self.log(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
        self.log(f"Mode: {self.mode}, Ticker: {self.ticker}")
