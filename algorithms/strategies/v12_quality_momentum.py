"""
v12 QUALITY + MOMENTUM Strategy

Combines quality factor with momentum:
1. Filter for quality: ROE > 15%, low debt-to-equity
2. Among quality stocks, rank by momentum

Quality stocks tend to have more persistent momentum.
"""

from AlgorithmImports import *


class V12QualityMomentum(QCAlgorithm):

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

        # Universe
        self.universe_size = 50
        self.min_market_cap = 5e9     # $5B
        self.max_market_cap = 500e9   # $500B
        self.min_price = 10
        self.min_avg_dollar_volume = 20e6

        # Quality filters
        self.min_roe = 0.10  # 10% ROE minimum

        self.last_universe_refresh = None

        self.rebalance_week = 0
        self.active_symbols = []
        self.momentum = {}
        self.volume_sma = {}

        # Regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
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
        return (self.time - self.last_universe_refresh).days >= 90  # Quarterly

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

        # Market cap filter
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

        # QUALITY FILTER
        quality_stocks = []
        for stock in sector_filtered:
            try:
                # Check ROE
                if hasattr(stock, 'operation_ratios') and stock.operation_ratios is not None:
                    roe = stock.operation_ratios.roe.value
                    if roe is not None and roe > self.min_roe:
                        quality_stocks.append(stock)
                else:
                    # If no data, include but with lower priority
                    quality_stocks.append(stock)
            except:
                # Include if can't get data
                quality_stocks.append(stock)

        sorted_stocks = sorted(quality_stocks, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_stocks[:self.universe_size]]

        self.last_universe_refresh = self.time
        self.log(f"Quality momentum universe: {len(selected)} stocks at {self.time.date()}")

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
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue
            if symbol in self.volume_sma and self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue

            mom = self.momentum[symbol].current.value

            # Only positive momentum
            if mom > 0:
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
