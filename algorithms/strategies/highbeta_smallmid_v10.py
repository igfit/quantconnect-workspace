"""
High-Beta Small/Mid Cap v10 - MONTHLY REBALANCE

Changes:
- Monthly rebalance (less whipsaw)
- Patient regime: 200 SMA (avoid false exits)
- 1.3x leverage when strong
- Top 6 concentrated
"""

from AlgorithmImports import *


class HighBetaSmallMidV10(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Parameters
        self.lookback_days = 126
        self.accel_period = 21
        self.top_n = 6
        self.max_leverage = 1.3
        self.min_dollar_volume = 5_000_000

        self.prev_short_mom = {}

        # Universe - 32 high-beta stocks
        self.universe_tickers = [
            "TSLA", "NVDA", "AMD",
            "MU", "MRVL", "ON", "SWKS", "AMAT", "LRCX", "KLAC",
            "CRWD", "ZS", "OKTA", "TWLO", "NET", "MDB",
            "SQ", "PYPL",
            "SHOP", "ETSY", "ROKU", "SNAP", "PINS", "TTD",
            "ENPH", "SEDG", "FSLR",
            "UBER", "EXPE",
            "MRNA", "VRTX", "REGN",
        ]

        # PATIENT regime: 200 SMA
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.qqq_sma_50 = self.sma(self.qqq, 50, Resolution.DAILY)
        self.qqq_sma_200 = self.sma(self.qqq, 200, Resolution.DAILY)
        self.qqq_mom = self.roc(self.qqq, 63, Resolution.DAILY)

        self.symbols = []
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                self.symbols.append(equity.symbol)
            except:
                pass

        self.log(f"Universe size: {len(self.symbols)} stocks")

        self.momentum = {}
        self.short_mom = {}
        self.volume_sma = {}
        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
            self.short_mom[symbol] = self.roc(symbol, self.accel_period, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        self.set_warm_up(max(self.lookback_days, 200) + 10, Resolution.DAILY)

        # MONTHLY rebalance
        self.schedule.on(
            self.date_rules.month_start("QQQ"),
            self.time_rules.after_market_open("QQQ", 30),
            self.rebalance
        )
        self.set_benchmark("QQQ")

    def rebalance(self):
        if self.is_warming_up:
            return

        qqq_price = self.securities[self.qqq].price

        if not self.qqq_sma_200.is_ready:
            return

        above_200 = qqq_price > self.qqq_sma_200.current.value
        above_50 = self.qqq_sma_50.is_ready and qqq_price > self.qqq_sma_50.current.value
        qqq_mom_positive = self.qqq_mom.is_ready and self.qqq_mom.current.value > 0

        # Exit only if below 200 SMA (patient)
        if not above_200:
            self.liquidate()
            return

        # Leverage based on regime strength
        if above_200 and above_50 and qqq_mom_positive:
            leverage = self.max_leverage
        elif above_200 and above_50:
            leverage = 1.1
        else:
            leverage = 1.0

        scores = {}

        for symbol in self.symbols:
            if not self.momentum[symbol].is_ready:
                continue
            if not self.short_mom[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue
            if self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue

            mom = self.momentum[symbol].current.value
            short_mom = self.short_mom[symbol].current.value
            prev_mom = self.prev_short_mom.get(symbol, 0)
            acceleration = short_mom - prev_mom
            self.prev_short_mom[symbol] = short_mom

            if mom > 0:
                accel_bonus = 1.5 if acceleration > 0 else 1.0
                scores[symbol] = mom * accel_bonus

        if len(scores) < 3:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        total_score = sum(scores[s] for s in top_symbols)
        weights = {s: (scores[s] / total_score) * leverage for s in top_symbols}

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])
