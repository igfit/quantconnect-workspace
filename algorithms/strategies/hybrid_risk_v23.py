# region imports
from AlgorithmImports import *
# endregion

class HybridRiskV23(QCAlgorithm):
    """
    V23: Hybrid Risk Management

    Combines:
    - VIX-adaptive position sizing
    - Stop-loss (10%)
    - Trailing stop (15%)
    - Momentum quality filter
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.min_market_cap = 10_000_000_000
        self.max_market_cap = 2_000_000_000_000
        self.min_price = 20
        self.min_dollar_volume = 50_000_000
        self.universe_size = 50
        self.top_n = 4

        # Risk params
        self.stop_loss_pct = 0.10
        self.trailing_stop_pct = 0.15

        self.universe_symbols = []
        self.price_history = {}
        self.holdings = {}
        self.entry_prices = {}
        self.highest_prices = {}

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter, self.fine_filter)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.schedule.on(
            self.date_rules.every([DayOfWeek.MONDAY]),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 31),
            self.check_stops
        )

        self.set_benchmark("SPY")
        self.set_warm_up(150, Resolution.DAILY)

    def coarse_filter(self, coarse):
        if self.is_warming_up:
            return []

        filtered = [x for x in coarse
                    if x.has_fundamental_data
                    and x.price > self.min_price
                    and x.dollar_volume > self.min_dollar_volume]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:200]]

    def fine_filter(self, fine):
        if self.is_warming_up:
            return []

        filtered = []
        for x in fine:
            if not (self.min_market_cap < x.market_cap < self.max_market_cap):
                continue

            try:
                sector = x.asset_classification.morningstar_sector_code
                if sector not in [311, 102, 308]:
                    continue
            except:
                continue

            filtered.append(x)

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_by_volume[:self.universe_size]]
        return selected

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            symbol = security.symbol
            if symbol == self.spy or symbol == self.vix:
                continue
            if symbol not in self.price_history:
                self.price_history[symbol] = []

        self.universe_symbols = [s for s in self.active_securities.keys()
                                  if s != self.spy and s != self.vix]

    def get_vix(self):
        if self.vix in self.securities and self.securities[self.vix].price > 0:
            return self.securities[self.vix].price
        return 20

    def get_vix_scale(self):
        vix = self.get_vix()
        if vix < 15:
            return 1.0
        elif vix < 20:
            return 0.80
        elif vix < 25:
            return 0.60
        elif vix < 30:
            return 0.35
        else:
            return 0.0

    def on_data(self, data):
        if self.is_warming_up:
            return

        for symbol in self.universe_symbols:
            if symbol in data and data[symbol] is not None:
                price = data[symbol].close
                if symbol not in self.price_history:
                    self.price_history[symbol] = []
                self.price_history[symbol].append(price)
                if len(self.price_history[symbol]) > 150:
                    self.price_history[symbol] = self.price_history[symbol][-150:]

                if symbol in self.holdings:
                    if symbol not in self.highest_prices:
                        self.highest_prices[symbol] = price
                    else:
                        self.highest_prices[symbol] = max(self.highest_prices[symbol], price)

    def get_momentum(self, symbol, days):
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < days:
            return None
        return (prices[-1] - prices[-days]) / prices[-days]

    def get_momentum_quality(self, symbol):
        """Check if momentum is consistent (not just one spike)"""
        mom_6m = self.get_momentum(symbol, 126)
        mom_3m = self.get_momentum(symbol, 63)
        mom_1m = self.get_momentum(symbol, 21)

        if mom_6m is None or mom_3m is None or mom_1m is None:
            return None, False

        # Quality = all positive and reasonably consistent
        if mom_6m < 0 or mom_3m < 0 or mom_1m < -0.05:
            return mom_6m, False

        return mom_6m, True

    def check_stops(self):
        if self.is_warming_up:
            return

        for symbol in list(self.holdings.keys()):
            if symbol not in self.securities:
                continue

            price = self.securities[symbol].price
            if price <= 0:
                continue

            entry = self.entry_prices.get(symbol, price)
            highest = self.highest_prices.get(symbol, price)

            if price < entry * (1 - self.stop_loss_pct):
                self.liquidate(symbol)
                self._cleanup(symbol)
                continue

            if price < highest * (1 - self.trailing_stop_pct):
                self.liquidate(symbol)
                self._cleanup(symbol)

    def _cleanup(self, symbol):
        for d in [self.holdings, self.entry_prices, self.highest_prices]:
            if symbol in d:
                del d[symbol]

    def rebalance(self):
        if self.is_warming_up:
            return

        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.holdings = {}
            self.entry_prices = {}
            self.highest_prices = {}
            return

        vix_scale = self.get_vix_scale()
        if vix_scale == 0:
            self.liquidate()
            self.holdings = {}
            self.entry_prices = {}
            self.highest_prices = {}
            return

        scores = []
        for symbol in self.universe_symbols:
            mom_6m, is_quality = self.get_momentum_quality(symbol)

            if mom_6m is None or not is_quality:
                continue

            if mom_6m < 0.15:
                continue

            score = mom_6m
            scores.append((symbol, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        top_stocks = scores[:self.top_n]

        if len(top_stocks) == 0:
            self.liquidate()
            self.holdings = {}
            self.entry_prices = {}
            self.highest_prices = {}
            return

        base_weight = 1.0 / len(top_stocks)
        weight = base_weight * vix_scale

        new_holdings = set(s for s, _ in top_stocks)
        for symbol in list(self.holdings.keys()):
            if symbol not in new_holdings:
                self.liquidate(symbol)
                self._cleanup(symbol)

        for symbol, score in top_stocks:
            if symbol in self.securities:
                if symbol not in self.holdings:
                    self.entry_prices[symbol] = self.securities[symbol].price
                    self.highest_prices[symbol] = self.securities[symbol].price
                self.set_holdings(symbol, weight)
                self.holdings[symbol] = weight
