# region imports
from AlgorithmImports import *
# endregion

class ClassicMomentumV9(QCAlgorithm):
    """
    V9: Classic Academic Momentum (12-1)

    Pure momentum strategy based on academic research:
    - Select top 10 stocks by 12-month return (skip last month)
    - Equal weight
    - Monthly rebalance
    - Minimal filters (liquidity + price)

    This is the benchmark momentum strategy from Jegadeesh & Titman.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Minimal filters
        self.min_market_cap = 500_000_000      # $500M+
        self.min_price = 5
        self.min_dollar_volume = 5_000_000     # $5M/day
        self.universe_size = 100               # Large universe to pick from
        self.top_n = 10                        # Hold top 10 momentum stocks

        self.universe_symbols = []
        self.price_history = {}
        self.monthly_returns = {}

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter, self.fine_filter)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        # Monthly rebalance on first trading day
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.monthly_rebalance
        )

        self.set_benchmark("SPY")
        self.set_warm_up(260, Resolution.DAILY)

        self.holdings = {}

    def coarse_filter(self, coarse):
        if self.is_warming_up:
            return []

        filtered = [x for x in coarse
                    if x.has_fundamental_data
                    and x.price > self.min_price
                    and x.dollar_volume > self.min_dollar_volume]

        # Sort by dollar volume for liquidity
        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        return [x.symbol for x in sorted_by_volume[:500]]  # Top 500 liquid

    def fine_filter(self, fine):
        if self.is_warming_up:
            return []

        filtered = []
        for x in fine:
            if x.market_cap < self.min_market_cap:
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

        # Track prices for momentum calculation
        for symbol in self.universe_symbols:
            if symbol in data and data[symbol] is not None:
                price = data[symbol].close
                if symbol not in self.price_history:
                    self.price_history[symbol] = []
                self.price_history[symbol].append(price)
                # Keep 260 days of history
                if len(self.price_history[symbol]) > 260:
                    self.price_history[symbol] = self.price_history[symbol][-260:]

    def get_12_1_momentum(self, symbol):
        """
        Calculate 12-month momentum skipping most recent month
        This is the classic Jegadeesh-Titman momentum measure
        """
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < 252:
            return None

        # Price 12 months ago
        price_12m = prices[-252]
        # Price 1 month ago (skip recent month)
        price_1m = prices[-21]

        if price_12m <= 0:
            return None

        return (price_1m - price_12m) / price_12m

    def monthly_rebalance(self):
        if self.is_warming_up:
            return

        # Market regime check
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready:
            return

        # If bear market, reduce exposure or go to cash
        in_bear_market = spy_price < self.spy_sma_200.current.value

        vix = self.get_vix()
        high_volatility = vix > 35

        if in_bear_market or high_volatility:
            self.liquidate()
            self.holdings = {}
            return

        # Calculate momentum for all stocks
        momentum_scores = []
        for symbol in self.universe_symbols:
            mom = self.get_12_1_momentum(symbol)
            if mom is not None and mom > 0:  # Only positive momentum
                momentum_scores.append((symbol, mom))

        # Sort by momentum and take top N
        momentum_scores.sort(key=lambda x: x[1], reverse=True)
        top_stocks = momentum_scores[:self.top_n]

        if len(top_stocks) == 0:
            self.liquidate()
            self.holdings = {}
            return

        # Equal weight
        weight = 1.0 / len(top_stocks)

        # Liquidate stocks not in top N
        new_holdings = set(s for s, _ in top_stocks)
        for symbol in list(self.holdings.keys()):
            if symbol not in new_holdings:
                self.liquidate(symbol)
                del self.holdings[symbol]

        # Set holdings for top N
        for symbol, mom in top_stocks:
            if symbol in self.securities:
                self.set_holdings(symbol, weight)
                self.holdings[symbol] = weight
