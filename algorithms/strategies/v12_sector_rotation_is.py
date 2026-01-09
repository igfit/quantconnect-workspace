"""
v12 SECTOR ROTATION Strategy - IN SAMPLE (2020-2024)
Same as OOS version but for 2020-2024.
"""

from AlgorithmImports import *


class V12SectorRotationIS(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.lookback_days = 126
        self.sector_lookback = 63
        self.top_n = 8
        self.min_dollar_volume = 5_000_000

        self.stocks_per_sector = 30
        self.min_market_cap = 500e6
        self.max_market_cap = 500e9
        self.min_price = 5
        self.min_avg_dollar_volume = 10e6

        self.last_universe_refresh = None

        self.sector_etfs = {
            "XLK": MorningstarSectorCode.TECHNOLOGY,
            "XLY": MorningstarSectorCode.CONSUMER_CYCLICAL,
            "XLV": MorningstarSectorCode.HEALTHCARE,
            "XLC": MorningstarSectorCode.COMMUNICATION_SERVICES,
            "XLF": MorningstarSectorCode.FINANCIAL_SERVICES,
            "XLI": MorningstarSectorCode.INDUSTRIALS,
            "XLE": MorningstarSectorCode.ENERGY,
            "XLB": MorningstarSectorCode.BASIC_MATERIALS,
            "XLP": MorningstarSectorCode.CONSUMER_DEFENSIVE,
        }

        self.sector_momentum = {}
        for etf in self.sector_etfs.keys():
            symbol = self.add_equity(etf, Resolution.DAILY).symbol
            self.sector_momentum[etf] = self.roc(symbol, self.sector_lookback, Resolution.DAILY)

        self.leading_sectors = []

        self.prev_short_mom = {}
        self.rebalance_week = 0
        self.active_symbols = []
        self.stock_sectors = {}
        self.momentum = {}
        self.short_mom = {}
        self.volume_sma = {}

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_sma_50 = self.sma(self.spy, 50, Resolution.DAILY)

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.set_warm_up(200, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.maybe_rebalance
        )
        self.set_benchmark("SPY")

    def get_leading_sectors(self):
        sector_scores = []
        for etf, sector_code in self.sector_etfs.items():
            if self.sector_momentum[etf].is_ready:
                mom = self.sector_momentum[etf].current.value
                sector_scores.append((sector_code, mom))
        sector_scores.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in sector_scores[:3]]

    def should_refresh(self):
        if self.last_universe_refresh is None:
            return True
        return (self.time - self.last_universe_refresh).days >= 90

    def coarse_filter(self, coarse):
        if not self.should_refresh():
            return Universe.UNCHANGED
        self.leading_sectors = self.get_leading_sectors()
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
        if len(self.leading_sectors) > 0:
            sector_filtered = [x for x in filtered
                             if x.asset_classification.morningstar_sector_code in self.leading_sectors]
        else:
            sector_filtered = filtered
        for stock in sector_filtered:
            self.stock_sectors[stock.symbol] = stock.asset_classification.morningstar_sector_code
        sorted_stocks = sorted(sector_filtered, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_stocks[:self.stocks_per_sector * 3]]
        self.last_universe_refresh = self.time
        return selected

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            symbol = security.symbol
            if str(symbol).startswith("XL") or symbol == self.spy:
                continue
            if symbol not in self.active_symbols:
                self.active_symbols.append(symbol)
            if symbol not in self.momentum:
                self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
                self.short_mom[symbol] = self.roc(symbol, 21, Resolution.DAILY)
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
        if not self.spy_sma_200.is_ready:
            return
        spy_price = self.securities[self.spy].price
        above_200 = spy_price > self.spy_sma_200.current.value
        above_50 = self.spy_sma_50.is_ready and spy_price > self.spy_sma_50.current.value
        if not above_200:
            self.liquidate()
            return
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.active_symbols:
                if holding.symbol in self.short_mom and self.short_mom[holding.symbol].is_ready:
                    if self.short_mom[holding.symbol].current.value < -15:
                        self.liquidate(holding.symbol)
        if not above_50:
            return
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
        weights = {s: (scores[s] / total_score) for s in top_symbols}
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)
        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])
