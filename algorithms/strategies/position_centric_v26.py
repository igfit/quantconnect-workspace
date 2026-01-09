# region imports
from AlgorithmImports import *
# endregion

class PositionCentricV26(QCAlgorithm):
    """
    V26: Position-Centric Daily Signal Strategy

    Key difference from portfolio-centric:
    - No fixed rebalance schedule
    - Each stock monitored independently every day
    - Entry/exit signals trigger on daily conditions
    - Portfolio is collection of independent positions

    Entry signal (checked daily for non-held stocks):
    - 6-month momentum > 20%
    - Price > 20-day SMA
    - 5-day momentum > 0 (recent strength)
    - ADX > 20 (trending)

    Exit signal (checked daily for held stocks):
    - Price < 20-day SMA
    - OR 5-day momentum < -8%
    - OR trailing stop hit (15% from high)
    - OR momentum reversal (1-month return < -10%)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe
        self.min_market_cap = 10_000_000_000    # $10B+
        self.max_market_cap = 2_000_000_000_000
        self.min_price = 20
        self.min_dollar_volume = 50_000_000
        self.universe_size = 50
        self.max_positions = 5

        # Entry parameters
        self.entry_mom_6m = 0.20        # 20% 6-month momentum
        self.entry_mom_5d = 0.00        # Positive 5-day momentum
        self.entry_adx = 20             # ADX > 20 (trending)

        # Exit parameters
        self.trailing_stop_pct = 0.15   # 15% trailing stop
        self.exit_mom_5d = -0.08        # -8% 5-day drop
        self.exit_mom_1m = -0.10        # -10% 1-month drop

        # Position tracking
        self.universe_symbols = []
        self.price_history = {}
        self.positions = {}  # {symbol: {entry_price, highest_price, entry_date}}
        self.sma_20 = {}
        self.adx_ind = {}

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter, self.fine_filter)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        # Daily signal check - the core of position-centric approach
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

            if symbol not in self.sma_20:
                self.sma_20[symbol] = self.sma(symbol, 20, Resolution.DAILY)

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

                # Update highest price for trailing stop
                if symbol in self.positions:
                    self.positions[symbol]["highest_price"] = max(
                        self.positions[symbol]["highest_price"], price
                    )

    def get_momentum(self, symbol, days):
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < days:
            return None
        if prices[-days] <= 0:
            return None
        return (prices[-1] - prices[-days]) / prices[-days]

    def check_entry_signal(self, symbol):
        """Check if a stock meets entry criteria"""
        if symbol not in self.securities:
            return False

        price = self.securities[symbol].price
        if price <= 0:
            return False

        # 6-month momentum check
        mom_6m = self.get_momentum(symbol, 126)
        if mom_6m is None or mom_6m < self.entry_mom_6m:
            return False

        # 5-day momentum check (recent strength)
        mom_5d = self.get_momentum(symbol, 5)
        if mom_5d is None or mom_5d < self.entry_mom_5d:
            return False

        # Price above 20 SMA
        if symbol in self.sma_20 and self.sma_20[symbol].is_ready:
            if price < self.sma_20[symbol].current.value:
                return False

        # ADX check (trending)
        if symbol in self.adx_ind and self.adx_ind[symbol].is_ready:
            adx = self.adx_ind[symbol].current.value
            if adx < self.entry_adx:
                return False
            # Also check +DI > -DI (uptrend)
            pos_di = self.adx_ind[symbol].positive_directional_index.current.value
            neg_di = self.adx_ind[symbol].negative_directional_index.current.value
            if pos_di <= neg_di:
                return False

        return True

    def check_exit_signal(self, symbol):
        """Check if a stock meets exit criteria"""
        if symbol not in self.securities:
            return True  # Exit if security not available

        if symbol not in self.positions:
            return False

        price = self.securities[symbol].price
        if price <= 0:
            return True

        pos = self.positions[symbol]
        entry_price = pos["entry_price"]
        highest_price = pos["highest_price"]

        # Trailing stop check
        if price < highest_price * (1 - self.trailing_stop_pct):
            return True

        # Price below 20 SMA
        if symbol in self.sma_20 and self.sma_20[symbol].is_ready:
            if price < self.sma_20[symbol].current.value * 0.98:  # 2% buffer
                return True

        # 5-day momentum crash
        mom_5d = self.get_momentum(symbol, 5)
        if mom_5d is not None and mom_5d < self.exit_mom_5d:
            return True

        # 1-month momentum reversal
        mom_1m = self.get_momentum(symbol, 21)
        if mom_1m is not None and mom_1m < self.exit_mom_1m:
            return True

        # ADX trend breakdown
        if symbol in self.adx_ind and self.adx_ind[symbol].is_ready:
            neg_di = self.adx_ind[symbol].negative_directional_index.current.value
            pos_di = self.adx_ind[symbol].positive_directional_index.current.value
            if neg_di > pos_di + 10:  # Strong downtrend
                return True

        return False

    def daily_signal_check(self):
        """Core daily signal check - position-centric approach"""
        if self.is_warming_up:
            return

        # Market regime check
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            # Exit all positions in bear market
            for symbol in list(self.positions.keys()):
                self.liquidate(symbol)
            self.positions = {}
            return

        vix = self.get_vix()
        if vix > 35:
            # Exit all in high volatility
            for symbol in list(self.positions.keys()):
                self.liquidate(symbol)
            self.positions = {}
            return

        # STEP 1: Check exit signals for all held positions
        for symbol in list(self.positions.keys()):
            if self.check_exit_signal(symbol):
                self.liquidate(symbol)
                del self.positions[symbol]

        # STEP 2: Check entry signals for non-held stocks
        if len(self.positions) < self.max_positions:
            # Score potential entries
            candidates = []
            for symbol in self.universe_symbols:
                if symbol in self.positions:
                    continue  # Already holding

                if self.check_entry_signal(symbol):
                    mom_6m = self.get_momentum(symbol, 126)
                    if mom_6m is not None:
                        candidates.append((symbol, mom_6m))

            # Sort by momentum (strongest first)
            candidates.sort(key=lambda x: x[1], reverse=True)

            # Enter positions (up to max)
            slots_available = self.max_positions - len(self.positions)
            for symbol, mom in candidates[:slots_available]:
                price = self.securities[symbol].price

                # Position sizing: equal weight
                weight = 1.0 / self.max_positions

                # VIX scaling
                if vix > 25:
                    weight *= 0.7
                elif vix > 20:
                    weight *= 0.85

                self.set_holdings(symbol, weight)
                self.positions[symbol] = {
                    "entry_price": price,
                    "highest_price": price,
                    "entry_date": self.time
                }
