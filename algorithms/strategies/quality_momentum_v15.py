# region imports
from AlgorithmImports import *
# endregion

class QualityMomentumV15(QCAlgorithm):
    """
    V15: Quality + Momentum Multi-Factor

    Hypothesis: Quality companies with momentum = sustainable winners
    - High ROE (quality)
    - Low debt (safety)
    - Positive earnings growth
    - Price momentum
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
        self.universe_size = 30
        self.top_n = 5

        # Quality filters
        self.min_roe = 0.15                     # 15%+ ROE
        self.max_debt_equity = 1.0              # D/E < 1

        self.universe_symbols = []
        self.price_history = {}
        self.quality_scores = {}
        self.holdings = {}

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter, self.fine_filter)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.schedule.on(
            self.date_rules.month_start("SPY", 0),  # Monthly rebalance
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
        return [x.symbol for x in sorted_by_volume[:300]]

    def fine_filter(self, fine):
        if self.is_warming_up:
            return []

        filtered = []
        for x in fine:
            if not (self.min_market_cap < x.market_cap < self.max_market_cap):
                continue

            # Quality filters
            try:
                # ROE check
                roe = x.operation_ratios.roe.value
                if roe is None or roe < self.min_roe:
                    continue

                # Debt/Equity check
                debt_equity = x.operation_ratios.long_term_debt_equity_ratio.value
                if debt_equity is not None and debt_equity > self.max_debt_equity:
                    continue

                # Growth sectors preferred but not required
                sector = x.asset_classification.morningstar_sector_code
                if sector in [311, 102, 308, 310, 206]:  # Tech, Consumer, Comm, Industrial, Healthcare
                    quality_score = roe * 1.2  # Bonus for growth sectors
                else:
                    quality_score = roe

                self.quality_scores[x.symbol] = quality_score
                filtered.append(x)
            except:
                continue

        sorted_by_quality = sorted(filtered, key=lambda x: self.quality_scores.get(x.symbol, 0), reverse=True)
        selected = [x.symbol for x in sorted_by_quality[:self.universe_size]]
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
                if len(self.price_history[symbol]) > 200:
                    self.price_history[symbol] = self.price_history[symbol][-200:]

    def get_momentum_6m(self, symbol):
        """6-month momentum"""
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < 126:
            return None
        return (prices[-1] - prices[-126]) / prices[-126]

    def get_momentum_1m(self, symbol):
        """1-month momentum"""
        if symbol not in self.price_history:
            return None
        prices = self.price_history[symbol]
        if len(prices) < 21:
            return None
        return (prices[-1] - prices[-21]) / prices[-21]

    def is_trending_up(self, symbol):
        """Check if price is above 50-day MA"""
        if symbol not in self.price_history:
            return False
        prices = self.price_history[symbol]
        if len(prices) < 50:
            return False
        sma_50 = sum(prices[-50:]) / 50
        return prices[-1] > sma_50

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
        if vix > 32:
            self.liquidate()
            self.holdings = {}
            return

        candidates = []
        for symbol in self.universe_symbols:
            if symbol not in self.securities:
                continue
            price = self.securities[symbol].price
            if price <= 0:
                continue

            # Must have quality score
            quality = self.quality_scores.get(symbol, 0)
            if quality <= 0:
                continue

            # Momentum check
            mom_6m = self.get_momentum_6m(symbol)
            mom_1m = self.get_momentum_1m(symbol)
            if mom_6m is None or mom_1m is None:
                continue

            # Positive momentum required
            if mom_6m < 0.05 or mom_1m < 0:
                continue

            # Must be trending up
            if not self.is_trending_up(symbol):
                continue

            # Combined score: quality * momentum
            score = quality * (1 + mom_6m)
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
