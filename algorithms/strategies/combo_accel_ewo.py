"""
Parameter Variation #4: Acceleration Entry + EWO Filter

Uses the winning Acceleration Entry signal from Round 3:
- Entry: 1-month ROC > previous 1-month ROC (momentum accelerating)
- Filter: EWO > 0 (trend confirmation)

This combines the best momentum signal with EWO as confirmation.
"""

from AlgorithmImports import *


class AccelEWOStrategy(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Momentum params (same as winning strategy)
        self.lookback = 126  # 6 months
        self.accel_period = 21  # 1 month

        # EWO params
        self.ewo_fast = 5
        self.ewo_slow = 34

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

        self.momentum = {}
        self.accel = {}
        self.sma_fast = {}
        self.sma_slow = {}
        self.prev_accel = {}

        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback, Resolution.DAILY)
            self.accel[symbol] = self.roc(symbol, self.accel_period, Resolution.DAILY)
            self.sma_fast[symbol] = self.sma(symbol, self.ewo_fast, Resolution.DAILY)
            self.sma_slow[symbol] = self.sma(symbol, self.ewo_slow, Resolution.DAILY)
            self.prev_accel[symbol] = None

        self.set_warm_up(self.lookback + 10, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        self.set_benchmark("SPY")

    def get_ewo(self, symbol):
        if not self.sma_fast[symbol].is_ready or not self.sma_slow[symbol].is_ready:
            return None
        return self.sma_fast[symbol].current.value - self.sma_slow[symbol].current.value

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
            if not self.accel[symbol].is_ready:
                continue

            ewo = self.get_ewo(symbol)
            if ewo is None:
                continue

            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue

            mom = self.momentum[symbol].current.value
            accel = self.accel[symbol].current.value
            prev = self.prev_accel.get(symbol)

            # Core signal: Positive momentum AND accelerating
            # Filter: EWO must be positive
            if mom > 0 and ewo > 0:
                # Acceleration bonus (key signal from Round 3)
                accel_bonus = 1.5 if (prev is not None and accel > prev) else 1.0
                scores[symbol] = mom * accel_bonus

            self.prev_accel[symbol] = accel

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
