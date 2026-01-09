"""
v12 ADAPTIVE META-STRATEGY - IN SAMPLE (2020-2024)
Same as OOS but for 2020-2024 period.
"""

from AlgorithmImports import *


class V12AdaptiveMetaIS(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.lookback_days = 126
        self.min_dollar_volume = 10_000_000

        self.high_mom_top_n = 8
        self.low_mom_top_n = 12

        self.universe_size = 75
        self.last_universe_refresh = None
        self.current_regime = None

        self.prev_regime = None

        self.rebalance_week = 0
        self.active_symbols = []
        self.stock_added_in_regime = {}

        self.momentum = {}
        self.short_mom = {}
        self.sma_50 = {}
        self.sma_200 = {}
        self.volume_sma = {}

        self.prev_short_mom = {}

        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol

        self.qqq_mom_126 = self.roc(self.qqq, 126, Resolution.DAILY)
        self.qqq_mom_63 = self.roc(self.qqq, 63, Resolution.DAILY)
        self.qqq_sma_50 = self.sma(self.qqq, 50, Resolution.DAILY)
        self.qqq_sma_200 = self.sma(self.qqq, 200, Resolution.DAILY)
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.set_warm_up(210, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.weekly_check
        )
        self.set_benchmark("SPY")

    def get_regime(self):
        if not self.qqq_mom_126.is_ready or not self.qqq_sma_50.is_ready:
            return "LOW_MOMENTUM"

        qqq_price = self.securities[self.qqq].price
        mom_126 = self.qqq_mom_126.current.value
        mom_63 = self.qqq_mom_63.current.value if self.qqq_mom_63.is_ready else 0
        above_50_sma = qqq_price > self.qqq_sma_50.current.value

        if mom_126 > 15 and above_50_sma and mom_63 > 5:
            return "HIGH_MOMENTUM"

        return "LOW_MOMENTUM"

    def should_refresh(self):
        current_regime = self.get_regime()

        if self.prev_regime is not None and current_regime != self.prev_regime:
            self.log(f"REGIME CHANGE: {self.prev_regime} -> {current_regime}")
            return True

        if self.last_universe_refresh is None:
            return True

        return (self.time - self.last_universe_refresh).days >= 90

    def coarse_filter(self, coarse):
        if not self.should_refresh():
            return Universe.UNCHANGED

        self.current_regime = self.get_regime()

        if self.current_regime == "HIGH_MOMENTUM":
            min_price = 10
            min_dollar_vol = 20e6
        else:
            min_price = 20
            min_dollar_vol = 50e6

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > min_price
                   and x.dollar_volume > min_dollar_vol]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:500]]

    def fine_filter(self, fine):
        if not self.should_refresh():
            return Universe.UNCHANGED

        regime = self.current_regime

        if regime == "HIGH_MOMENTUM":
            filtered = [x for x in fine
                       if x.market_cap > 5e9
                       and x.market_cap < 300e9]

            growth_sectors = [
                MorningstarSectorCode.TECHNOLOGY,
                MorningstarSectorCode.CONSUMER_CYCLICAL,
                MorningstarSectorCode.HEALTHCARE,
                MorningstarSectorCode.COMMUNICATION_SERVICES,
            ]
            sector_filtered = [x for x in filtered
                             if x.asset_classification.morningstar_sector_code in growth_sectors]

        else:
            filtered = [x for x in fine
                       if x.market_cap > 20e9
                       and x.market_cap < 1000e9]

            excluded_sectors = [
                MorningstarSectorCode.UTILITIES,
                MorningstarSectorCode.REAL_ESTATE,
            ]
            sector_filtered = [x for x in filtered
                             if x.asset_classification.morningstar_sector_code not in excluded_sectors]

        sorted_stocks = sorted(sector_filtered, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_stocks[:self.universe_size]]

        self.prev_regime = regime
        self.last_universe_refresh = self.time
        self.log(f"Universe refresh ({regime}): {len(selected)} stocks at {self.time.date()}")

        return selected

    def on_securities_changed(self, changes):
        current_regime = self.get_regime()

        for security in changes.added_securities:
            symbol = security.symbol
            if symbol in [self.spy, self.qqq]:
                continue
            if symbol not in self.active_symbols:
                self.active_symbols.append(symbol)
                self.stock_added_in_regime[symbol] = current_regime

            if symbol not in self.momentum:
                self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
                self.short_mom[symbol] = self.roc(symbol, 21, Resolution.DAILY)
                self.sma_50[symbol] = self.sma(symbol, 50, Resolution.DAILY)
                self.sma_200[symbol] = self.sma(symbol, 200, Resolution.DAILY)
                self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.active_symbols:
                self.active_symbols.remove(symbol)
            if symbol in self.stock_added_in_regime:
                del self.stock_added_in_regime[symbol]
            if self.portfolio[symbol].invested:
                self.liquidate(symbol)

    def weekly_check(self):
        self.rebalance_week += 1
        regime = self.get_regime()

        if regime == "HIGH_MOMENTUM":
            if self.rebalance_week % 2 == 0:
                self.rebalance_high_momentum()
        else:
            if self.rebalance_week % 4 == 0:
                self.rebalance_low_momentum()

    def rebalance_high_momentum(self):
        if self.is_warming_up:
            return
        if len(self.active_symbols) == 0:
            return

        if not self.spy_sma_200.is_ready:
            return
        spy_price = self.securities[self.spy].price
        if spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            return

        if not self.qqq_sma_50.is_ready:
            return

        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.active_symbols:
                if holding.symbol in self.short_mom and self.short_mom[holding.symbol].is_ready:
                    if self.short_mom[holding.symbol].current.value < -15:
                        self.liquidate(holding.symbol)

        scores = {}
        for symbol in self.active_symbols:
            if symbol not in self.momentum or not self.momentum[symbol].is_ready:
                continue
            if symbol not in self.short_mom or not self.short_mom[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue
            if symbol in self.volume_sma and self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue

            mom = self.momentum[symbol].current.value
            short_mom = self.short_mom[symbol].current.value

            if mom <= 0 or short_mom < -10:
                continue

            prev_mom = self.prev_short_mom.get(symbol, 0)
            acceleration = short_mom - prev_mom
            self.prev_short_mom[symbol] = short_mom

            accel_bonus = 1.4 if acceleration > 0 else 1.0
            scores[symbol] = mom * accel_bonus

        if len(scores) < 3:
            return

        actual_n = min(self.high_mom_top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        total_score = sum(scores[s] for s in top_symbols)
        weights = {s: (scores[s] / total_score) for s in top_symbols}

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])

    def rebalance_low_momentum(self):
        if self.is_warming_up:
            return
        if len(self.active_symbols) == 0:
            return

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
            if price < 10:
                continue
            if symbol in self.volume_sma and self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue

            sma50 = self.sma_50[symbol].current.value
            sma200 = self.sma_200[symbol].current.value
            mom = self.momentum[symbol].current.value

            if price <= sma50:
                continue
            if sma50 <= sma200:
                continue
            if mom <= 0:
                continue

            scores[symbol] = mom

        if len(scores) < 3:
            self.liquidate()
            return

        actual_n = min(self.low_mom_top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        target_weight = 1.0 / actual_n

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, target_weight)
