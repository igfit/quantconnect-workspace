# region imports
from AlgorithmImports import *
# endregion

class AggressiveMomentumV10(QCAlgorithm):
    """
    V10: Aggressive Concentrated Momentum

    Key differences from classic momentum:
    - Only 5 positions (more concentrated)
    - Focus on growth sectors
    - Faster rebalance (bi-weekly)
    - 6-month momentum (shorter lookback)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe filters
        self.min_market_cap = 1_000_000_000    # $1B+
        self.max_market_cap = 200_000_000_000  # $200B
        self.min_price = 10
        self.min_dollar_volume = 15_000_000    # $15M/day
        self.universe_size = 50
        self.top_n = 5                         # Very concentrated

        self.universe_symbols = []
        self.price_history = {}
        self.holdings = {}

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter, self.fine_filter)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_sma_50 = self.sma(self.spy, 50, Resolution.DAILY)

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        # Bi-weekly rebalance
        self.schedule.on(
            self.date_rules.every([DayOfWeek.MONDAY]),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.last_rebalance = None

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

            # Growth sectors only
            try:
                sector = x.asset_classification.morningstar_sector_code
                if sector not in [311, 102, 308]:  # Tech, Consumer Disc, Comm
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

    def get_6_month_momentum(self, symbol):
        """6-month momentum (faster reaction)"""
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < 126:
            return None

        price_6m = prices[-126]
        price_now = prices[-1]

        if price_6m <= 0:
            return None

        return (price_now - price_6m) / price_6m

    def get_3_month_momentum(self, symbol):
        """3-month momentum for ranking"""
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < 63:
            return None

        price_3m = prices[-63]
        price_now = prices[-1]

        if price_3m <= 0:
            return None

        return (price_now - price_3m) / price_3m

    def is_trending(self, symbol):
        """Check if price is above 50-day average"""
        if symbol not in self.price_history:
            return False
        prices = self.price_history[symbol]
        if len(prices) < 50:
            return False
        avg_50 = sum(prices[-50:]) / 50
        return prices[-1] > avg_50

    def rebalance(self):
        if self.is_warming_up:
            return

        # Only rebalance every 2 weeks
        if self.last_rebalance is not None:
            days_since = (self.time - self.last_rebalance).days
            if days_since < 10:
                return

        self.last_rebalance = self.time

        # Market regime
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or not self.spy_sma_50.is_ready:
            return

        # Use 50 SMA for faster regime detection
        if spy_price < self.spy_sma_50.current.value:
            self.liquidate()
            self.holdings = {}
            return

        vix = self.get_vix()
        if vix > 32:
            self.liquidate()
            self.holdings = {}
            return

        # Score stocks
        scores = []
        for symbol in self.universe_symbols:
            mom_6m = self.get_6_month_momentum(symbol)
            mom_3m = self.get_3_month_momentum(symbol)

            if mom_6m is None or mom_3m is None:
                continue

            # Must have positive 6-month momentum
            if mom_6m < 0.15:  # 15%+
                continue

            # Must be trending
            if not self.is_trending(symbol):
                continue

            # Score: combination of 6m and 3m momentum
            score = mom_6m * 0.5 + mom_3m * 0.5
            scores.append((symbol, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        top_stocks = scores[:self.top_n]

        if len(top_stocks) == 0:
            self.liquidate()
            self.holdings = {}
            return

        # Equal weight
        weight = 1.0 / len(top_stocks)

        # Liquidate old holdings
        new_holdings = set(s for s, _ in top_stocks)
        for symbol in list(self.holdings.keys()):
            if symbol not in new_holdings:
                self.liquidate(symbol)
                del self.holdings[symbol]

        # Set new holdings
        for symbol, score in top_stocks:
            if symbol in self.securities:
                self.set_holdings(symbol, weight)
                self.holdings[symbol] = weight
