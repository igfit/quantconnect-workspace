# region imports
from AlgorithmImports import *
# endregion

class MomentumAccelV18(QCAlgorithm):
    """
    V18: Momentum Acceleration

    Hypothesis: Stocks with ACCELERATING momentum outperform
    - Short-term momentum > Long-term momentum = acceleration
    - Combined score: momentum * acceleration
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe
        self.min_market_cap = 5_000_000_000     # $5B
        self.max_market_cap = 500_000_000_000   # $500B
        self.min_price = 15
        self.min_dollar_volume = 30_000_000
        self.universe_size = 50
        self.top_n = 4

        self.universe_symbols = []
        self.price_history = {}
        self.holdings = {}

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

    def get_momentum_acceleration(self, symbol):
        """
        Momentum acceleration = normalized short-term mom - normalized long-term mom
        If acceleration > 0, momentum is increasing
        """
        mom_1m = self.get_momentum(symbol, 21)
        mom_3m = self.get_momentum(symbol, 63)

        if mom_1m is None or mom_3m is None:
            return None, None

        # Normalize to monthly rate
        mom_1m_monthly = mom_1m
        mom_3m_monthly = mom_3m / 3

        acceleration = mom_1m_monthly - mom_3m_monthly
        return acceleration, mom_3m

    def rebalance(self):
        if self.is_warming_up:
            return

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

        scores = []
        for symbol in self.universe_symbols:
            accel, mom_3m = self.get_momentum_acceleration(symbol)
            mom_6m = self.get_momentum(symbol, 126)

            if accel is None or mom_6m is None:
                continue

            # Require positive 6-month momentum
            if mom_6m < 0.15:
                continue

            # Require positive acceleration (momentum increasing)
            if accel < 0.02:
                continue

            # Score = momentum * (1 + acceleration)
            score = mom_6m * (1 + accel * 5)  # Amplify acceleration effect
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
