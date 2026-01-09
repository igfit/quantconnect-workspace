"""
High-Beta Small/Mid Cap v7 - AGGRESSIVE MOMENTUM

Key changes:
- Include TSLA/NVDA (high beta behavior despite size)
- 1.5x leverage when regime is strong
- Ultra-tight regime: QQQ > 20 SMA AND > 50 SMA
- Top 5 very concentrated
- Weekly momentum check (faster exits on weakness)
"""

from AlgorithmImports import *


class HighBetaSmallMidV7(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Parameters - AGGRESSIVE
        self.lookback_days = 126
        self.accel_period = 21
        self.top_n = 5            # Very concentrated
        self.max_leverage = 1.5   # 1.5x when regime is strong
        self.min_dollar_volume = 5_000_000

        self.prev_short_mom = {}

        # Universe - High-beta stocks including momentum leaders
        self.universe_tickers = [
            # MUST HAVE: proven momentum leaders with high beta
            "TSLA", "NVDA", "AMD",

            # Semiconductors
            "MU", "MRVL", "ON", "SWKS", "AMAT", "LRCX", "KLAC",

            # Software/Cloud (high growth)
            "CRWD", "ZS", "OKTA", "TWLO", "NET", "MDB",

            # Fintech
            "SQ", "PYPL",

            # Consumer (high beta)
            "SHOP", "ETSY", "ROKU", "SNAP", "PINS", "TTD",

            # Clean Energy
            "ENPH", "SEDG", "FSLR",

            # Travel
            "UBER", "EXPE",

            # Biotech
            "MRNA", "VRTX", "REGN",
        ]

        # QQQ regime with multiple timeframes
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.qqq_sma_20 = self.sma(self.qqq, 20, Resolution.DAILY)
        self.qqq_sma_50 = self.sma(self.qqq, 50, Resolution.DAILY)
        self.qqq_mom = self.roc(self.qqq, 63, Resolution.DAILY)  # 3-month QQQ momentum

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

        qqq_price = self.securities[self.qqq].price

        # Check regime strength
        if not self.qqq_sma_20.is_ready or not self.qqq_sma_50.is_ready:
            return

        above_20 = qqq_price > self.qqq_sma_20.current.value
        above_50 = qqq_price > self.qqq_sma_50.current.value
        qqq_mom_positive = self.qqq_mom.is_ready and self.qqq_mom.current.value > 0

        # Exit if below both SMAs (clear downtrend)
        if not above_20 and not above_50:
            self.liquidate()
            return

        # Determine leverage based on regime strength
        if above_20 and above_50 and qqq_mom_positive:
            leverage = self.max_leverage  # Strong regime: 1.5x
        elif above_50:
            leverage = 1.0  # Normal regime
        else:
            leverage = 0.5  # Weak regime: reduce exposure

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
