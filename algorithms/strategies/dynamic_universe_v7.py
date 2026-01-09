# region imports
from AlgorithmImports import *
# endregion

class DynamicUniverseV7(QCAlgorithm):
    """
    V7: Quality Momentum

    Combines profitability metrics with momentum:
    - High ROE (> 15%)
    - Positive earnings growth
    - Strong price momentum
    - "Smooth" momentum (consistent, not volatile)

    Based on Alpha Architect's "Quality Momentum" research.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe parameters
        self.min_market_cap = 2_000_000_000     # $2B+ (quality)
        self.max_market_cap = 300_000_000_000   # $300B
        self.min_price = 15
        self.min_dollar_volume = 25_000_000     # $25M/day
        self.universe_size = 30

        # Quality filters
        self.min_roe = 0.12                     # 12%+ ROE
        self.min_profit_margin = 0.08           # 8%+ profit margin

        self.universe_symbols = []
        self.sma_50 = {}
        self.sma_200 = {}
        self.return_history = {}
        self.entry_prices = {}
        self.highest_prices = {}
        self.prev_prices = {}
        self.atr_ind = {}

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter, self.fine_filter)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_returns = []

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.max_positions = 5
        self.max_single_position = 0.22
        self.max_total_exposure = 0.95

        self.stop_pct = 0.10
        self.trailing_pct = 0.12

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

            # QUALITY FILTERS
            try:
                # ROE filter
                roe = x.operation_ratios.roe.value
                if roe is None or roe < self.min_roe:
                    continue

                # Profit margin filter
                net_margin = x.operation_ratios.net_margin.value
                if net_margin is None or net_margin < self.min_profit_margin:
                    continue

            except:
                continue

            # Growth sectors
            try:
                sector = x.asset_classification.morningstar_sector_code
                if sector not in [311, 102, 308, 310, 206]:  # Tech, Consumer, Comm, Industrial, Healthcare
                    continue
            except:
                continue

            filtered.append((x, roe))

        # Sort by ROE (quality first)
        sorted_by_quality = sorted(filtered, key=lambda t: t[1], reverse=True)
        selected = [x[0].symbol for x in sorted_by_quality[:self.universe_size]]
        return selected

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            symbol = security.symbol
            ticker = symbol.value
            if ticker == "SPY" or symbol == self.vix:
                continue

            if ticker not in self.return_history:
                self.return_history[ticker] = []

            if ticker not in self.sma_50:
                self.sma_50[ticker] = SimpleMovingAverage(50)
                self.register_indicator(symbol, self.sma_50[ticker], Resolution.DAILY)

            if ticker not in self.sma_200:
                self.sma_200[ticker] = SimpleMovingAverage(200)
                self.register_indicator(symbol, self.sma_200[ticker], Resolution.DAILY)

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

        if self.spy in data and data[self.spy] is not None:
            spy_price = data[self.spy].close
            if self.spy in self.prev_prices:
                spy_ret = (spy_price - self.prev_prices[self.spy]) / self.prev_prices[self.spy]
                self.spy_returns.append(spy_ret)
                if len(self.spy_returns) > 300:
                    self.spy_returns = self.spy_returns[-300:]
            self.prev_prices[self.spy] = spy_price

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

    def get_momentum_quality(self, ticker):
        """
        Calculate momentum quality - prefer smooth, consistent momentum
        over volatile spikes
        """
        if ticker not in self.return_history:
            return None, None
        rets = self.return_history[ticker]
        if len(rets) < 126:  # Need 6 months
            return None, None

        # 6-month total return
        total_return = sum(rets[-126:])

        # Momentum quality: % of positive days
        positive_days = sum(1 for r in rets[-126:] if r > 0)
        consistency = positive_days / 126

        # Combined score: total return * consistency
        quality_score = total_return * consistency

        return total_return, quality_score

    def is_ma_aligned(self, ticker, price):
        if ticker not in self.sma_50 or not self.sma_50[ticker].is_ready:
            return False
        if ticker not in self.sma_200 or not self.sma_200[ticker].is_ready:
            return False
        sma50 = self.sma_50[ticker].current.value
        sma200 = self.sma_200[ticker].current.value
        return price > sma50 > sma200

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

            if pnl <= -self.stop_pct:
                should_exit = True

            high = self.highest_prices[ticker]
            if price <= high * (1 - self.trailing_pct):
                should_exit = True

            # Exit on MA breakdown
            if ticker in self.sma_50 and self.sma_50[ticker].is_ready:
                if price < self.sma_50[ticker].current.value * 0.97:
                    should_exit = True

            if should_exit:
                self.liquidate(symbol)
                self._cleanup(ticker)

    def _cleanup(self, ticker):
        for d in [self.entry_prices, self.highest_prices]:
            if ticker in d:
                del d[ticker]

    def rebalance(self):
        if self.is_warming_up:
            return

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

            # Must be MA aligned
            if not self.is_ma_aligned(ticker, price):
                continue

            # Get momentum quality score
            total_ret, quality_score = self.get_momentum_quality(ticker)
            if quality_score is None or total_ret < 0.10:  # 10%+ 6-month return
                continue

            candidates.append({
                "ticker": ticker,
                "symbol": symbol,
                "score": quality_score,
                "return": total_ret
            })

        # Sort by quality-adjusted momentum
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
