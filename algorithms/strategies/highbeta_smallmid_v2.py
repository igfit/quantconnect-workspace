"""
High-Beta Small/Mid Cap Momentum Strategy v2

Changes from v1:
- Shorter lookback (63 days / 3 months) for faster signals
- Top 15 positions for more diversification
- More aggressive acceleration bonus
"""

from AlgorithmImports import *


class HighBetaSmallMidV2(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Parameters - SHORTER LOOKBACK
        self.lookback_days = 63   # 3-month momentum (faster)
        self.accel_period = 21    # 1-month acceleration
        self.top_n = 15           # More diversification
        self.use_regime_filter = True
        self.min_dollar_volume = 5_000_000

        self.prev_short_mom = {}

        # HIGH-BETA SMALL/MID CAP UNIVERSE (35 stocks)
        self.universe_tickers = [
            # Semiconductors
            "AMD", "MRVL", "ON", "SWKS", "QRVO", "MU",
            "AMAT", "LRCX", "KLAC", "ENTG",
            # High-Growth Software/Cloud
            "CRWD", "ZS", "DDOG", "NET", "MDB", "SNOW",
            "OKTA", "TWLO", "ZM", "DOCU",
            # Fintech
            "SQ", "PYPL", "COIN", "HOOD", "SOFI", "AFRM",
            # E-commerce/Consumer
            "SHOP", "ETSY", "ROKU", "SNAP", "PINS", "TTD",
            # Clean Energy
            "ENPH", "SEDG", "FSLR", "RUN",
            # Travel/Leisure
            "ABNB", "UBER", "LYFT", "DASH", "EXPE",
            # Gaming/Entertainment
            "RBLX", "DKNG", "PENN",
            # Biotech
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
                # More aggressive acceleration bonus (1.5x instead of just ranking)
                accel_bonus = 1.5 if acceleration > 0 else 1.0
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
