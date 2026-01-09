# region imports
from AlgorithmImports import *
# endregion

class LargeCapLowDD(QCAlgorithm):
    """
    Large-Cap High-Beta with DD Reduction

    Based on ResidualHighBetaR16 (Sharpe 1.404, CAGR 49%, MaxDD 25.7%)
    but with additional risk controls to reduce drawdown further.

    Target: Sharpe > 1.2, MaxDD < 20%
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.lookback = 42
        self.beta_lookback = 126

        # Large-Cap High-Beta Universe (from R16)
        self.tickers = [
            "TSLA", "NVDA", "AMD", "META", "NFLX", "CRM",
            "AMZN", "AVGO", "GS", "CAT", "AAPL", "MSFT", "GOOGL",
            "COIN", "MSTR"  # Ultra high beta
        ]

        self.symbols = {}
        self.return_history = {}
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
                self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)
                self.atr_ind[ticker] = self.atr(sym, 14, Resolution.DAILY)
            except:
                self.debug(f"Could not add {ticker}")

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_sma_50 = self.sma(self.spy, 50, Resolution.DAILY)
        self.spy_returns = []

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.max_positions = 5
        self.max_single_position = 0.18
        self.max_total_exposure = 0.80
        self.prev_prices = {}

        # Risk parameters
        self.stop_atr_mult = 2.0
        self.trailing_atr_mult = 2.5
        self.trailing_activation = 0.10
        self.vix_entry_threshold = 25
        self.vix_exit_threshold = 32

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

        if var_market == 0:
            return 1.5
        return cov / var_market

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
            return 0.03

        symbol = self.symbols[ticker]
        price = self.securities[symbol].price
        if price <= 0:
            return 0.03

        atr = self.atr_ind[ticker].current.value
        return atr / price

    def calculate_position_size(self, ticker):
        atr_pct = self.get_atr_pct(ticker)

        # Target risk per position: 2% of portfolio
        target_risk = 0.02

        stop_distance = atr_pct * self.stop_atr_mult
        if stop_distance <= 0:
            return 0.10

        position_size = target_risk / stop_distance

        # VIX scaling
        vix = self.get_vix()
        if vix > 20:
            vix_scale = max(0.5, 1.0 - (vix - 20) / 25)
            position_size *= vix_scale

        position_size = min(position_size, self.max_single_position)
        return position_size

    def check_exits(self):
        if self.is_warming_up:
            return

        vix = self.get_vix()
        if vix > self.vix_exit_threshold:
            self.debug(f"{self.time.date()}: VIX EXIT ({vix:.1f})")
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

            atr = self.entry_atr.get(ticker, entry * 0.03)

            should_exit = False
            reason = ""

            # ATR-based stop
            stop_price = entry - (self.stop_atr_mult * atr)
            if price <= stop_price:
                should_exit = True
                reason = f"ATR_STOP({pnl:.1%})"

            # ATR-based trailing stop
            if pnl >= self.trailing_activation:
                trail_stop = self.highest_prices[ticker] - (self.trailing_atr_mult * atr)
                if price <= trail_stop:
                    should_exit = True
                    reason = f"ATR_TRAIL({pnl:+.1%})"

            # ADX trend reversal
            if ticker in self.adx_ind and self.adx_ind[ticker].is_ready:
                neg_di = self.adx_ind[ticker].negative_directional_index.current.value
                pos_di = self.adx_ind[ticker].positive_directional_index.current.value
                if neg_di > pos_di + 10:
                    should_exit = True
                    reason = f"TREND_REV({pnl:+.1%})"

            if should_exit:
                self.liquidate(symbol)
                self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                self._cleanup(ticker)

    def _cleanup(self, ticker):
        if ticker in self.entry_prices:
            del self.entry_prices[ticker]
        if ticker in self.highest_prices:
            del self.highest_prices[ticker]
        if ticker in self.entry_atr:
            del self.entry_atr[ticker]

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

            if ticker in self.adx_ind and self.adx_ind[ticker].is_ready:
                adx = self.adx_ind[ticker].current.value
                pos_di = self.adx_ind[ticker].positive_directional_index.current.value
                neg_di = self.adx_ind[ticker].negative_directional_index.current.value

                if adx < 20 or pos_di <= neg_di:
                    continue

                score = residual_mom * (adx / 100) * beta
            else:
                score = residual_mom * beta

            position_size = self.calculate_position_size(ticker)

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "residual_mom": residual_mom,
                "beta": beta,
                "score": score,
                "position_size": position_size
            })

        scores.sort(key=lambda x: x["score"], reverse=True)

        current_positions = len(self.entry_prices)
        slots = self.max_positions - current_positions

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
                self.entry_atr[ticker] = price * 0.03

            total_exposure += weight
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} RM={s['residual_mom']:.3f} Size={weight:.1%}")
