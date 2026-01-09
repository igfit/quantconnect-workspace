"""
High-Beta Small/Mid Cap Momentum Strategy v5 - VOL TARGETING

Key changes:
- Volatility targeting: reduce exposure when vol > 25%
- Tighter regime filter: 100 SMA instead of 200 (faster exits)
- Top 5 most concentrated
- Only pure small/mid caps (no TSLA/NVDA)
"""

from AlgorithmImports import *


class HighBetaSmallMidV5(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Parameters - VOL TARGETING
        self.lookback_days = 126
        self.accel_period = 21
        self.top_n = 5            # Very concentrated
        self.min_dollar_volume = 5_000_000
        self.target_vol = 0.25    # 25% annualized vol target

        self.prev_short_mom = {}

        # PURE SMALL/MID CAP UNIVERSE (no mega-caps)
        # 35 stocks all with $5B-$50B market cap as of 2020
        self.universe_tickers = [
            # Semiconductors (high beta cyclicals)
            "AMD", "MU", "MRVL", "ON", "SWKS", "QRVO",
            "AMAT", "LRCX", "KLAC", "ENTG",

            # Software (pre-2020 IPO, high growth)
            "CRWD", "ZS", "OKTA", "TWLO", "NET",
            "MDB", "DOCU", "SPLK", "WDAY",

            # Fintech
            "SQ", "PYPL",

            # Consumer (high beta)
            "SHOP", "ETSY", "ROKU", "SNAP", "PINS", "TTD",
            "W",

            # Clean Energy (extreme vol)
            "ENPH", "SEDG", "FSLR",

            # Travel (cyclical)
            "UBER", "LYFT", "EXPE",

            # Gaming
            "DKNG",
        ]

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        # TIGHTER regime filter: 100 SMA
        self.spy_sma = self.sma(self.spy, 100, Resolution.DAILY)

        # Volatility indicator
        self.vix_proxy = self.add_equity("VXX", Resolution.DAILY).symbol
        self.spy_std = self.std(self.spy, 20, Resolution.DAILY)

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

        # TIGHTER regime filter
        if not self.spy_sma.is_ready:
            return
        if self.securities[self.spy].price < self.spy_sma.current.value:
            self.liquidate()
            return

        # Volatility scaling: reduce exposure in high vol
        vol_scale = 1.0
        if self.spy_std.is_ready:
            current_vol = self.spy_std.current.value * 16  # Annualize daily std
            spy_price = self.securities[self.spy].price
            current_vol_pct = current_vol / spy_price if spy_price > 0 else 0.2
            if current_vol_pct > self.target_vol:
                vol_scale = self.target_vol / current_vol_pct
                vol_scale = max(0.3, min(1.0, vol_scale))  # Min 30% exposure

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
                accel_bonus = 1.3 if acceleration > 0 else 1.0
                scores[symbol] = mom * accel_bonus

        if len(scores) < 3:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        total_mom = sum(scores[s] for s in top_symbols)
        weights = {s: (scores[s] / total_mom) * vol_scale for s in top_symbols}

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])
