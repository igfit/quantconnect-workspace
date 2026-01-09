"""
Parameter Variation #3: Momentum + BX Filter (No Cross)

Same concept as EWO filter but with BX Trender.
BX > 0 as filter instead of requiring cross.

Also trying BX > 10 threshold for stronger signals.
"""

from AlgorithmImports import *
import numpy as np


class MomentumBXFilter(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # BX params
        self.bx_l1 = 5
        self.bx_l2 = 20
        self.bx_l3 = 15
        self.bx_threshold = 5  # Require BX > 5 for entry

        # Momentum
        self.mom_period = 126
        self.top_n = 10

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

        self.ema_fast = {}
        self.ema_slow = {}
        self.ema_diff_window = {}
        self.momentum = {}

        for symbol in self.symbols:
            self.ema_fast[symbol] = self.ema(symbol, self.bx_l1, Resolution.DAILY)
            self.ema_slow[symbol] = self.ema(symbol, self.bx_l2, Resolution.DAILY)
            self.ema_diff_window[symbol] = RollingWindow[float](self.bx_l3 + 2)
            self.momentum[symbol] = self.roc(symbol, self.mom_period, Resolution.DAILY)

        self.set_warm_up(self.mom_period + 20, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
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

    def get_bx(self, symbol):
        if not self.ema_fast[symbol].is_ready or not self.ema_slow[symbol].is_ready:
            return None

        ema_diff = self.ema_fast[symbol].current.value - self.ema_slow[symbol].current.value
        self.ema_diff_window[symbol].add(ema_diff)

        if not self.ema_diff_window[symbol].is_ready:
            return None

        values = [self.ema_diff_window[symbol][i] for i in range(self.ema_diff_window[symbol].count)][::-1]
        rsi = self.calc_rsi(values, self.bx_l3)
        return (rsi - 50) if rsi else None

    def rebalance(self):
        if self.is_warming_up:
            return

        if not self.spy_sma.is_ready:
            return
        if self.securities[self.spy].price < self.spy_sma.current.value:
            self.liquidate()
            return

        scores = {}

        for symbol in self.symbols:
            if not self.momentum[symbol].is_ready:
                continue

            bx = self.get_bx(symbol)
            if bx is None:
                continue

            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue

            mom = self.momentum[symbol].current.value

            # Momentum > 0 AND BX > threshold
            if mom > 0 and bx > self.bx_threshold:
                # BX bonus for stronger signals
                bx_bonus = 1.0 + (bx / 50)  # BX ranges -50 to 50
                scores[symbol] = mom * bx_bonus

        if len(scores) < 5:
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
