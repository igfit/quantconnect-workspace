"""
High-Beta Small/Mid Cap v6 - DUAL MOMENTUM + QQQ REGIME

Key changes:
- QQQ regime filter (tech-heavy like our universe)
- Dual momentum: both absolute (mom > 0) AND relative (vs QQQ) must be positive
- Faster exit: 50 SMA regime (very responsive)
- Top 8 for concentration
"""

from AlgorithmImports import *


class HighBetaSmallMidV6(QCAlgorithm):

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
        self.top_n = 8
        self.min_dollar_volume = 5_000_000

        self.prev_short_mom = {}

        # Universe - 40 high-beta stocks
        self.universe_tickers = [
            # High-beta tech leaders
            "TSLA", "NVDA", "AMD", "SQ", "SHOP",
            # Semiconductors
            "MU", "MRVL", "ON", "SWKS", "QRVO",
            "AMAT", "LRCX", "KLAC", "ASML", "ENTG",
            # Software/Cloud
            "CRWD", "ZS", "OKTA", "TWLO", "NET",
            "MDB", "DOCU", "SPLK", "WDAY",
            # Fintech
            "PYPL",
            # Consumer
            "ETSY", "ROKU", "SNAP", "PINS", "TTD", "W",
            # Clean Energy
            "ENPH", "SEDG", "FSLR",
            # Travel
            "UBER", "LYFT", "EXPE",
            # Gaming
            "DKNG",
            # Biotech
            "MRNA", "VRTX", "REGN",
        ]

        # QQQ for regime filter (matches tech-heavy universe better)
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.qqq_sma_fast = self.sma(self.qqq, 50, Resolution.DAILY)  # FAST regime
        self.qqq_mom = self.roc(self.qqq, self.lookback_days, Resolution.DAILY)

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

        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("QQQ", 30),
            self.rebalance
        )
        self.set_benchmark("QQQ")

    def rebalance(self):
        if self.is_warming_up:
            return

        # FAST QQQ regime filter (50 SMA)
        if not self.qqq_sma_fast.is_ready:
            return
        if self.securities[self.qqq].price < self.qqq_sma_fast.current.value:
            self.liquidate()
            return

        # Additional: QQQ absolute momentum must be positive
        if self.qqq_mom.is_ready and self.qqq_mom.current.value < 0:
            self.liquidate()
            return

        qqq_mom = self.qqq_mom.current.value if self.qqq_mom.is_ready else 0

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

            # DUAL MOMENTUM: absolute AND relative
            # Stock must beat QQQ AND have positive momentum
            relative_mom = mom - qqq_mom
            if mom > 0 and relative_mom > 0:
                accel_bonus = 1.3 if acceleration > 0 else 1.0
                scores[symbol] = relative_mom * accel_bonus

        if len(scores) < 3:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        total_score = sum(scores[s] for s in top_symbols)
        weights = {s: scores[s] / total_score for s in top_symbols}

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])
