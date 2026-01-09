# region imports
from AlgorithmImports import *
# endregion

class AdaptivePositionsV24(QCAlgorithm):
    """
    V24: Adaptive Number of Positions

    - High conviction environment (low VIX, strong trend): 2 positions
    - Medium conviction: 4 positions
    - Low conviction: 6 positions or cash
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

        self.universe_symbols = []
        self.price_history = {}
        self.spy_prices = []
        self.holdings = {}

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter, self.fine_filter)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_sma_50 = self.sma(self.spy, 50, Resolution.DAILY)

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.schedule.on(
            self.date_rules.every([DayOfWeek.MONDAY]),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_benchmark("SPY")
        self.set_warm_up(200, Resolution.DAILY)

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

    def on_data(self, data):
        if self.is_warming_up:
            return

        if self.spy in data and data[self.spy] is not None:
            self.spy_prices.append(data[self.spy].close)
            if len(self.spy_prices) > 200:
                self.spy_prices = self.spy_prices[-200:]

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

    def get_market_conviction(self):
        """
        Determine market conviction level:
        - High: VIX < 15, SPY > 50 SMA > 200 SMA, strong trend
        - Medium: Moderate VIX, mixed signals
        - Low: High VIX or weak trend
        """
        vix = self.get_vix()
        spy_price = self.securities[self.spy].price

        if not self.spy_sma_200.is_ready or not self.spy_sma_50.is_ready:
            return "low"

        sma_200 = self.spy_sma_200.current.value
        sma_50 = self.spy_sma_50.current.value

        # Strong uptrend: price > 50 SMA > 200 SMA
        strong_trend = spy_price > sma_50 > sma_200

        if vix < 15 and strong_trend:
            return "high"
        elif vix < 22 and spy_price > sma_200:
            return "medium"
        elif vix < 28 and spy_price > sma_200:
            return "low"
        else:
            return "none"

    def get_position_count(self, conviction):
        if conviction == "high":
            return 2  # Concentrated
        elif conviction == "medium":
            return 4
        elif conviction == "low":
            return 6
        else:
            return 0

    def rebalance(self):
        if self.is_warming_up:
            return

        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.holdings = {}
            return

        conviction = self.get_market_conviction()
        top_n = self.get_position_count(conviction)

        if top_n == 0:
            self.liquidate()
            self.holdings = {}
            return

        scores = []
        for symbol in self.universe_symbols:
            mom_6m = self.get_momentum(symbol, 126)
            mom_3m = self.get_momentum(symbol, 63)
            mom_1m = self.get_momentum(symbol, 21)

            if mom_6m is None or mom_3m is None or mom_1m is None:
                continue

            # Higher threshold for more concentrated portfolios
            min_mom = 0.30 if top_n <= 2 else (0.20 if top_n <= 4 else 0.15)
            if mom_6m < min_mom:
                continue

            if mom_1m < 0:
                continue

            score = mom_6m * 0.5 + mom_3m * 0.3 + mom_1m * 0.2
            scores.append((symbol, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        top_stocks = scores[:top_n]

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
