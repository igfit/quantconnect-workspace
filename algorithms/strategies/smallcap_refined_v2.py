# region imports
from AlgorithmImports import *
# endregion

class SmallCapRefinedV2(QCAlgorithm):
    """
    Small-Cap Refined V2: Volume Filter + Category Diversification

    Changes from baseline:
    - Volume filter: Only trade when volume > 20-day average
    - Category diversification: Max 2 positions per sector
    - Relative strength within small-cap universe (not vs SPY)
    - Bi-weekly rebalance (less frequent to avoid churn)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.lookback = 42
        self.beta_lookback = 126

        # Small/Mid-Cap Universe with categories
        self.ticker_categories = {
            # Fintech
            "SOFI": "fintech", "UPST": "fintech", "AFRM": "fintech",
            "HOOD": "fintech", "BILL": "fintech",
            # EV/Clean Energy
            "RIVN": "ev", "LCID": "ev", "PLUG": "ev",
            "FCEL": "ev", "CHPT": "ev",
            # Crypto-adjacent
            "RIOT": "crypto", "MARA": "crypto", "COIN": "crypto",
            # Gaming/Consumer
            "DKNG": "consumer", "RBLX": "consumer", "U": "consumer",
            # Cloud/SaaS
            "NET": "cloud", "DDOG": "cloud", "MDB": "cloud",
            "CRWD": "cloud", "ZS": "cloud", "GTLB": "cloud",
            # Data/AI
            "PLTR": "ai", "PATH": "ai", "SNOW": "ai",
        }
        self.tickers = list(self.ticker_categories.keys())
        self.max_per_category = 2

        self.symbols = {}
        self.return_history = {}
        self.volume_history = {}
        self.adx_ind = {}
        self.atr_ind = {}
        self.entry_prices = {}
        self.entry_atr = {}
        self.highest_prices = {}

        for ticker in self.tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
                sym = equity.symbol
                self.symbols[ticker] = sym
                self.return_history[ticker] = []
                self.volume_history[ticker] = []
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

        self.max_positions = 6
        self.max_single_position = 0.14
        self.max_total_exposure = 0.75
        self.prev_prices = {}

        self.stop_atr_mult = 2.5
        self.trailing_atr_mult = 3.0
        self.trailing_activation = 0.12
        self.vix_entry_threshold = 28
        self.vix_exit_threshold = 35

        # Bi-weekly rebalance
        self.last_rebalance = None
        self.rebalance_days = 10

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.check_rebalance
        )

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 31),
            self.check_exits
        )

        self.set_benchmark("SPY")
        self.set_warm_up(200, Resolution.DAILY)

    def check_rebalance(self):
        if self.last_rebalance is None:
            self.rebalance()
            self.last_rebalance = self.time
        elif (self.time - self.last_rebalance).days >= self.rebalance_days:
            self.rebalance()
            self.last_rebalance = self.time

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
                bar = data[symbol]
                price = bar.close
                volume = bar.volume

                if symbol in self.prev_prices:
                    ret = (price - self.prev_prices[symbol]) / self.prev_prices[symbol]
                    self.return_history[ticker].append(ret)
                    if len(self.return_history[ticker]) > 300:
                        self.return_history[ticker] = self.return_history[ticker][-300:]

                self.volume_history[ticker].append(volume)
                if len(self.volume_history[ticker]) > 30:
                    self.volume_history[ticker] = self.volume_history[ticker][-30:]

                self.prev_prices[symbol] = price

    def is_volume_confirmed(self, ticker):
        """Check if current volume is above 20-day average"""
        if ticker not in self.volume_history:
            return False
        vol_hist = self.volume_history[ticker]
        if len(vol_hist) < 20:
            return False
        avg_vol = sum(vol_hist[-20:]) / 20
        current_vol = vol_hist[-1] if vol_hist else 0
        return current_vol > avg_vol * 0.8  # At least 80% of average

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

    def calculate_momentum(self, ticker):
        """Simple momentum over lookback period"""
        if ticker not in self.return_history:
            return None
        stock_rets = self.return_history[ticker]
        if len(stock_rets) < self.lookback:
            return None
        return sum(stock_rets[-self.lookback:])

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

    def get_category_counts(self):
        """Count positions per category"""
        counts = {}
        for ticker in self.entry_prices.keys():
            if ticker in self.ticker_categories:
                cat = self.ticker_categories[ticker]
                counts[cat] = counts.get(cat, 0) + 1
        return counts

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
            should_exit = False

            if price <= entry - (self.stop_atr_mult * atr):
                should_exit = True

            if pnl >= self.trailing_activation:
                if price <= self.highest_prices[ticker] - (self.trailing_atr_mult * atr):
                    should_exit = True

            if ticker in self.adx_ind and self.adx_ind[ticker].is_ready:
                neg_di = self.adx_ind[ticker].negative_directional_index.current.value
                pos_di = self.adx_ind[ticker].positive_directional_index.current.value
                if neg_di > pos_di + 12:
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

        total_exposure = sum(abs(self.portfolio[self.symbols[t]].holdings_value)
                            for t in self.entry_prices if t in self.symbols) / self.portfolio.total_portfolio_value

        if total_exposure >= self.max_total_exposure:
            return

        category_counts = self.get_category_counts()

        # Calculate relative strength within the universe
        all_momentum = {}
        for ticker in self.symbols.keys():
            mom = self.calculate_momentum(ticker)
            if mom is not None:
                all_momentum[ticker] = mom

        if len(all_momentum) < 5:
            return

        # Get median momentum for relative strength
        sorted_moms = sorted(all_momentum.values())
        median_mom = sorted_moms[len(sorted_moms) // 2]

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

            # Check category limit
            cat = self.ticker_categories.get(ticker, "other")
            if category_counts.get(cat, 0) >= self.max_per_category:
                continue

            # Volume filter
            if not self.is_volume_confirmed(ticker):
                continue

            # Momentum check
            result = self.calculate_residual_momentum(ticker)
            if result is None:
                continue

            residual_mom, beta = result
            if residual_mom <= 0.02:
                continue

            # Must be above median (relative strength)
            abs_mom = all_momentum.get(ticker, 0)
            if abs_mom < median_mom:
                continue

            if ticker in self.adx_ind and self.adx_ind[ticker].is_ready:
                adx = self.adx_ind[ticker].current.value
                pos_di = self.adx_ind[ticker].positive_directional_index.current.value
                neg_di = self.adx_ind[ticker].negative_directional_index.current.value
                if adx < 20 or pos_di <= neg_di:
                    continue
                score = residual_mom * (adx / 100) * beta
            else:
                continue

            position_size = self.calculate_position_size(ticker)
            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "score": score,
                "position_size": position_size,
                "category": cat
            })

        scores.sort(key=lambda x: x["score"], reverse=True)
        slots = self.max_positions - len(self.entry_prices)

        for s in scores[:slots]:
            ticker = s["ticker"]
            symbol = s["symbol"]
            cat = s["category"]

            # Re-check category limit
            if category_counts.get(cat, 0) >= self.max_per_category:
                continue

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
                self.entry_atr[ticker] = price * 0.05
            total_exposure += weight
            category_counts[cat] = category_counts.get(cat, 0) + 1
