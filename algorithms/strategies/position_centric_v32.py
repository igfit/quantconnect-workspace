# region imports
from AlgorithmImports import *
# endregion

class PositionCentricV32(QCAlgorithm):
    """
    V32: Hybrid Best-of-Both (Target 30% CAGR)

    Combines:
    - V16's concentration (2-3 positions) + high momentum threshold
    - V28's breakout entry + daily exit monitoring
    - Add 1-month momentum acceleration filter
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
        self.max_positions = 3

        # Entry: Strong momentum + breakout
        self.entry_mom_6m = 0.35        # 35% 6-month (between V16's 30% and V30's 40%)
        self.entry_mom_1m = 0.03        # Positive recent
        self.entry_adx = 22

        # Exit: From V28
        self.trailing_stop_pct = 0.18
        self.hard_stop_pct = 0.14

        self.universe_symbols = []
        self.price_history = {}
        self.positions = {}
        self.sma_20 = {}
        self.sma_50 = {}
        self.high_10 = {}  # 10-day high for tighter breakout
        self.adx_ind = {}

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter, self.fine_filter)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.daily_signal_check
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

            if symbol not in self.sma_20:
                self.sma_20[symbol] = self.sma(symbol, 20, Resolution.DAILY)
            if symbol not in self.sma_50:
                self.sma_50[symbol] = self.sma(symbol, 50, Resolution.DAILY)

            if symbol not in self.high_10:
                self.high_10[symbol] = Maximum(10)
                self.register_indicator(symbol, self.high_10[symbol], Resolution.DAILY)

            if symbol not in self.adx_ind:
                self.adx_ind[symbol] = AverageDirectionalIndex(14)
                self.register_indicator(symbol, self.adx_ind[symbol], Resolution.DAILY)

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

                if symbol in self.positions:
                    pos = self.positions[symbol]
                    pos["highest_price"] = max(pos["highest_price"], price)

    def get_momentum(self, symbol, days):
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < days:
            return None
        if prices[-days] <= 0:
            return None
        return (prices[-1] - prices[-days]) / prices[-days]

    def is_breakout(self, symbol):
        """Check if price is at or near 10-day high"""
        if symbol not in self.high_10 or not self.high_10[symbol].is_ready:
            return False
        if symbol not in self.securities:
            return False

        price = self.securities[symbol].price
        high = self.high_10[symbol].current.value
        return price >= high * 0.99

    def check_entry_signal(self, symbol):
        if symbol not in self.securities:
            return False

        price = self.securities[symbol].price
        if price <= 0:
            return False

        # Breakout condition
        if not self.is_breakout(symbol):
            return False

        # Strong 6-month momentum
        mom_6m = self.get_momentum(symbol, 126)
        if mom_6m is None or mom_6m < self.entry_mom_6m:
            return False

        # Positive recent momentum
        mom_1m = self.get_momentum(symbol, 21)
        if mom_1m is None or mom_1m < self.entry_mom_1m:
            return False

        # Price above both SMAs
        if symbol in self.sma_20 and self.sma_20[symbol].is_ready:
            if price < self.sma_20[symbol].current.value:
                return False
        if symbol in self.sma_50 and self.sma_50[symbol].is_ready:
            if price < self.sma_50[symbol].current.value:
                return False

        # ADX trending
        if symbol in self.adx_ind and self.adx_ind[symbol].is_ready:
            adx = self.adx_ind[symbol].current.value
            pos_di = self.adx_ind[symbol].positive_directional_index.current.value
            neg_di = self.adx_ind[symbol].negative_directional_index.current.value
            if adx < self.entry_adx or pos_di <= neg_di:
                return False

        return True

    def check_exit_signal(self, symbol):
        if symbol not in self.securities:
            return True

        if symbol not in self.positions:
            return False

        price = self.securities[symbol].price
        if price <= 0:
            return True

        pos = self.positions[symbol]
        entry_price = pos["entry_price"]
        highest_price = pos["highest_price"]

        # Hard stop
        if price < entry_price * (1 - self.hard_stop_pct):
            return True

        # Trailing stop
        if price < highest_price * (1 - self.trailing_stop_pct):
            return True

        # Price significantly below 20 SMA
        if symbol in self.sma_20 and self.sma_20[symbol].is_ready:
            if price < self.sma_20[symbol].current.value * 0.96:
                return True

        # 1-month momentum reversal
        mom_1m = self.get_momentum(symbol, 21)
        if mom_1m is not None and mom_1m < -0.10:
            return True

        return False

    def daily_signal_check(self):
        if self.is_warming_up:
            return

        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            for symbol in list(self.positions.keys()):
                self.liquidate(symbol)
            self.positions = {}
            return

        vix = self.get_vix()
        if vix > 28:
            for symbol in list(self.positions.keys()):
                self.liquidate(symbol)
            self.positions = {}
            return

        # Check exits first
        for symbol in list(self.positions.keys()):
            if self.check_exit_signal(symbol):
                self.liquidate(symbol)
                del self.positions[symbol]

        # Check entries
        if len(self.positions) < self.max_positions:
            candidates = []
            for symbol in self.universe_symbols:
                if symbol in self.positions:
                    continue

                if self.check_entry_signal(symbol):
                    mom_6m = self.get_momentum(symbol, 126)
                    if mom_6m is not None:
                        candidates.append((symbol, mom_6m))

            candidates.sort(key=lambda x: x[1], reverse=True)

            slots_available = self.max_positions - len(self.positions)
            for symbol, mom in candidates[:slots_available]:
                price = self.securities[symbol].price
                weight = 1.0 / self.max_positions

                if vix > 20:
                    weight *= 0.85

                self.set_holdings(symbol, weight)
                self.positions[symbol] = {
                    "entry_price": price,
                    "highest_price": price,
                    "entry_date": self.time
                }
