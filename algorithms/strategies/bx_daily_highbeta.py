from AlgorithmImports import *
import numpy as np


class BXDailyHighBeta(QCAlgorithm):
    """
    BX Trender Daily-Only on High-Beta Portfolio

    Stocks: TSLA, NVDA, AMD, COIN
    Entry: Daily BX turns bullish
    Exit: Daily BX turns bearish
    Position: Equal weight allocation (25% each when all active)
    """

    def initialize(self):
        self.set_start_date(2021, 1, 1)  # Start 2021 for COIN availability
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        # High-beta stocks
        self.tickers = ["TSLA", "NVDA", "AMD", "COIN"]

        # BX params
        self.short_l1, self.short_l2, self.short_l3 = 5, 20, 15

        # Storage
        self.symbols = {}
        self.daily_ema_fast = {}
        self.daily_ema_slow = {}
        self.daily_ema_diff_window = {}
        self.daily_bx = {}
        self.prev_daily_bx = {}

        for ticker in self.tickers:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.daily_ema_fast[symbol] = self.ema(symbol, self.short_l1, Resolution.DAILY)
            self.daily_ema_slow[symbol] = self.ema(symbol, self.short_l2, Resolution.DAILY)
            self.daily_ema_diff_window[symbol] = RollingWindow[float](self.short_l3 + 1)
            self.daily_bx[symbol] = None
            self.prev_daily_bx[symbol] = None

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
        if self.is_warming_up:
            return

        for ticker, symbol in self.symbols.items():
            if symbol not in data or data[symbol] is None:
                continue
            if not self.daily_ema_fast[symbol].is_ready or not self.daily_ema_slow[symbol].is_ready:
                continue

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

            if self.prev_daily_bx[symbol] is not None:
                turned_bullish = self.prev_daily_bx[symbol] < 0 and self.daily_bx[symbol] >= 0
                turned_bearish = self.prev_daily_bx[symbol] >= 0 and self.daily_bx[symbol] < 0

                weight = 1.0 / len(self.tickers)  # 25% each

                if turned_bullish:
                    if not self.portfolio[symbol].invested:
                        self.set_holdings(symbol, weight)
                        self.debug(f"{self.time}: BUY {ticker} - BX: {self.daily_bx[symbol]:.1f}")

                elif turned_bearish and self.portfolio[symbol].invested:
                    self.liquidate(symbol)
                    self.debug(f"{self.time}: SELL {ticker} - BX: {self.daily_bx[symbol]:.1f}")

            self.prev_daily_bx[symbol] = self.daily_bx[symbol]

    def on_end_of_algorithm(self):
        self.log(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
