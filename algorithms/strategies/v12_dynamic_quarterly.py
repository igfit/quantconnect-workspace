"""
v12 Dynamic Universe - QUARTERLY REFRESH

Key changes from yearly:
1. Refresh every 3 months instead of yearly (catch momentum shifts faster)
2. Lower market cap floor ($500M) to catch rising stars
3. Use relative strength - compare to QQQ performance

This should adapt better to changing market leadership.
"""

from AlgorithmImports import *


class V12DynamicQuarterly(QCAlgorithm):

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
        self.accel_period = 21
        self.top_n = 8
        self.min_dollar_volume = 5_000_000

        # Universe - lower market cap, quarterly refresh
        self.universe_size = 50
        self.min_market_cap = 500e6   # $500M
        self.max_market_cap = 300e9   # $300B
        self.min_price = 5
        self.min_avg_dollar_volume = 10e6

        # QUARTERLY refresh (90 days)
        self.last_universe_refresh = None
        self.refresh_days = 90

        self.prev_short_mom = {}
        self.rebalance_week = 0
        self.active_symbols = []
        self.momentum = {}
        self.short_mom = {}
        self.volume_sma = {}

        # Regime filters
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.qqq_sma_10 = self.sma(self.qqq, 10, Resolution.DAILY)
        self.qqq_sma_20 = self.sma(self.qqq, 20, Resolution.DAILY)
        self.qqq_sma_50 = self.sma(self.qqq, 50, Resolution.DAILY)
        self.qqq_mom = self.roc(self.qqq, 63, Resolution.DAILY)

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("QQQ", 30),
            self.maybe_rebalance
        )
        self.set_benchmark("QQQ")

    def should_refresh(self):
        if self.last_universe_refresh is None:
            return True
        return (self.time - self.last_universe_refresh).days >= self.refresh_days

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

        growth_sectors = [
            MorningstarSectorCode.TECHNOLOGY,
            MorningstarSectorCode.CONSUMER_CYCLICAL,
            MorningstarSectorCode.HEALTHCARE,
            MorningstarSectorCode.COMMUNICATION_SERVICES
        ]

        sector_filtered = [x for x in filtered
                         if x.asset_classification.morningstar_sector_code in growth_sectors]

        # Sort by dollar volume (proxy for momentum/institutional interest)
        sorted_stocks = sorted(sector_filtered, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_stocks[:self.universe_size]]

        self.last_universe_refresh = self.time
        self.log(f"Universe refreshed (Q): {len(selected)} stocks at {self.time.date()}")

        return selected

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            symbol = security.symbol
            if symbol == self.qqq:
                continue
            if symbol not in self.active_symbols:
                self.active_symbols.append(symbol)
            if symbol not in self.momentum:
                self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
                self.short_mom[symbol] = self.roc(symbol, self.accel_period, Resolution.DAILY)
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

        qqq_price = self.securities[self.qqq].price
        if not self.qqq_sma_10.is_ready or not self.qqq_sma_20.is_ready or not self.qqq_sma_50.is_ready:
            return

        above_10 = qqq_price > self.qqq_sma_10.current.value
        above_20 = qqq_price > self.qqq_sma_20.current.value
        above_50 = qqq_price > self.qqq_sma_50.current.value
        qqq_mom_positive = self.qqq_mom.is_ready and self.qqq_mom.current.value > 0

        if not above_10:
            self.liquidate()
            return

        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.active_symbols:
                if holding.symbol in self.short_mom and self.short_mom[holding.symbol].is_ready:
                    if self.short_mom[holding.symbol].current.value < -15:
                        self.liquidate(holding.symbol)

        if above_10 and above_20 and above_50 and qqq_mom_positive:
            leverage = 1.0
        elif above_10 and above_20:
            leverage = 1.0
        else:
            leverage = 0.8

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

            if short_mom < -10:
                continue

            prev_mom = self.prev_short_mom.get(symbol, 0)
            acceleration = short_mom - prev_mom
            self.prev_short_mom[symbol] = short_mom

            if mom > 0:
                accel_bonus = 1.4 if acceleration > 0 else 1.0
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
