# region imports
from AlgorithmImports import *
# endregion

class SmallCapRefinedV3(QCAlgorithm):
    """
    Small-Cap Refined V3: Volatility-Adaptive Parameters

    Changes from baseline:
    - Adaptive stops: Based on stock's volatility percentile (1.5x-4x ATR)
    - Adaptive position sizing: More aggressive on lower-vol small-caps
    - Volatility ranking: Prefer lower-volatility small-caps (still high beta)
    - Momentum persistence filter: Require 3 consecutive weeks of positive momentum
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.lookback = 42
        self.beta_lookback = 126

        # Small/Mid-Cap Universe
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
        self.weekly_returns = {}  # For persistence check
        self.adx_ind = {}
        self.atr_ind = {}
        self.entry_prices = {}
        self.entry_atr = {}
        self.entry_vol_mult = {}  # Store volatility multiplier at entry
        self.highest_prices = {}

        for ticker in self.tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
                sym = equity.symbol
                self.symbols[ticker] = sym
                self.return_history[ticker] = []
                self.weekly_returns[ticker] = []
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
        self.weekly_start_prices = {}
        self.day_count = 0

        # Base parameters (will be adjusted per-stock)
        self.base_stop_mult = 2.0
        self.base_trailing_mult = 2.5
        self.trailing_activation = 0.10
        self.vix_entry_threshold = 28
        self.vix_exit_threshold = 35

        self.schedule.on(
            self.date_rules.every([DayOfWeek.MONDAY]),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.schedule.on(
            self.date_rules.every([DayOfWeek.FRIDAY]),
            self.time_rules.before_market_close("SPY", 30),
            self.record_weekly_returns
        )

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 31),
            self.check_exits
        )

        self.set_benchmark("SPY")
        self.set_warm_up(200, Resolution.DAILY)

    def record_weekly_returns(self):
        """Record weekly returns for persistence check"""
        for ticker in self.symbols.keys():
            symbol = self.symbols[ticker]
            if symbol not in self.securities:
                continue
            current_price = self.securities[symbol].price
            if ticker in self.weekly_start_prices and self.weekly_start_prices[ticker] > 0:
                weekly_ret = (current_price - self.weekly_start_prices[ticker]) / self.weekly_start_prices[ticker]
                self.weekly_returns[ticker].append(weekly_ret)
                if len(self.weekly_returns[ticker]) > 10:
                    self.weekly_returns[ticker] = self.weekly_returns[ticker][-10:]
            self.weekly_start_prices[ticker] = current_price

    def has_persistent_momentum(self, ticker):
        """Check if stock has 3+ consecutive positive weeks"""
        if ticker not in self.weekly_returns:
            return False
        weekly = self.weekly_returns[ticker]
        if len(weekly) < 3:
            return False
        # Last 3 weeks positive
        return all(w > 0 for w in weekly[-3:])

    def get_volatility_percentile(self, ticker):
        """Get stock's volatility percentile within universe"""
        all_atr_pct = {}
        for t in self.symbols.keys():
            atr_pct = self.get_atr_pct(t)
            all_atr_pct[t] = atr_pct

        if len(all_atr_pct) < 5:
            return 0.5

        ticker_vol = all_atr_pct.get(ticker, 0.05)
        sorted_vols = sorted(all_atr_pct.values())
        rank = sum(1 for v in sorted_vols if v <= ticker_vol)
        return rank / len(sorted_vols)

    def get_adaptive_stop_mult(self, ticker):
        """
        Higher volatility = wider stops
        Percentile 0 (lowest vol): 1.5x ATR
        Percentile 100 (highest vol): 4x ATR
        """
        pct = self.get_volatility_percentile(ticker)
        return 1.5 + (pct * 2.5)  # Range: 1.5 to 4.0

    def get_vix(self):
        if self.vix in self.securities and self.securities[self.vix].price > 0:
            return self.securities[self.vix].price
        return 20

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Track weekly start prices on Monday
        if self.time.weekday() == 0:
            for ticker in self.symbols.keys():
                symbol = self.symbols[ticker]
                if symbol in data and data[symbol] is not None:
                    self.weekly_start_prices[ticker] = data[symbol].close

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

    def calculate_residual_momentum(self, ticker):
        if ticker not in self.return_history:
            return None
        stock_rets = self.return_history[ticker]
        if len(stock_rets) < self.lookback or len(self.spy_returns) < self.lookback:
            return None
        beta = self.calculate_beta(stock_rets, self.spy_returns)
        residuals = []
        n = min(len(stock_rets), len(self.spy_returns), self.lookback)
        for i in range(-n, 0):
            residual = stock_rets[i] - beta * self.spy_returns[i]
            residuals.append(residual)
        return sum(residuals), beta

    def get_atr_pct(self, ticker):
        if ticker not in self.atr_ind or not self.atr_ind[ticker].is_ready:
            return 0.05
        symbol = self.symbols[ticker]
        price = self.securities[symbol].price
        return self.atr_ind[ticker].current.value / price if price > 0 else 0.05

    def calculate_position_size(self, ticker):
        atr_pct = self.get_atr_pct(ticker)
        vol_pct = self.get_volatility_percentile(ticker)

        # Lower vol stocks get higher target risk
        target_risk = 0.025 - (vol_pct * 0.012)  # Range: 0.013 to 0.025

        stop_mult = self.get_adaptive_stop_mult(ticker)
        stop_distance = atr_pct * stop_mult
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

            atr = self.entry_atr.get(ticker, entry * 0.05)
            stop_mult = self.entry_vol_mult.get(ticker, 2.5)
            trailing_mult = stop_mult * 1.25

            should_exit = False

            if price <= entry - (stop_mult * atr):
                should_exit = True

            if pnl >= self.trailing_activation:
                if price <= self.highest_prices[ticker] - (trailing_mult * atr):
                    should_exit = True

            if ticker in self.adx_ind and self.adx_ind[ticker].is_ready:
                neg_di = self.adx_ind[ticker].negative_directional_index.current.value
                pos_di = self.adx_ind[ticker].positive_directional_index.current.value
                if neg_di > pos_di + 10:
                    should_exit = True

            if should_exit:
                self.liquidate(symbol)
                self._cleanup(ticker)

    def _cleanup(self, ticker):
        for d in [self.entry_prices, self.highest_prices, self.entry_atr, self.entry_vol_mult]:
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

            result = self.calculate_residual_momentum(ticker)
            if result is None:
                continue

            residual_mom, beta = result
            if residual_mom <= 0.02:
                continue

            # Require persistent momentum for small-caps
            if not self.has_persistent_momentum(ticker):
                continue

            if ticker in self.adx_ind and self.adx_ind[ticker].is_ready:
                adx = self.adx_ind[ticker].current.value
                pos_di = self.adx_ind[ticker].positive_directional_index.current.value
                neg_di = self.adx_ind[ticker].negative_directional_index.current.value
                if adx < 20 or pos_di <= neg_di:
                    continue

                # Penalize highest volatility stocks (prefer lower vol small-caps)
                vol_pct = self.get_volatility_percentile(ticker)
                vol_penalty = 1.0 - (vol_pct * 0.3)  # 0.7 to 1.0

                score = residual_mom * (adx / 100) * beta * vol_penalty
            else:
                continue

            position_size = self.calculate_position_size(ticker)
            stop_mult = self.get_adaptive_stop_mult(ticker)

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "score": score,
                "position_size": position_size,
                "stop_mult": stop_mult
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
            self.entry_vol_mult[ticker] = s["stop_mult"]
            if ticker in self.atr_ind and self.atr_ind[ticker].is_ready:
                self.entry_atr[ticker] = self.atr_ind[ticker].current.value
            else:
                self.entry_atr[ticker] = price * 0.05
            total_exposure += weight
