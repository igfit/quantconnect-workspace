# region imports
from AlgorithmImports import *
# endregion

class RecoveryMomentumV11(QCAlgorithm):
    """
    V11: Recovery Momentum

    Buy stocks that:
    1. Have fallen significantly from their high (opportunity)
    2. Are now showing strong recent momentum (recovery)
    3. Are in growth sectors

    This captures "fallen angels" that are bouncing back.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe
        self.min_market_cap = 2_000_000_000    # $2B+
        self.max_market_cap = 150_000_000_000  # $150B
        self.min_price = 10
        self.min_dollar_volume = 20_000_000
        self.universe_size = 40
        self.top_n = 5

        # Recovery parameters
        self.min_drawdown = 0.20               # At least 20% below 52W high
        self.max_drawdown = 0.60               # Not more than 60% down
        self.min_recovery = 0.10               # 10%+ recovery from recent low

        self.universe_symbols = []
        self.price_history = {}
        self.high_52w = {}
        self.low_20d = {}
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
            if symbol.value not in self.high_52w:
                self.high_52w[symbol.value] = Maximum(252)
                self.register_indicator(symbol, self.high_52w[symbol.value], Resolution.DAILY)
            if symbol.value not in self.low_20d:
                self.low_20d[symbol.value] = Minimum(20)
                self.register_indicator(symbol, self.low_20d[symbol.value], Resolution.DAILY)

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
                if len(self.price_history[symbol]) > 260:
                    self.price_history[symbol] = self.price_history[symbol][-260:]

    def get_drawdown_from_high(self, ticker, price):
        """How far is current price from 52-week high"""
        if ticker not in self.high_52w or not self.high_52w[ticker].is_ready:
            return None
        high = self.high_52w[ticker].current.value
        if high <= 0:
            return None
        return (high - price) / high

    def get_recovery_from_low(self, ticker, price):
        """How far has price recovered from 20-day low"""
        if ticker not in self.low_20d or not self.low_20d[ticker].is_ready:
            return None
        low = self.low_20d[ticker].current.value
        if low <= 0:
            return None
        return (price - low) / low

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

        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.holdings = {}
            return

        vix = self.get_vix()
        if vix > 35:
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

            # Get drawdown from 52W high
            dd = self.get_drawdown_from_high(ticker, price)
            if dd is None:
                continue

            # Must be in "opportunity zone" - down but not too much
            if dd < self.min_drawdown or dd > self.max_drawdown:
                continue

            # Get recovery from recent low
            recovery = self.get_recovery_from_low(ticker, price)
            if recovery is None or recovery < self.min_recovery:
                continue

            # Must have positive 1-month momentum
            mom_1m = self.get_momentum_1m(symbol)
            if mom_1m is None or mom_1m < 0.05:  # 5%+ 1-month return
                continue

            # Score: recovery * momentum (prefer strong recovery + strong momentum)
            score = recovery * mom_1m
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
