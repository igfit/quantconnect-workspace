"""
v12 DUAL MOMENTUM Strategy

Classic dual momentum approach (Antonacci):
1. Absolute momentum: Stock must have positive momentum
2. Relative momentum: Stock must beat SPY

Only invest when both conditions are met.
This should work across different market regimes.
"""

from AlgorithmImports import *


class V12DualMomentum(QCAlgorithm):

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
        self.max_market_cap = 1000e9  # $1T
        self.min_price = 10
        self.min_avg_dollar_volume = 20e6

        self.last_universe_refresh = None

        self.rebalance_week = 0
        self.active_symbols = []
        self.momentum = {}
        self.volume_sma = {}

        # SPY for dual momentum comparison
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_mom = self.roc(self.spy, self.lookback_days, Resolution.DAILY)
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

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
            MorningstarSectorCode.CONSUMER_DEFENSIVE,
        ]

        sector_filtered = [x for x in filtered
                         if x.asset_classification.morningstar_sector_code not in excluded_sectors]

        sorted_stocks = sorted(sector_filtered, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_stocks[:self.universe_size]]

        self.last_universe_refresh = self.time
        self.log(f"Dual momentum universe: {len(selected)} stocks at {self.time.date()}")

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
        if not self.spy_sma_200.is_ready or not self.spy_mom.is_ready:
            return

        spy_price = self.securities[self.spy].price
        spy_momentum = self.spy_mom.current.value

        # If SPY below 200 SMA, go to cash
        if spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            return

        # If SPY has negative momentum, reduce exposure
        if spy_momentum < 0:
            self.liquidate()
            return

        scores = {}
        for symbol in self.active_symbols:
            if symbol not in self.momentum or not self.momentum[symbol].is_ready:
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

            # DUAL MOMENTUM:
            # 1. Absolute momentum: stock must be positive
            if stock_mom <= 0:
                continue

            # 2. Relative momentum: stock must beat SPY
            relative_mom = stock_mom - spy_momentum
            if relative_mom <= 0:
                continue

            # Score by relative outperformance
            scores[symbol] = relative_mom

        if len(scores) < 3:
            # If no stocks pass dual momentum, go to cash
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
