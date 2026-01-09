# region imports
from AlgorithmImports import *
# endregion

class SmallCapV8VolContraction(QCAlgorithm):
    """
    Small-Cap V8: Volatility Contraction Filter

    Key idea: Only enter when stock volatility is CONTRACTING (not expanding)
    - Current ATR must be below 20-day ATR average
    - This avoids entering during volatility spikes (usually bad timing)
    - Volatility contraction often precedes big moves

    Also uses faster exit when volatility expands (danger sign).
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.short_lookback = 30
        self.long_lookback = 84
        self.beta_lookback = 126

        self.tickers = [
            "SOFI", "UPST", "AFRM", "HOOD", "BILL",
            "RIVN", "LCID", "PLUG", "FCEL", "CHPT",
            "RIOT", "MARA", "COIN",
            "DKNG", "RBLX", "U",
            "NET", "DDOG", "MDB", "CRWD", "ZS", "GTLB",
            "PLTR", "PATH", "SNOW",
        ]

        self.symbols = {}
        self.return_history = {}
        self.atr_history = {}  # Track ATR history for contraction detection
        self.adx_ind = {}
        self.atr_ind = {}
        self.entry_prices = {}
        self.entry_atr = {}
        self.entry_avg_atr = {}  # Store average ATR at entry
        self.highest_prices = {}

        for ticker in self.tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
                sym = equity.symbol
                self.symbols[ticker] = sym
                self.return_history[ticker] = []
                self.atr_history[ticker] = []
                self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)
                self.atr_ind[ticker] = self.atr(sym, 14, Resolution.DAILY)
            except:
                pass

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_returns = []

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.max_positions = 5
        self.max_single_position = 0.16
        self.max_total_exposure = 0.75
        self.prev_prices = {}

        self.stop_atr_mult = 2.5
        self.trailing_atr_mult = 3.0
        self.trailing_activation = 0.12
        self.vix_entry_threshold = 28
        self.vix_exit_threshold = 35

        # Volatility contraction parameters
        self.atr_avg_period = 20
        self.vol_contraction_threshold = 0.95  # ATR must be < 95% of average

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

    def is_volatility_contracting(self, ticker):
        """Check if current ATR is below average (volatility contracting)"""
        if ticker not in self.atr_ind or not self.atr_ind[ticker].is_ready:
            return False
        if ticker not in self.atr_history or len(self.atr_history[ticker]) < self.atr_avg_period:
            return False

        current_atr = self.atr_ind[ticker].current.value
        avg_atr = sum(self.atr_history[ticker][-self.atr_avg_period:]) / self.atr_avg_period

        return current_atr < avg_atr * self.vol_contraction_threshold

    def is_volatility_expanding(self, ticker):
        """Check if volatility is expanding (danger sign)"""
        if ticker not in self.atr_ind or not self.atr_ind[ticker].is_ready:
            return False
        if ticker not in self.atr_history or len(self.atr_history[ticker]) < self.atr_avg_period:
            return False

        current_atr = self.atr_ind[ticker].current.value
        avg_atr = sum(self.atr_history[ticker][-self.atr_avg_period:]) / self.atr_avg_period

        return current_atr > avg_atr * 1.3  # 30% above average = expanding

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

        for ticker in self.symbols.keys():
            symbol = self.symbols[ticker]
            if symbol in data and data[symbol] is not None:
                price = data[symbol].close
                if symbol in self.prev_prices:
                    ret = (price - self.prev_prices[symbol]) / self.prev_prices[symbol]
                    self.return_history[ticker].append(ret)
                    if len(self.return_history[ticker]) > 300:
                        self.return_history[ticker] = self.return_history[ticker][-300:]
                self.prev_prices[symbol] = price

                # Track ATR history
                if ticker in self.atr_ind and self.atr_ind[ticker].is_ready:
                    self.atr_history[ticker].append(self.atr_ind[ticker].current.value)
                    if len(self.atr_history[ticker]) > 50:
                        self.atr_history[ticker] = self.atr_history[ticker][-50:]

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
        symbol = self.symbols[ticker]
        price = self.securities[symbol].price
        return self.atr_ind[ticker].current.value / price if price > 0 else 0.04

    def calculate_position_size(self, ticker):
        atr_pct = self.get_atr_pct(ticker)
        target_risk = 0.018
        stop_distance = atr_pct * self.stop_atr_mult
        if stop_distance <= 0:
            return 0.08
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

        for ticker in list(self.entry_prices.keys()):
            if ticker not in self.symbols:
                continue
            symbol = self.symbols[ticker]
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

            # Stop loss
            if price <= entry - (self.stop_atr_mult * atr):
                should_exit = True

            # Trailing stop
            if pnl >= self.trailing_activation:
                if price <= self.highest_prices[ticker] - (self.trailing_atr_mult * atr):
                    should_exit = True

            # KEY EXIT: Volatility expansion = danger, exit faster
            if self.is_volatility_expanding(ticker) and pnl < 0.08:
                # Tighter trailing stop when vol expands
                if price <= self.highest_prices[ticker] - (2.0 * atr):
                    should_exit = True

            # ADX trend reversal
            if ticker in self.adx_ind and self.adx_ind[ticker].is_ready:
                neg_di = self.adx_ind[ticker].negative_directional_index.current.value
                pos_di = self.adx_ind[ticker].positive_directional_index.current.value
                if neg_di > pos_di + 10:
                    should_exit = True

            if should_exit:
                self.liquidate(symbol)
                self._cleanup(ticker)

    def _cleanup(self, ticker):
        for d in [self.entry_prices, self.highest_prices, self.entry_atr, self.entry_avg_atr]:
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

        total_exposure = sum(abs(self.portfolio[self.symbols[t]].holdings_value)
                            for t in self.entry_prices if t in self.symbols) / self.portfolio.total_portfolio_value

        if total_exposure >= self.max_total_exposure:
            return

        scores = []
        for ticker in self.symbols.keys():
            if ticker in self.entry_prices:
                continue

            symbol = self.symbols[ticker]
            if symbol not in self.securities:
                continue
            price = self.securities[symbol].price
            if price <= 0:
                continue

            # KEY FILTER: Only enter when volatility is contracting
            if not self.is_volatility_contracting(ticker):
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
