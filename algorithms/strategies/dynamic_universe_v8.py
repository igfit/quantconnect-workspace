# region imports
from AlgorithmImports import *
# endregion

class DynamicUniverseV8(QCAlgorithm):
    """
    V8: Sector Rotation + Top Stocks

    Strategy:
    1. Identify top 2-3 performing sectors by 3-month momentum
    2. Within those sectors, pick top momentum stocks
    3. Concentrate in winning sectors/stocks

    This captures sector momentum AND individual stock momentum.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Sector ETFs to track sector momentum
        self.sector_etfs = {
            "XLK": 311,  # Tech
            "XLY": 102,  # Consumer Discretionary
            "XLC": 308,  # Communication
            "XLI": 310,  # Industrials
            "XLV": 206,  # Healthcare
            "XLF": 103,  # Financials
        }

        self.sector_symbols = {}
        self.sector_returns = {}

        for etf in self.sector_etfs.keys():
            equity = self.add_equity(etf, Resolution.DAILY)
            self.sector_symbols[etf] = equity.symbol
            self.sector_returns[etf] = []

        # Universe parameters
        self.min_market_cap = 2_000_000_000     # $2B+
        self.max_market_cap = 200_000_000_000   # $200B
        self.min_price = 15
        self.min_dollar_volume = 20_000_000
        self.universe_size = 30

        self.universe_symbols = []
        self.stock_sector = {}
        self.sma_20 = {}
        self.sma_50 = {}
        self.return_history = {}
        self.entry_prices = {}
        self.highest_prices = {}
        self.prev_prices = {}

        self.universe_settings.resolution = Resolution.DAILY
        self.add_universe(self.coarse_filter, self.fine_filter)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.max_positions = 4
        self.max_single_position = 0.27
        self.max_total_exposure = 0.95

        self.stop_pct = 0.10
        self.trailing_pct = 0.12

        # Hot sectors (updated each rebalance)
        self.hot_sectors = []

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
        self.set_warm_up(100, Resolution.DAILY)

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
            if not (self.min_market_cap < x.market_cap < self.max_market_cap):
                continue

            try:
                sector = x.asset_classification.morningstar_sector_code
                # Only consider sectors we track
                if sector not in self.sector_etfs.values():
                    continue
                filtered.append((x, sector))
            except:
                continue

        sorted_by_volume = sorted(filtered, key=lambda t: t[0].dollar_volume, reverse=True)
        selected = []
        for x, sector in sorted_by_volume[:self.universe_size]:
            selected.append(x.symbol)
            self.stock_sector[x.symbol.value] = sector

        return selected

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            symbol = security.symbol
            ticker = symbol.value
            if ticker in self.sector_etfs or ticker == "SPY" or symbol == self.vix:
                continue

            if ticker not in self.return_history:
                self.return_history[ticker] = []

            if ticker not in self.sma_20:
                self.sma_20[ticker] = SimpleMovingAverage(20)
                self.register_indicator(symbol, self.sma_20[ticker], Resolution.DAILY)

            if ticker not in self.sma_50:
                self.sma_50[ticker] = SimpleMovingAverage(50)
                self.register_indicator(symbol, self.sma_50[ticker], Resolution.DAILY)

        self.universe_symbols = [s for s in self.active_securities.keys()
                                  if s != self.spy and s != self.vix
                                  and s.value not in self.sector_etfs]

    def get_vix(self):
        if self.vix in self.securities and self.securities[self.vix].price > 0:
            return self.securities[self.vix].price
        return 20

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Track sector ETF returns
        for etf, symbol in self.sector_symbols.items():
            if symbol in data and data[symbol] is not None:
                price = data[symbol].close
                if symbol in self.prev_prices and self.prev_prices[symbol] > 0:
                    ret = (price - self.prev_prices[symbol]) / self.prev_prices[symbol]
                    self.sector_returns[etf].append(ret)
                    if len(self.sector_returns[etf]) > 100:
                        self.sector_returns[etf] = self.sector_returns[etf][-100:]
                self.prev_prices[symbol] = price

        # Track stock returns
        for symbol in self.universe_symbols:
            ticker = symbol.value
            if symbol in data and data[symbol] is not None:
                price = data[symbol].close
                if symbol in self.prev_prices and self.prev_prices[symbol] > 0:
                    ret = (price - self.prev_prices[symbol]) / self.prev_prices[symbol]
                    if ticker not in self.return_history:
                        self.return_history[ticker] = []
                    self.return_history[ticker].append(ret)
                    if len(self.return_history[ticker]) > 200:
                        self.return_history[ticker] = self.return_history[ticker][-200:]
                self.prev_prices[symbol] = price

    def update_hot_sectors(self):
        """Identify top 2 sectors by 3-month momentum"""
        sector_momentum = {}
        for etf in self.sector_etfs.keys():
            rets = self.sector_returns.get(etf, [])
            if len(rets) >= 63:
                mom = sum(rets[-63:])  # 3-month return
                sector_momentum[etf] = mom

        if len(sector_momentum) < 2:
            self.hot_sectors = list(self.sector_etfs.values())
            return

        # Top 2 sectors
        sorted_sectors = sorted(sector_momentum.items(), key=lambda x: x[1], reverse=True)
        self.hot_sectors = [self.sector_etfs[etf] for etf, _ in sorted_sectors[:2]]

    def get_stock_momentum(self, ticker):
        if ticker not in self.return_history:
            return None
        rets = self.return_history[ticker]
        if len(rets) < 63:
            return None
        return sum(rets[-63:])  # 3-month return

    def is_trending_up(self, ticker, price):
        if ticker not in self.sma_20 or not self.sma_20[ticker].is_ready:
            return False
        if ticker not in self.sma_50 or not self.sma_50[ticker].is_ready:
            return False
        sma20 = self.sma_20[ticker].current.value
        sma50 = self.sma_50[ticker].current.value
        return price > sma20 > sma50

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

            # Exit if sector falls out of top 2
            if ticker in self.stock_sector:
                sector = self.stock_sector[ticker]
                if sector not in self.hot_sectors and pnl < 0.05:
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

        # Update hot sectors
        self.update_hot_sectors()

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

            # Must be in hot sector
            if ticker not in self.stock_sector:
                continue
            if self.stock_sector[ticker] not in self.hot_sectors:
                continue

            if symbol not in self.securities:
                continue
            price = self.securities[symbol].price
            if price <= 0:
                continue

            if not self.is_trending_up(ticker, price):
                continue

            mom = self.get_stock_momentum(ticker)
            if mom is None or mom < 0.10:  # 10%+ 3-month return
                continue

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
