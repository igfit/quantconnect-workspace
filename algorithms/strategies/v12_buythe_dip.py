"""
v12 BUY THE DIP Strategy

Instead of chasing momentum, buy stocks in uptrends during pullbacks:
1. Stock in long-term uptrend (price > 200 SMA)
2. Short-term dip (price down 5-15% from recent high)
3. RSI oversold (< 40)

This might work better in 2015-2019's steady uptrend.
"""

from AlgorithmImports import *


class V12BuyTheDip(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2019, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Strategy parameters
        self.top_n = 10
        self.min_dollar_volume = 10_000_000

        # Universe
        self.universe_size = 75
        self.min_market_cap = 10e9    # $10B
        self.max_market_cap = 500e9   # $500B
        self.min_price = 20
        self.min_avg_dollar_volume = 30e6

        self.last_universe_refresh = None

        self.active_symbols = []
        self.sma_200 = {}
        self.rsi = {}
        self.max_price = {}  # Track 52-week high
        self.volume_sma = {}

        # Regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.set_warm_up(210, Resolution.DAILY)

        # Check daily for dip opportunities
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.check_for_dips
        )
        self.set_benchmark("SPY")

    def should_refresh(self):
        if self.last_universe_refresh is None:
            return True
        return (self.time - self.last_universe_refresh).days >= 90

    def coarse_filter(self, coarse):
        if not self.should_refresh():
            return Universe.UNCHANGED

        filtered = [x for x in coarse
                   if x.has_fundamental_data
                   and x.price > self.min_price
                   and x.dollar_volume > self.min_avg_dollar_volume]

        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:300]]

    def fine_filter(self, fine):
        if not self.should_refresh():
            return Universe.UNCHANGED

        filtered = [x for x in fine
                   if x.market_cap > self.min_market_cap
                   and x.market_cap < self.max_market_cap]

        # Exclude defensive sectors
        excluded_sectors = [
            MorningstarSectorCode.UTILITIES,
            MorningstarSectorCode.REAL_ESTATE,
        ]

        sector_filtered = [x for x in filtered
                         if x.asset_classification.morningstar_sector_code not in excluded_sectors]

        sorted_stocks = sorted(sector_filtered, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_stocks[:self.universe_size]]

        self.last_universe_refresh = self.time
        self.log(f"Buy dip universe: {len(selected)} stocks at {self.time.date()}")

        return selected

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            symbol = security.symbol
            if symbol == self.spy:
                continue
            if symbol not in self.active_symbols:
                self.active_symbols.append(symbol)
            if symbol not in self.sma_200:
                self.sma_200[symbol] = self.sma(symbol, 200, Resolution.DAILY)
                self.rsi[symbol] = RelativeStrengthIndex(14)
                self.register_indicator(symbol, self.rsi[symbol], Resolution.DAILY)
                self.max_price[symbol] = Maximum(126)
                self.register_indicator(symbol, self.max_price[symbol], Resolution.DAILY)
                self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.active_symbols:
                self.active_symbols.remove(symbol)
            if self.portfolio[symbol].invested:
                self.liquidate(symbol)

    def check_for_dips(self):
        if self.is_warming_up:
            return
        if len(self.active_symbols) == 0:
            return

        # Regime check
        if not self.spy_sma_200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        if spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            return

        # Count current positions
        current_positions = sum(1 for h in self.portfolio.values()
                               if h.invested and h.symbol != self.spy)

        # Exit positions that recovered
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.active_symbols:
                symbol = holding.symbol
                if symbol in self.rsi and self.rsi[symbol].is_ready:
                    # Exit when RSI > 60 (recovered)
                    if self.rsi[symbol].current.value > 60:
                        self.liquidate(symbol)
                        current_positions -= 1

        # Look for dip opportunities
        if current_positions >= self.top_n:
            return

        dip_candidates = []
        for symbol in self.active_symbols:
            if self.portfolio[symbol].invested:
                continue

            if not self.securities[symbol].has_data:
                continue
            if symbol not in self.sma_200 or not self.sma_200[symbol].is_ready:
                continue
            if symbol not in self.rsi or not self.rsi[symbol].is_ready:
                continue
            if symbol not in self.max_price or not self.max_price[symbol].is_ready:
                continue

            price = self.securities[symbol].price
            sma200 = self.sma_200[symbol].current.value
            rsi_val = self.rsi[symbol].current.value
            recent_high = self.max_price[symbol].current.value

            # Skip if no valid data
            if sma200 <= 0 or recent_high <= 0:
                continue

            # DIP CONDITIONS:
            # 1. Price above 200 SMA (uptrend)
            if price <= sma200:
                continue

            # 2. Price 5-20% below recent high (pullback)
            drawdown = (recent_high - price) / recent_high
            if drawdown < 0.05 or drawdown > 0.20:
                continue

            # 3. RSI < 45 (oversold territory)
            if rsi_val >= 45:
                continue

            # Score by depth of dip (more oversold = better)
            dip_score = drawdown * (50 - rsi_val)
            dip_candidates.append((symbol, dip_score))

        if len(dip_candidates) == 0:
            return

        # Buy best dip candidates
        dip_candidates.sort(key=lambda x: x[1], reverse=True)
        available_slots = self.top_n - current_positions

        for symbol, score in dip_candidates[:available_slots]:
            target_weight = 1.0 / self.top_n
            self.set_holdings(symbol, target_weight)
