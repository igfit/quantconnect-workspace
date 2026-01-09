# region imports
from AlgorithmImports import *
# endregion

class OptimizedMomentumV20(QCAlgorithm):
    """
    V20: Optimized Momentum (Best of V12 + refinements)

    Combines:
    - Large-cap focus (V12's success)
    - 3 concentrated positions
    - Lower momentum threshold to catch more winners
    - Faster exit when momentum breaks down
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Large-cap universe (like V12)
        self.min_market_cap = 10_000_000_000    # $10B+
        self.max_market_cap = 2_000_000_000_000 # $2T
        self.min_price = 20
        self.min_dollar_volume = 50_000_000
        self.universe_size = 50
        self.top_n = 3

        self.universe_symbols = []
        self.price_history = {}
        self.holdings = {}
        self.entry_prices = {}

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter, self.fine_filter)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_sma_50 = self.sma(self.spy, 50, Resolution.DAILY)

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        # Weekly rebalance
        self.schedule.on(
            self.date_rules.every([DayOfWeek.MONDAY]),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        # Daily exit check
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 31),
            self.check_exits
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

        for symbol in self.universe_symbols:
            if symbol in data and data[symbol] is not None:
                price = data[symbol].close
                if symbol not in self.price_history:
                    self.price_history[symbol] = []
                self.price_history[symbol].append(price)
                if len(self.price_history[symbol]) > 150:
                    self.price_history[symbol] = self.price_history[symbol][-150:]

    def get_momentum(self, symbol, days):
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < days:
            return None
        return (prices[-1] - prices[-days]) / prices[-days]

    def get_sma(self, symbol, days):
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < days:
            return None
        return sum(prices[-days:]) / days

    def check_exits(self):
        """Exit positions that lose momentum"""
        if self.is_warming_up:
            return

        for symbol in list(self.holdings.keys()):
            if symbol not in self.securities:
                continue

            price = self.securities[symbol].price
            if price <= 0:
                continue

            # Exit if price drops below 20-day MA
            sma_20 = self.get_sma(symbol, 20)
            if sma_20 is not None and price < sma_20 * 0.98:  # 2% buffer
                self.liquidate(symbol)
                if symbol in self.holdings:
                    del self.holdings[symbol]
                if symbol in self.entry_prices:
                    del self.entry_prices[symbol]
                continue

            # Exit if momentum turns negative
            mom_1m = self.get_momentum(symbol, 21)
            if mom_1m is not None and mom_1m < -0.10:  # -10% in a month
                self.liquidate(symbol)
                if symbol in self.holdings:
                    del self.holdings[symbol]
                if symbol in self.entry_prices:
                    del self.entry_prices[symbol]

    def rebalance(self):
        if self.is_warming_up:
            return

        # Market regime: use 50 SMA for faster response
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_50.is_ready or spy_price < self.spy_sma_50.current.value:
            self.liquidate()
            self.holdings = {}
            self.entry_prices = {}
            return

        # Also check 200 SMA for major trend
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value * 0.95:
            self.liquidate()
            self.holdings = {}
            self.entry_prices = {}
            return

        vix = self.get_vix()
        if vix > 28:
            self.liquidate()
            self.holdings = {}
            self.entry_prices = {}
            return

        # Score stocks
        scores = []
        for symbol in self.universe_symbols:
            mom_6m = self.get_momentum(symbol, 126)
            mom_3m = self.get_momentum(symbol, 63)
            mom_1m = self.get_momentum(symbol, 21)

            if mom_6m is None or mom_3m is None or mom_1m is None:
                continue

            # Lower threshold to catch more winners
            if mom_6m < 0.15:  # 15%+ in 6 months
                continue

            # Must have positive recent momentum
            if mom_1m < 0:
                continue

            # Check price above 50-day MA
            sma_50 = self.get_sma(symbol, 50)
            if symbol in self.securities:
                price = self.securities[symbol].price
                if sma_50 is not None and price < sma_50:
                    continue

            # Combined score
            score = mom_6m * 0.4 + mom_3m * 0.4 + mom_1m * 0.2
            scores.append((symbol, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        top_stocks = scores[:self.top_n]

        if len(top_stocks) == 0:
            self.liquidate()
            self.holdings = {}
            self.entry_prices = {}
            return

        weight = 1.0 / len(top_stocks)

        new_holdings = set(s for s, _ in top_stocks)
        for symbol in list(self.holdings.keys()):
            if symbol not in new_holdings:
                self.liquidate(symbol)
                del self.holdings[symbol]
                if symbol in self.entry_prices:
                    del self.entry_prices[symbol]

        for symbol, score in top_stocks:
            if symbol in self.securities:
                self.set_holdings(symbol, weight)
                self.holdings[symbol] = weight
                self.entry_prices[symbol] = self.securities[symbol].price
