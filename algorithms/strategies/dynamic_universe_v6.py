# region imports
from AlgorithmImports import *
# endregion

class DynamicUniverseV6(QCAlgorithm):
    """
    V6: 52-Week High Proximity + MA Alignment

    Based on academic research:
    - George & Hwang: Stocks near 52-week highs outperform
    - 12-1 momentum: Skip most recent month to avoid reversal
    - MA alignment: Price > 50 SMA > 200 SMA

    Universe: Selected QUARTERLY (less frequent = more stable)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe parameters
        self.min_market_cap = 1_000_000_000     # $1B+ (established)
        self.max_market_cap = 500_000_000_000   # $500B
        self.min_price = 10
        self.min_dollar_volume = 20_000_000     # $20M/day
        self.universe_size = 25

        # Strategy parameters
        self.lookback_52w = 252
        self.high_proximity_pct = 0.15          # Within 15% of 52-week high
        self.min_12m_return = 0.20              # 20%+ 12-month return

        self.universe_symbols = []
        self.sma_50 = {}
        self.sma_200 = {}
        self.high_52w = {}
        self.return_history = {}
        self.entry_prices = {}
        self.highest_prices = {}
        self.prev_prices = {}
        self.atr_ind = {}
        self.entry_atr = {}

        # Universe selection - quarterly
        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter, self.fine_filter)

        # SPY for regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_returns = []

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        # Position sizing
        self.max_positions = 5
        self.max_single_position = 0.22
        self.max_total_exposure = 0.95

        # Stops
        self.stop_pct = 0.12                    # 12% stop loss
        self.trailing_pct = 0.15               # 15% trailing from high

        self.schedule.on(
            self.date_rules.every([DayOfWeek.MONDAY]),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 31),
            self.check_exits
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

        return [x.symbol for x in filtered]

    def fine_filter(self, fine):
        if self.is_warming_up:
            return []

        filtered = []
        for x in fine:
            # Market cap filter
            if not (self.min_market_cap < x.market_cap < self.max_market_cap):
                continue

            # Growth sectors
            try:
                sector = x.asset_classification.morningstar_sector_code
                if sector not in [311, 102, 308, 310]:  # Tech, Consumer, Comm, Industrial
                    continue
            except:
                continue

            filtered.append(x)

        # Sort by dollar volume
        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_by_volume[:50]]  # Take top 50 for further filtering
        return selected

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            symbol = security.symbol
            ticker = symbol.value
            if ticker == "SPY" or symbol == self.vix:
                continue

            if ticker not in self.return_history:
                self.return_history[ticker] = []

            # Create MAs for each stock
            if ticker not in self.sma_50:
                self.sma_50[ticker] = SimpleMovingAverage(50)
                self.register_indicator(symbol, self.sma_50[ticker], Resolution.DAILY)

            if ticker not in self.sma_200:
                self.sma_200[ticker] = SimpleMovingAverage(200)
                self.register_indicator(symbol, self.sma_200[ticker], Resolution.DAILY)

            if ticker not in self.high_52w:
                self.high_52w[ticker] = Maximum(252)
                self.register_indicator(symbol, self.high_52w[ticker], Resolution.DAILY)

            if ticker not in self.atr_ind:
                self.atr_ind[ticker] = AverageTrueRange(14)
                self.register_indicator(symbol, self.atr_ind[ticker], Resolution.DAILY)

        self.universe_symbols = [s for s in self.active_securities.keys()
                                  if s != self.spy and s != self.vix]

    def get_vix(self):
        if self.vix in self.securities and self.securities[self.vix].price > 0:
            return self.securities[self.vix].price
        return 20

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Track SPY returns
        if self.spy in data and data[self.spy] is not None:
            spy_price = data[self.spy].close
            if self.spy in self.prev_prices:
                spy_ret = (spy_price - self.prev_prices[self.spy]) / self.prev_prices[self.spy]
                self.spy_returns.append(spy_ret)
                if len(self.spy_returns) > 300:
                    self.spy_returns = self.spy_returns[-300:]
            self.prev_prices[self.spy] = spy_price

        # Track returns for universe
        for symbol in self.universe_symbols:
            ticker = symbol.value
            if symbol in data and data[symbol] is not None:
                price = data[symbol].close
                if symbol in self.prev_prices and self.prev_prices[symbol] > 0:
                    ret = (price - self.prev_prices[symbol]) / self.prev_prices[symbol]
                    if ticker not in self.return_history:
                        self.return_history[ticker] = []
                    self.return_history[ticker].append(ret)
                    if len(self.return_history[ticker]) > 300:
                        self.return_history[ticker] = self.return_history[ticker][-300:]
                self.prev_prices[symbol] = price

    def is_near_52w_high(self, ticker, price):
        """Check if price is within X% of 52-week high"""
        if ticker not in self.high_52w or not self.high_52w[ticker].is_ready:
            return False
        high = self.high_52w[ticker].current.value
        if high <= 0:
            return False
        pct_from_high = (high - price) / high
        return pct_from_high <= self.high_proximity_pct

    def is_ma_aligned(self, ticker, price):
        """Check if Price > 50 SMA > 200 SMA"""
        if ticker not in self.sma_50 or not self.sma_50[ticker].is_ready:
            return False
        if ticker not in self.sma_200 or not self.sma_200[ticker].is_ready:
            return False
        sma50 = self.sma_50[ticker].current.value
        sma200 = self.sma_200[ticker].current.value
        return price > sma50 > sma200

    def get_12_1_momentum(self, ticker):
        """12-month momentum skipping most recent month (avoid reversal)"""
        if ticker not in self.return_history:
            return None
        rets = self.return_history[ticker]
        if len(rets) < 252:
            return None
        # Sum returns from day -252 to day -21 (skip last month)
        mom_12_1 = sum(rets[-252:-21])
        return mom_12_1

    def check_exits(self):
        if self.is_warming_up:
            return

        vix = self.get_vix()
        if vix > 40:
            self.liquidate()
            for t in list(self.entry_prices.keys()):
                self._cleanup(t)
            return

        for ticker in list(self.entry_prices.keys()):
            symbol = Symbol.create(ticker, SecurityType.EQUITY, Market.USA)
            if symbol not in self.securities:
                self._cleanup(ticker)
                continue
            if not self.portfolio[symbol].invested:
                self._cleanup(ticker)
                continue

            price = self.securities[symbol].price
            entry = self.entry_prices[ticker]
            pnl = (price - entry) / entry

            if ticker not in self.highest_prices:
                self.highest_prices[ticker] = price
            self.highest_prices[ticker] = max(self.highest_prices[ticker], price)

            should_exit = False

            # Stop loss
            if pnl <= -self.stop_pct:
                should_exit = True

            # Trailing stop
            high = self.highest_prices[ticker]
            if price <= high * (1 - self.trailing_pct):
                should_exit = True

            # MA breakdown - exit if price < 50 SMA
            if ticker in self.sma_50 and self.sma_50[ticker].is_ready:
                if price < self.sma_50[ticker].current.value * 0.98:
                    should_exit = True

            if should_exit:
                self.liquidate(symbol)
                self._cleanup(ticker)

    def _cleanup(self, ticker):
        for d in [self.entry_prices, self.highest_prices, self.entry_atr]:
            if ticker in d:
                del d[ticker]

    def rebalance(self):
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            for t in list(self.entry_prices.keys()):
                self._cleanup(t)
            return

        vix = self.get_vix()
        if vix > 30:
            return

        total_exposure = sum(
            abs(self.portfolio[Symbol.create(t, SecurityType.EQUITY, Market.USA)].holdings_value)
            for t in self.entry_prices
            if Symbol.create(t, SecurityType.EQUITY, Market.USA) in self.securities
        ) / self.portfolio.total_portfolio_value

        if total_exposure >= self.max_total_exposure:
            return

        # Score candidates
        candidates = []
        for symbol in self.universe_symbols:
            ticker = symbol.value

            if ticker in self.entry_prices:
                continue

            if symbol not in self.securities:
                continue
            price = self.securities[symbol].price
            if price <= 0:
                continue

            # Filter 1: Near 52-week high
            if not self.is_near_52w_high(ticker, price):
                continue

            # Filter 2: MA alignment
            if not self.is_ma_aligned(ticker, price):
                continue

            # Filter 3: Strong 12-1 momentum
            mom = self.get_12_1_momentum(ticker)
            if mom is None or mom < self.min_12m_return:
                continue

            # Score by momentum strength
            candidates.append({
                "ticker": ticker,
                "symbol": symbol,
                "score": mom
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        slots = self.max_positions - len(self.entry_prices)

        for c in candidates[:slots]:
            ticker = c["ticker"]
            symbol = c["symbol"]
            price = self.securities[symbol].price
            weight = self.max_single_position

            if total_exposure + weight > self.max_total_exposure:
                weight = max(0.10, self.max_total_exposure - total_exposure)
            if weight < 0.10:
                continue

            self.set_holdings(symbol, weight)
            self.entry_prices[ticker] = price
            self.highest_prices[ticker] = price
            total_exposure += weight
