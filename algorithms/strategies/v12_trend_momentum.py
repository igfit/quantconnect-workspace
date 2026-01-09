"""
v12 TREND + MOMENTUM Strategy

Combines trend following with momentum:
1. Stock must be in uptrend (price > 50 SMA AND 50 SMA > 200 SMA)
2. Among trending stocks, rank by momentum

This filters out false momentum signals from mean reversion.
"""

from AlgorithmImports import *


class V12TrendMomentum(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2019, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Strategy parameters
        self.lookback_days = 126
        self.top_n = 10
        self.min_dollar_volume = 10_000_000

        # Wide universe
        self.universe_size = 75
        self.min_market_cap = 5e9     # $5B
        self.max_market_cap = 500e9   # $500B
        self.min_price = 10
        self.min_avg_dollar_volume = 20e6

        self.last_universe_refresh = None

        self.rebalance_week = 0
        self.active_symbols = []
        self.momentum = {}
        self.sma_50 = {}
        self.sma_200 = {}
        self.volume_sma = {}

        # Regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.set_warm_up(210, Resolution.DAILY)  # Need 200 days for SMAs

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.maybe_rebalance
        )
        self.set_benchmark("SPY")

    def should_refresh(self):
        if self.last_universe_refresh is None:
            return True
        return (self.time - self.last_universe_refresh).days >= 180

    def coarse_filter(self, coarse):
        if not self.should_refresh():
            return Universe.UNCHANGED

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_avg_dollar_volume]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:500]]

    def fine_filter(self, fine):
        if not self.should_refresh():
            return Universe.UNCHANGED

        filtered = [x for x in fine
                   if x.market_cap > self.min_market_cap
                   and x.market_cap < self.max_market_cap]

        # Exclude defensive sectors
        excluded_sectors = [
            MorningstarSectorCode.UTILITIES,
            MorningstarSectorCode.REAL_ESTATE,
        ]

        sector_filtered = [x for x in filtered
                         if x.asset_classification.morningstar_sector_code not in excluded_sectors]

        sorted_stocks = sorted(sector_filtered, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_stocks[:self.universe_size]]

        self.last_universe_refresh = self.time
        self.log(f"Trend momentum universe: {len(selected)} stocks at {self.time.date()}")

        return selected

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            symbol = security.symbol
            if symbol == self.spy:
                continue
            if symbol not in self.active_symbols:
                self.active_symbols.append(symbol)
            if symbol not in self.momentum:
                self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
                self.sma_50[symbol] = self.sma(symbol, 50, Resolution.DAILY)
                self.sma_200[symbol] = self.sma(symbol, 200, Resolution.DAILY)
                self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.active_symbols:
                self.active_symbols.remove(symbol)
            if self.portfolio[symbol].invested:
                self.liquidate(symbol)

    def maybe_rebalance(self):
        self.rebalance_week += 1
        if self.rebalance_week % 2 == 0:
            self.rebalance()

    def rebalance(self):
        if self.is_warming_up:
            return
        if len(self.active_symbols) == 0:
            return

        # Regime check
        if not self.spy_sma_200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        if spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            return

        scores = {}
        for symbol in self.active_symbols:
            if symbol not in self.momentum or not self.momentum[symbol].is_ready:
                continue
            if symbol not in self.sma_50 or not self.sma_50[symbol].is_ready:
                continue
            if symbol not in self.sma_200 or not self.sma_200[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue
            if symbol in self.volume_sma and self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue

            sma50 = self.sma_50[symbol].current.value
            sma200 = self.sma_200[symbol].current.value
            mom = self.momentum[symbol].current.value

            # TREND FILTER:
            # 1. Price above 50 SMA (short-term uptrend)
            # 2. 50 SMA above 200 SMA (golden cross / long-term uptrend)
            if price <= sma50:
                continue
            if sma50 <= sma200:
                continue

            # Must have positive momentum
            if mom <= 0:
                continue

            # Score by momentum among trending stocks
            scores[symbol] = mom

        if len(scores) < 3:
            self.liquidate()
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        # Equal weight
        target_weight = 1.0 / actual_n

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, target_weight)
