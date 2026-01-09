"""
v12 RELATIVE STRENGTH Strategy

Key insight: Absolute momentum may not work in low-momentum regimes.
Instead, look for stocks OUTPERFORMING the market.

Signal: Stock 6-month return - QQQ 6-month return > 0
(Stock is beating the market)

This should work in both:
- 2015-2019: Find stocks beating a slow-moving market
- 2020-2024: Find stocks beating a fast-moving market
"""

from AlgorithmImports import *


class V12RelativeStrength(QCAlgorithm):

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

        # Universe - include both mid and large caps
        self.universe_size = 75
        self.min_market_cap = 1e9     # $1B
        self.max_market_cap = 1000e9  # $1T
        self.min_price = 10
        self.min_avg_dollar_volume = 20e6

        self.last_universe_refresh = None

        self.prev_short_mom = {}
        self.rebalance_week = 0
        self.active_symbols = []
        self.momentum = {}
        self.short_mom = {}
        self.volume_sma = {}

        # Benchmark for relative strength
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.qqq_mom = self.roc(self.qqq, self.lookback_days, Resolution.DAILY)
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.maybe_rebalance
        )
        self.set_benchmark("QQQ")

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

        # Broad sector filter
        excluded_sectors = [
            MorningstarSectorCode.UTILITIES,
            MorningstarSectorCode.REAL_ESTATE,
        ]

        sector_filtered = [x for x in filtered
                         if x.asset_classification.morningstar_sector_code not in excluded_sectors]

        sorted_stocks = sorted(sector_filtered, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_stocks[:self.universe_size]]

        self.last_universe_refresh = self.time
        self.log(f"Universe (RS): {len(selected)} stocks at {self.time.date()}")

        return selected

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            symbol = security.symbol
            if symbol in [self.spy, self.qqq]:
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

        # Simple regime - SPY above 200 SMA
        if not self.spy_sma_200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        if spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            return

        # Get QQQ momentum for relative strength calculation
        if not self.qqq_mom.is_ready:
            return
        qqq_momentum = self.qqq_mom.current.value

        # Exit weak positions (relative weakness)
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.active_symbols:
                if holding.symbol in self.short_mom and self.short_mom[holding.symbol].is_ready:
                    stock_short = self.short_mom[holding.symbol].current.value
                    # Exit if underperforming badly
                    if stock_short < -20:
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

            stock_mom = self.momentum[symbol].current.value
            short_mom = self.short_mom[symbol].current.value

            # RELATIVE STRENGTH: stock momentum - QQQ momentum
            relative_strength = stock_mom - qqq_momentum

            # Only consider stocks with positive relative strength
            # (beating the market)
            if relative_strength <= 0:
                continue

            # Also require not in severe short-term decline
            if short_mom < -15:
                continue

            prev_mom = self.prev_short_mom.get(symbol, 0)
            acceleration = short_mom - prev_mom
            self.prev_short_mom[symbol] = short_mom

            # Score based on relative strength + acceleration
            accel_bonus = 1.4 if acceleration > 0 else 1.0
            scores[symbol] = relative_strength * accel_bonus

        if len(scores) < 3:
            # Fallback: if no stocks beating market, go to cash
            self.liquidate()
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        total_score = sum(scores[s] for s in top_symbols)
        weights = {s: (scores[s] / total_score) for s in top_symbols}

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])
