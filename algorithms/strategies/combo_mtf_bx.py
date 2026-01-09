"""
Creative Combo #4: Multi-Timeframe BX (Weekly + Daily)

Use weekly BX as trend filter, daily BX for entry signals.

Weekly BX: Determines trend direction (only trade if weekly BX > 0)
Daily BX: Entry/exit signals

Entry: Weekly BX > 0 AND Daily BX crosses above 0
Exit: Daily BX < 0 OR Weekly BX turns negative

Hypothesis: Weekly filter reduces whipsaws by only trading
in the direction of the larger trend.
"""

from AlgorithmImports import *
import numpy as np


class MTFBXStrategy(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # BX parameters
        self.bx_l1 = 5
        self.bx_l2 = 20
        self.bx_l3 = 15

        self.top_n = 10
        self.use_regime_filter = True

        # NO TOP3 UNIVERSE
        self.universe_tickers = [
            "AMD", "AVGO", "QCOM", "MU", "AMAT", "LRCX", "KLAC", "MRVL", "ON",
            "TXN", "ADI", "SNPS", "CDNS", "ASML",
            "CRM", "ADBE", "NOW", "INTU", "PANW", "VEEV", "WDAY",
            "V", "MA", "PYPL", "SQ",
            "AMZN", "SHOP",
            "BKNG", "RCL", "CCL", "MAR", "HLT", "WYNN",
            "XOM", "CVX", "OXY", "DVN", "SLB", "COP",
            "CAT", "DE", "URI", "BA",
            "NKE", "LULU", "CMG", "DECK",
            "GS", "MS",
            "NFLX", "ROKU",
        ]

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        self.symbols = []
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                self.symbols.append(equity.symbol)
            except:
                pass

        # Daily BX components
        self.daily_ema_fast = {}
        self.daily_ema_slow = {}
        self.daily_diff_window = {}
        self.daily_bx = {}
        self.prev_daily_bx = {}

        # Weekly close tracking for weekly BX
        self.weekly_closes = {}
        self.weekly_bx = {}

        for symbol in self.symbols:
            self.daily_ema_fast[symbol] = self.ema(symbol, self.bx_l1, Resolution.DAILY)
            self.daily_ema_slow[symbol] = self.ema(symbol, self.bx_l2, Resolution.DAILY)
            self.daily_diff_window[symbol] = RollingWindow[float](self.bx_l3 + 2)
            self.daily_bx[symbol] = None
            self.prev_daily_bx[symbol] = None
            self.weekly_closes[symbol] = RollingWindow[float](50)  # For weekly BX
            self.weekly_bx[symbol] = None

        self.set_warm_up(100, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        # Update weekly closes at end of week
        self.schedule.on(
            self.date_rules.every(DayOfWeek.FRIDAY),
            self.time_rules.before_market_close("SPY", 10),
            self.update_weekly
        )

        self.set_benchmark("SPY")

    def calc_rsi(self, values, period):
        """Calculate RSI from a list of values"""
        if len(values) < period + 1:
            return None
        changes = [values[i] - values[i-1] for i in range(1, len(values))]
        gains = [c if c > 0 else 0 for c in changes[-period:]]
        losses = [-c if c < 0 else 0 for c in changes[-period:]]
        avg_gain, avg_loss = np.mean(gains), np.mean(losses)
        if avg_loss == 0:
            return 100
        return 100 - (100 / (1 + avg_gain / avg_loss))

    def calc_ema(self, values, period):
        """Simple EMA calculation"""
        if len(values) < period:
            return None
        multiplier = 2 / (period + 1)
        ema = sum(values[:period]) / period
        for val in values[period:]:
            ema = (val - ema) * multiplier + ema
        return ema

    def get_daily_bx(self, symbol):
        """Calculate daily BX"""
        if not self.daily_ema_fast[symbol].is_ready or not self.daily_ema_slow[symbol].is_ready:
            return None

        ema_diff = self.daily_ema_fast[symbol].current.value - self.daily_ema_slow[symbol].current.value
        self.daily_diff_window[symbol].add(ema_diff)

        if not self.daily_diff_window[symbol].is_ready:
            return None

        values = [self.daily_diff_window[symbol][i] for i in range(self.daily_diff_window[symbol].count)][::-1]
        rsi = self.calc_rsi(values, self.bx_l3)
        return (rsi - 50) if rsi else None

    def update_weekly(self):
        """Update weekly closes and calculate weekly BX"""
        for symbol in self.symbols:
            if not self.securities[symbol].has_data:
                continue
            self.weekly_closes[symbol].add(self.securities[symbol].price)

            # Calculate weekly BX from weekly closes
            if self.weekly_closes[symbol].count >= self.bx_l2 + self.bx_l3 + 1:
                closes = [self.weekly_closes[symbol][i] for i in range(min(50, self.weekly_closes[symbol].count))][::-1]

                # Calculate EMAs on weekly data
                ema_fast = self.calc_ema(closes, self.bx_l1)
                ema_slow = self.calc_ema(closes, self.bx_l2)

                if ema_fast and ema_slow:
                    # Build EMA diff series for RSI
                    ema_diffs = []
                    for i in range(self.bx_l2, len(closes)):
                        f = self.calc_ema(closes[:i+1], self.bx_l1)
                        s = self.calc_ema(closes[:i+1], self.bx_l2)
                        if f and s:
                            ema_diffs.append(f - s)

                    if len(ema_diffs) >= self.bx_l3 + 1:
                        rsi = self.calc_rsi(ema_diffs, self.bx_l3)
                        self.weekly_bx[symbol] = (rsi - 50) if rsi else None

    def rebalance(self):
        if self.is_warming_up:
            return

        # Regime filter
        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                return

        scores = {}

        for symbol in self.symbols:
            daily_bx = self.get_daily_bx(symbol)
            weekly_bx = self.weekly_bx.get(symbol)
            prev_daily = self.prev_daily_bx.get(symbol)

            if daily_bx is None or weekly_bx is None:
                if daily_bx is not None:
                    self.prev_daily_bx[symbol] = daily_bx
                continue

            if not self.securities[symbol].has_data:
                self.prev_daily_bx[symbol] = daily_bx
                continue

            price = self.securities[symbol].price
            if price < 5:
                self.prev_daily_bx[symbol] = daily_bx
                continue

            # Entry: Weekly BX > 0 (uptrend) AND Daily BX > 0
            if weekly_bx > 0 and daily_bx > 0:
                # Bonus for daily crossing bullish
                cross_bonus = 1.5 if (prev_daily is not None and prev_daily < 0) else 1.0
                # Score by combined BX strength
                scores[symbol] = (daily_bx + weekly_bx) * cross_bonus

            self.prev_daily_bx[symbol] = daily_bx

        # Exit conditions
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.symbols:
                daily_bx = self.get_daily_bx(holding.symbol)
                weekly_bx = self.weekly_bx.get(holding.symbol)

                if daily_bx is not None:
                    # Exit if daily BX negative OR weekly turned bearish
                    if daily_bx < 0:
                        self.liquidate(holding.symbol)
                    elif weekly_bx is not None and weekly_bx < 0:
                        self.liquidate(holding.symbol)

        if len(scores) < 3:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        weight = 1.0 / actual_n

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols and holding.symbol != self.spy:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weight)
