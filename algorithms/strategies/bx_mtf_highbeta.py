from AlgorithmImports import *
import numpy as np


class BXMTFHighBeta(QCAlgorithm):
    """
    BX Multi-Timeframe on High-Beta Stocks Portfolio

    Tests: TSLA, NVDA, AMD, COIN, RBLX
    Uses Daily + Weekly BX alignment for entry
    """

    def initialize(self):
        self.set_start_date(2021, 1, 1)  # Start 2021 for COIN/RBLX availability
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        # High-beta stocks to test
        self.tickers = ["TSLA", "NVDA", "AMD", "COIN"]

        # BX params
        self.short_l1, self.short_l2, self.short_l3 = 5, 20, 15

        # Storage for each symbol
        self.symbols = {}
        self.daily_ema_fast = {}
        self.daily_ema_slow = {}
        self.daily_ema_diff_window = {}
        self.weekly_bars = {}
        self.daily_bx = {}
        self.weekly_bx = {}
        self.prev_daily_bx = {}

        for ticker in self.tickers:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol

            self.daily_ema_fast[symbol] = self.ema(symbol, self.short_l1, Resolution.DAILY)
            self.daily_ema_slow[symbol] = self.ema(symbol, self.short_l2, Resolution.DAILY)
            self.daily_ema_diff_window[symbol] = RollingWindow[float](self.short_l3 + 1)

            self.weekly_bars[symbol] = RollingWindow[TradeBar](25)
            self.consolidate(symbol, Calendar.Weekly, lambda bar, s=symbol: self.on_weekly_bar(bar, s))

            self.daily_bx[symbol] = None
            self.weekly_bx[symbol] = None
            self.prev_daily_bx[symbol] = None

        self.set_warm_up(300, Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_weekly_bar(self, bar, symbol):
        self.weekly_bars[symbol].add(bar)
        if self.weekly_bars[symbol].count >= 25:
            closes = [self.weekly_bars[symbol][i].close for i in range(min(self.weekly_bars[symbol].count, 25))]
            closes.reverse()
            self.weekly_bx[symbol] = self.calculate_bx(closes)

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
        if self.is_warming_up:
            return

        for ticker, symbol in self.symbols.items():
            if symbol not in data or data[symbol] is None:
                continue
            if not self.daily_ema_fast[symbol].is_ready or not self.daily_ema_slow[symbol].is_ready:
                continue

            # Calculate daily BX
            ema_diff = self.daily_ema_fast[symbol].current.value - self.daily_ema_slow[symbol].current.value
            self.daily_ema_diff_window[symbol].add(ema_diff)

            if not self.daily_ema_diff_window[symbol].is_ready:
                continue

            diff_vals = [self.daily_ema_diff_window[symbol][i] for i in range(self.daily_ema_diff_window[symbol].count)]
            diff_vals.reverse()
            rsi = self.calc_rsi(diff_vals, self.short_l3)

            if rsi is None:
                continue

            self.daily_bx[symbol] = rsi - 50

            daily_bullish = self.daily_bx[symbol] >= 0
            weekly_bullish = self.weekly_bx[symbol] is not None and self.weekly_bx[symbol] >= 0

            if self.prev_daily_bx[symbol] is not None:
                turned_bullish = self.prev_daily_bx[symbol] < 0 and self.daily_bx[symbol] >= 0
                turned_bearish = self.prev_daily_bx[symbol] >= 0 and self.daily_bx[symbol] < 0

                # Equal weight allocation (25% per stock when all 4 are active)
                weight = 1.0 / len(self.tickers)

                if turned_bullish and daily_bullish and weekly_bullish:
                    if not self.portfolio[symbol].invested:
                        self.set_holdings(symbol, weight)
                        self.debug(f"{self.time}: BUY {ticker} - Daily: {self.daily_bx[symbol]:.1f}, Weekly: {self.weekly_bx[symbol]:.1f}")

                elif turned_bearish and self.portfolio[symbol].invested:
                    self.liquidate(symbol)
                    self.debug(f"{self.time}: SELL {ticker}")

            self.prev_daily_bx[symbol] = self.daily_bx[symbol]

    def on_end_of_algorithm(self):
        self.log(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
