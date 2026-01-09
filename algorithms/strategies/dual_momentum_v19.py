# region imports
from AlgorithmImports import *
# endregion

class DualMomentumV19(QCAlgorithm):
    """
    V19: Dual Momentum Strategy

    Academic dual momentum:
    1. Absolute momentum: Only invest if market has positive momentum
    2. Relative momentum: Select top stocks within the universe
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe
        self.min_market_cap = 10_000_000_000    # $10B+
        self.max_market_cap = 1_000_000_000_000 # $1T
        self.min_price = 20
        self.min_dollar_volume = 40_000_000
        self.universe_size = 40
        self.top_n = 4

        self.universe_symbols = []
        self.price_history = {}
        self.spy_prices = []
        self.holdings = {}

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter, self.fine_filter)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.schedule.on(
            self.date_rules.month_start("SPY", 0),  # Monthly rebalance
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_benchmark("SPY")
        self.set_warm_up(260, Resolution.DAILY)

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
                if sector not in [311, 102, 308]:  # Tech, Consumer, Comm
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

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Track SPY prices for absolute momentum
        if self.spy in data and data[self.spy] is not None:
            self.spy_prices.append(data[self.spy].close)
            if len(self.spy_prices) > 260:
                self.spy_prices = self.spy_prices[-260:]

        for symbol in self.universe_symbols:
            if symbol in data and data[symbol] is not None:
                price = data[symbol].close
                if symbol not in self.price_history:
                    self.price_history[symbol] = []
                self.price_history[symbol].append(price)
                if len(self.price_history[symbol]) > 260:
                    self.price_history[symbol] = self.price_history[symbol][-260:]

    def get_spy_momentum_12m(self):
        """12-month SPY momentum (absolute momentum signal)"""
        if len(self.spy_prices) < 252:
            return None
        return (self.spy_prices[-1] - self.spy_prices[-252]) / self.spy_prices[-252]

    def get_momentum_12_1(self, symbol):
        """Classic 12-1 momentum (skip last month)"""
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < 252:
            return None
        # 12-month return, skipping last month
        price_12m = prices[-252]
        price_1m = prices[-21]
        if price_12m <= 0:
            return None
        return (price_1m - price_12m) / price_12m

    def get_momentum_1m(self, symbol):
        """1-month momentum"""
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < 21:
            return None
        return (prices[-1] - prices[-21]) / prices[-21]

    def rebalance(self):
        if self.is_warming_up:
            return

        # ABSOLUTE MOMENTUM: Check if market has positive momentum
        spy_mom = self.get_spy_momentum_12m()
        if spy_mom is None or spy_mom < 0:
            self.liquidate()
            self.holdings = {}
            return

        # Additional regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.holdings = {}
            return

        vix = self.get_vix()
        if vix > 30:
            self.liquidate()
            self.holdings = {}
            return

        # RELATIVE MOMENTUM: Select top stocks
        scores = []
        for symbol in self.universe_symbols:
            mom_12_1 = self.get_momentum_12_1(symbol)
            mom_1m = self.get_momentum_1m(symbol)

            if mom_12_1 is None or mom_1m is None:
                continue

            # Must have positive 12-1 momentum
            if mom_12_1 < 0.10:  # 10%+
                continue

            # Recent momentum confirmation
            if mom_1m < -0.05:  # Not crashing
                continue

            score = mom_12_1
            scores.append((symbol, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        top_stocks = scores[:self.top_n]

        if len(top_stocks) == 0:
            self.liquidate()
            self.holdings = {}
            return

        weight = 1.0 / len(top_stocks)

        new_holdings = set(s for s, _ in top_stocks)
        for symbol in list(self.holdings.keys()):
            if symbol not in new_holdings:
                self.liquidate(symbol)
                del self.holdings[symbol]

        for symbol, score in top_stocks:
            if symbol in self.securities:
                self.set_holdings(symbol, weight)
                self.holdings[symbol] = weight
