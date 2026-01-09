# region imports
from AlgorithmImports import *
# endregion

class PositionCentricV36(QCAlgorithm):
    """
    V36: Maximum CAGR (Target 30%+ CAGR)

    Builds on V35's success (29% CAGR) with:
    - 2 positions max (higher concentration)
    - Up to 1.75x leverage in ideal conditions
    - Focus on absolute highest momentum mega-caps
    - Tighter exits to protect gains
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Mega-cap focus with high liquidity
        self.min_market_cap = 50_000_000_000   # $50B+ only
        self.max_market_cap = 5_000_000_000_000
        self.min_price = 30
        self.min_dollar_volume = 200_000_000   # Very liquid
        self.universe_size = 30
        self.max_positions = 2                  # Maximum concentration

        # Entry thresholds
        self.entry_mom_6m = 0.30               # 30% 6-month momentum
        self.entry_mom_3m = 0.12               # 12% 3-month momentum

        # Exit - tighter to protect gains
        self.trailing_stop_pct = 0.12          # Tighter trailing
        self.hard_stop_pct = 0.10

        # Leverage settings
        self.base_leverage = 1.0
        self.max_leverage = 1.75

        self.universe_symbols = []
        self.price_history = {}
        self.positions = {}
        self.sma_20 = {}
        self.sma_50 = {}
        self.high_20 = {}
        self.adx_ind = {}

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter, self.fine_filter)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_sma_50 = self.sma(self.spy, 50, Resolution.DAILY)

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
        return [x.symbol for x in sorted_by_volume[:100]]

    def fine_filter(self, fine):
        if self.is_warming_up:
            return []

        # All sectors but only mega caps
        filtered = [x for x in fine
                    if self.min_market_cap < x.market_cap < self.max_market_cap]

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

            if symbol not in self.high_20:
                self.high_20[symbol] = Maximum(20)
                self.register_indicator(symbol, self.high_20[symbol], Resolution.DAILY)

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

    def is_new_high(self, symbol):
        if symbol not in self.high_20 or not self.high_20[symbol].is_ready:
            return False
        if symbol not in self.securities:
            return False

        price = self.securities[symbol].price
        high_20 = self.high_20[symbol].current.value
        return price >= high_20 * 0.99

    def get_leverage_multiplier(self):
        """Determine leverage based on market conditions"""
        if not self.spy_sma_200.is_ready or not self.spy_sma_50.is_ready:
            return self.base_leverage

        spy_price = self.securities[self.spy].price
        vix = self.get_vix()

        # Ideal conditions for max leverage
        above_200 = spy_price > self.spy_sma_200.current.value
        above_50 = spy_price > self.spy_sma_50.current.value
        strong_trend = spy_price > self.spy_sma_200.current.value * 1.08

        if strong_trend and vix < 15:
            return self.max_leverage  # 1.75x
        elif above_200 and above_50 and vix < 18:
            return 1.5
        elif above_200 and vix < 22:
            return 1.25
        elif above_200:
            return self.base_leverage
        else:
            return 0.7  # Reduce significantly in bear markets

    def check_entry_signal(self, symbol):
        if symbol not in self.securities:
            return False

        price = self.securities[symbol].price
        if price <= 0:
            return False

        # New 20-day high
        if not self.is_new_high(symbol):
            return False

        # Strong 6-month momentum
        mom_6m = self.get_momentum(symbol, 126)
        if mom_6m is None or mom_6m < self.entry_mom_6m:
            return False

        # Strong 3-month momentum
        mom_3m = self.get_momentum(symbol, 63)
        if mom_3m is None or mom_3m < self.entry_mom_3m:
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
            if adx < 22 or pos_di <= neg_di:
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

        # Momentum breakdown
        mom_1m = self.get_momentum(symbol, 21)
        if mom_1m is not None and mom_1m < -0.08:
            return True

        # Weekly momentum crash
        mom_1w = self.get_momentum(symbol, 5)
        if mom_1w is not None and mom_1w < -0.10:
            return True

        return False

    def daily_signal_check(self):
        if self.is_warming_up:
            return

        spy_price = self.securities[self.spy].price

        # Use 200 SMA for regime
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

        leverage = self.get_leverage_multiplier()

        # Check exits
        for symbol in list(self.positions.keys()):
            if self.check_exit_signal(symbol):
                self.liquidate(symbol)
                del self.positions[symbol]

        # Rebalance existing positions with new leverage
        for symbol in list(self.positions.keys()):
            target_weight = (leverage / self.max_positions)
            current = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value
            if abs(current - target_weight) > 0.08:  # Only rebalance if >8% drift
                self.set_holdings(symbol, target_weight)

        # Check entries
        if len(self.positions) < self.max_positions:
            candidates = []
            for symbol in self.universe_symbols:
                if symbol in self.positions:
                    continue

                if self.check_entry_signal(symbol):
                    mom_6m = self.get_momentum(symbol, 126)
                    mom_3m = self.get_momentum(symbol, 63)
                    if mom_6m is not None and mom_3m is not None:
                        # Combined momentum score favoring recent strength
                        score = mom_6m * 0.5 + mom_3m * 0.5
                        candidates.append((symbol, score))

            candidates.sort(key=lambda x: x[1], reverse=True)

            slots_available = self.max_positions - len(self.positions)
            for symbol, score in candidates[:slots_available]:
                price = self.securities[symbol].price
                weight = leverage / self.max_positions

                self.set_holdings(symbol, weight)
                self.positions[symbol] = {
                    "entry_price": price,
                    "highest_price": price,
                    "entry_date": self.time
                }
