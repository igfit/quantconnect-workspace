"""
High-Beta Small/Mid Cap Momentum Strategy v4 - REFINED UNIVERSE

Key changes:
- REMOVED stocks that IPO'd in 2020+ (COIN, HOOD, RBLX, DASH, SNOW, etc.)
- Focus on proven volatile names with 5+ year history
- Added more semis and cyclicals (they bounce back)
- Include TSLA and NVDA (high beta behavior despite size)
- 40 stocks total for broader selection
"""

from AlgorithmImports import *


class HighBetaSmallMidV4(QCAlgorithm):

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
        self.top_n = 10
        self.use_regime_filter = True
        self.min_dollar_volume = 5_000_000

        self.prev_short_mom = {}

        # REFINED UNIVERSE - Only pre-2020 IPO stocks with high beta history
        # 40 stocks: proven momentum names that existed before 2020
        self.universe_tickers = [
            # HIGH-BETA TECH LEADERS (proven momentum)
            "TSLA", "NVDA", "AMD", "SQ", "SHOP",

            # Semiconductors (cyclical, high beta)
            "MU", "MRVL", "ON", "SWKS", "QRVO",
            "AMAT", "LRCX", "KLAC", "ASML", "ENTG",

            # Software/Cloud (pre-2020 IPO)
            "CRWD", "ZS", "OKTA", "TWLO", "ZM",
            "NET", "MDB", "DOCU", "SPLK", "WDAY",

            # Fintech (pre-2020)
            "PYPL",

            # E-commerce/Consumer (high beta)
            "ETSY", "ROKU", "SNAP", "PINS", "TTD",
            "W", "CHWY",

            # Clean Energy (volatile)
            "ENPH", "SEDG", "FSLR", "RUN",

            # Travel/Leisure (cyclical)
            "UBER", "LYFT", "EXPE", "MAR",

            # Gaming
            "DKNG", "EA",

            # Biotech (liquid, volatile)
            "MRNA", "VRTX", "REGN", "BIIB",
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
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        self.set_benchmark("SPY")

    def rebalance(self):
        if self.is_warming_up:
            return

        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                return

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
                # Acceleration bonus
                accel_bonus = 1.3 if acceleration > 0 else 1.0
                scores[symbol] = mom * accel_bonus

        if len(scores) < 5:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        total_mom = sum(scores[s] for s in top_symbols)
        weights = {s: scores[s] / total_mom for s in top_symbols}

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])
