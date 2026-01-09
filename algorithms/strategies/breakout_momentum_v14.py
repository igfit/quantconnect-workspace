# region imports
from AlgorithmImports import *
# endregion

class BreakoutMomentumV14(QCAlgorithm):
    """
    V14: Breakout Momentum

    Hypothesis: Stocks breaking to new highs with momentum continue higher
    - Buy stocks within 5% of 52-week high
    - With strong volume confirmation
    - And positive momentum
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe
        self.min_market_cap = 5_000_000_000     # $5B+
        self.max_market_cap = 500_000_000_000   # $500B
        self.min_price = 15
        self.min_dollar_volume = 30_000_000
        self.universe_size = 40
        self.top_n = 5

        self.universe_symbols = []
        self.price_history = {}
        self.volume_history = {}
        self.high_52w = {}
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
                if sector not in [311, 102, 308, 310]:  # Tech, Consumer, Comm, Industrial
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
            if symbol not in self.volume_history:
                self.volume_history[symbol] = []
            if symbol.value not in self.high_52w:
                self.high_52w[symbol.value] = Maximum(252)
                self.register_indicator(symbol, self.high_52w[symbol.value], Resolution.DAILY)

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
                bar = data[symbol]
                price = bar.close
                volume = bar.volume

                if symbol not in self.price_history:
                    self.price_history[symbol] = []
                self.price_history[symbol].append(price)
                if len(self.price_history[symbol]) > 260:
                    self.price_history[symbol] = self.price_history[symbol][-260:]

                if symbol not in self.volume_history:
                    self.volume_history[symbol] = []
                self.volume_history[symbol].append(volume)
                if len(self.volume_history[symbol]) > 50:
                    self.volume_history[symbol] = self.volume_history[symbol][-50:]

    def get_distance_from_high(self, ticker, price):
        """How close is current price to 52-week high (0 = at high)"""
        if ticker not in self.high_52w or not self.high_52w[ticker].is_ready:
            return None
        high = self.high_52w[ticker].current.value
        if high <= 0:
            return None
        return (high - price) / high

    def get_volume_ratio(self, symbol):
        """Recent volume vs average"""
        if symbol not in self.volume_history:
            return None
        vols = self.volume_history[symbol]
        if len(vols) < 20:
            return None
        avg_vol = sum(vols[-20:]) / 20
        recent_vol = sum(vols[-5:]) / 5
        if avg_vol <= 0:
            return None
        return recent_vol / avg_vol

    def get_momentum_3m(self, symbol):
        """3-month momentum"""
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < 63:
            return None
        return (prices[-1] - prices[-63]) / prices[-63]

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

        # Market regime filter
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

        candidates = []
        for symbol in self.universe_symbols:
            ticker = symbol.value
            if symbol not in self.securities:
                continue
            price = self.securities[symbol].price
            if price <= 0:
                continue

            # Must be within 5% of 52-week high (breakout zone)
            dist = self.get_distance_from_high(ticker, price)
            if dist is None or dist > 0.05:
                continue

            # Volume confirmation (above average)
            vol_ratio = self.get_volume_ratio(symbol)
            if vol_ratio is None or vol_ratio < 1.0:
                continue

            # Positive momentum
            mom_3m = self.get_momentum_3m(symbol)
            mom_1m = self.get_momentum_1m(symbol)
            if mom_3m is None or mom_1m is None:
                continue
            if mom_3m < 0.10 or mom_1m < 0:  # 10%+ 3-month, positive 1-month
                continue

            # Score: combination of momentum and volume
            score = mom_3m * vol_ratio
            candidates.append((symbol, score))

        candidates.sort(key=lambda x: x[1], reverse=True)
        top_stocks = candidates[:self.top_n]

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
