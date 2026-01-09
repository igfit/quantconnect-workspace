# region imports
from AlgorithmImports import *
# endregion

class SmallCapDynamicV1(QCAlgorithm):
    """
    V1: Remove sector filter, select by 3-month momentum instead of volume

    Hypothesis: Sector filter was too restrictive. Let momentum select winners.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.short_lookback = 30
        self.long_lookback = 84
        self.beta_lookback = 126
        self.rs_lookback = 21

        # Universe: smaller cap, no sector filter
        self.min_market_cap = 500_000_000      # $500M
        self.max_market_cap = 5_000_000_000    # $5B (tighter range)
        self.min_price = 10                     # Higher price = more established
        self.min_dollar_volume = 10_000_000    # $10M/day (more liquid)
        self.universe_size = 25

        self.universe_symbols = []
        self.return_history = {}
        self.adx_ind = {}
        self.atr_ind = {}
        self.entry_prices = {}
        self.entry_atr = {}
        self.highest_prices = {}
        self.prev_prices = {}
        self.momentum_scores = {}  # Track 3-month momentum for selection

        self.add_universe(self.coarse_filter, self.fine_filter)
        self.universe_settings.resolution = Resolution.DAILY

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_returns = []

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.max_positions = 5
        self.max_single_position = 0.18  # Slightly higher concentration
        self.max_total_exposure = 0.80

        self.stop_atr_mult = 2.5
        self.trailing_atr_mult = 3.0
        self.trailing_activation = 0.10
        self.vix_entry_threshold = 28
        self.vix_exit_threshold = 35
        self.rs_percentile = 0.50

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
        self.set_warm_up(200, Resolution.DAILY)

    def coarse_filter(self, coarse):
        if self.is_warming_up:
            return []

        # Filter and sort by 3-month price change
        filtered = []
        for x in coarse:
            if not x.has_fundamental_data:
                continue
            if x.price < self.min_price:
                continue
            if x.dollar_volume < self.min_dollar_volume:
                continue
            filtered.append(x)

        return [x.symbol for x in filtered]

    def fine_filter(self, fine):
        if self.is_warming_up:
            return []

        filtered = []
        for x in fine:
            # Market cap filter only - no sector restriction
            if not (self.min_market_cap < x.market_cap < self.max_market_cap):
                continue
            filtered.append(x)

        # Sort by dollar volume (proxy for institutional interest)
        sorted_by_volume = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        selected = [x.symbol for x in sorted_by_volume[:self.universe_size]]
        return selected

    def on_securities_changed(self, changes):
        for security in changes.added_securities:
            symbol = security.symbol
            ticker = symbol.value
            if ticker == "SPY" or symbol == self.vix:
                continue
            if ticker not in self.return_history:
                self.return_history[ticker] = []
            if ticker not in self.adx_ind:
                self.adx_ind[ticker] = AverageDirectionalIndex(14)
                self.register_indicator(symbol, self.adx_ind[ticker], Resolution.DAILY)
            if ticker not in self.atr_ind:
                self.atr_ind[ticker] = AverageTrueRange(14)
                self.register_indicator(symbol, self.atr_ind[ticker], Resolution.DAILY)

        self.universe_symbols = [s for s in self.active_securities.keys()
                                  if s != self.spy and s != self.vix]

    def calculate_universe_returns(self):
        returns = {}
        for symbol in self.universe_symbols:
            ticker = symbol.value
            if ticker not in self.return_history:
                continue
            rets = self.return_history[ticker]
            if len(rets) >= self.rs_lookback:
                total_ret = sum(rets[-self.rs_lookback:])
                returns[ticker] = total_ret
        return returns

    def get_rs_leaders(self):
        returns = self.calculate_universe_returns()
        if len(returns) < 5:
            return set(r for r in returns.keys())
        sorted_tickers = sorted(returns.keys(), key=lambda x: returns[x], reverse=True)
        cutoff = int(len(sorted_tickers) * self.rs_percentile)
        cutoff = max(cutoff, 5)
        return set(sorted_tickers[:cutoff])

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

    def calculate_beta(self, stock_returns, market_returns):
        if len(stock_returns) < 60 or len(market_returns) < 60:
            return 1.5
        n = min(len(stock_returns), len(market_returns), self.beta_lookback)
        stock = stock_returns[-n:]
        market = market_returns[-n:]
        mean_stock = sum(stock) / len(stock)
        mean_market = sum(market) / len(market)
        cov = sum((s - mean_stock) * (m - mean_market) for s, m in zip(stock, market)) / len(stock)
        var_market = sum((m - mean_market) ** 2 for m in market) / len(market)
        return cov / var_market if var_market > 0 else 1.5

    def calculate_residual_momentum(self, ticker, lookback):
        if ticker not in self.return_history:
            return None
        stock_rets = self.return_history[ticker]
        if len(stock_rets) < lookback or len(self.spy_returns) < lookback:
            return None
        beta = self.calculate_beta(stock_rets, self.spy_returns)
        residuals = []
        n = min(len(stock_rets), len(self.spy_returns), lookback)
        for i in range(-n, 0):
            residual = stock_rets[i] - beta * self.spy_returns[i]
            residuals.append(residual)
        return sum(residuals), beta

    def is_momentum_accelerating(self, ticker):
        short_result = self.calculate_residual_momentum(ticker, self.short_lookback)
        long_result = self.calculate_residual_momentum(ticker, self.long_lookback)
        if short_result is None or long_result is None:
            return False, None, None
        short_mom, beta = short_result
        long_mom, _ = long_result
        short_mom_norm = short_mom / self.short_lookback
        long_mom_norm = long_mom / self.long_lookback
        is_accelerating = short_mom > 0 and short_mom_norm > long_mom_norm
        return is_accelerating, short_mom, beta

    def get_atr_pct(self, ticker):
        if ticker not in self.atr_ind or not self.atr_ind[ticker].is_ready:
            return 0.04
        symbol = Symbol.create(ticker, SecurityType.EQUITY, Market.USA)
        if symbol not in self.securities:
            return 0.04
        price = self.securities[symbol].price
        return self.atr_ind[ticker].current.value / price if price > 0 else 0.04

    def calculate_position_size(self, ticker):
        atr_pct = self.get_atr_pct(ticker)
        target_risk = 0.02  # Slightly higher risk per trade
        stop_distance = atr_pct * self.stop_atr_mult
        if stop_distance <= 0:
            return 0.10
        position_size = target_risk / stop_distance
        vix = self.get_vix()
        if vix > 18:
            vix_scale = max(0.4, 1.0 - (vix - 18) / 22)
            position_size *= vix_scale
        return min(position_size, self.max_single_position)

    def check_exits(self):
        if self.is_warming_up:
            return

        vix = self.get_vix()
        if vix > self.vix_exit_threshold:
            self.liquidate()
            for t in list(self.entry_prices.keys()):
                self._cleanup(t)
            return

        leaders = self.get_rs_leaders()

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

            atr = self.entry_atr.get(ticker, entry * 0.04)
            should_exit = False

            if price <= entry - (self.stop_atr_mult * atr):
                should_exit = True

            if pnl >= self.trailing_activation:
                if price <= self.highest_prices[ticker] - (self.trailing_atr_mult * atr):
                    should_exit = True

            if ticker not in leaders and pnl < 0.03:
                should_exit = True

            if ticker in self.adx_ind and self.adx_ind[ticker].is_ready:
                neg_di = self.adx_ind[ticker].negative_directional_index.current.value
                pos_di = self.adx_ind[ticker].positive_directional_index.current.value
                if neg_di > pos_di + 12:
                    should_exit = True

            short_result = self.calculate_residual_momentum(ticker, self.short_lookback)
            if short_result is not None and short_result[0] < -0.025:
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

        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            for t in list(self.entry_prices.keys()):
                self._cleanup(t)
            return

        vix = self.get_vix()
        if vix > self.vix_entry_threshold:
            return

        total_exposure = sum(
            abs(self.portfolio[Symbol.create(t, SecurityType.EQUITY, Market.USA)].holdings_value)
            for t in self.entry_prices
            if Symbol.create(t, SecurityType.EQUITY, Market.USA) in self.securities
        ) / self.portfolio.total_portfolio_value

        if total_exposure >= self.max_total_exposure:
            return

        leaders = self.get_rs_leaders()

        scores = []
        for symbol in self.universe_symbols:
            ticker = symbol.value

            if ticker in self.entry_prices:
                continue

            if ticker not in leaders:
                continue

            if symbol not in self.securities:
                continue
            price = self.securities[symbol].price
            if price <= 0:
                continue

            is_accelerating, short_mom, beta = self.is_momentum_accelerating(ticker)
            if not is_accelerating or short_mom is None:
                continue

            if short_mom <= 0.015:
                continue

            if ticker in self.adx_ind and self.adx_ind[ticker].is_ready:
                adx = self.adx_ind[ticker].current.value
                pos_di = self.adx_ind[ticker].positive_directional_index.current.value
                neg_di = self.adx_ind[ticker].negative_directional_index.current.value
                if adx < 18 or pos_di <= neg_di:
                    continue
                score = short_mom * (adx / 100) * beta
            else:
                score = short_mom * beta

            position_size = self.calculate_position_size(ticker)
            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "score": score,
                "position_size": position_size
            })

        scores.sort(key=lambda x: x["score"], reverse=True)
        slots = self.max_positions - len(self.entry_prices)

        for s in scores[:slots]:
            ticker = s["ticker"]
            symbol = s["symbol"]
            price = self.securities[symbol].price
            weight = s["position_size"]

            if total_exposure + weight > self.max_total_exposure:
                weight = max(0.05, self.max_total_exposure - total_exposure)
            if weight < 0.05:
                continue

            self.set_holdings(symbol, weight)
            self.entry_prices[ticker] = price
            self.highest_prices[ticker] = price
            if ticker in self.atr_ind and self.atr_ind[ticker].is_ready:
                self.entry_atr[ticker] = self.atr_ind[ticker].current.value
            else:
                self.entry_atr[ticker] = price * 0.04
            total_exposure += weight
