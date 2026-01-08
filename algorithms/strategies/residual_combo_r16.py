# region imports
from AlgorithmImports import *
# endregion

class ResidualComboR16(QCAlgorithm):
    """
    Round 16 Strategy 6c: Residual Momentum + ADX + Keltner

    Combines multiple non-obvious signals:
    1. Residual momentum (alpha-based ranking)
    2. ADX trend strength confirmation
    3. Price above Keltner middle (trend direction)

    Thesis: Multi-factor confirmation reduces false signals
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.lookback = 42
        self.beta_lookback = 126

        # Expanded high-quality universe
        self.tickers = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
            "AMD", "NFLX", "CRM", "ADBE", "AVGO",
            "JPM", "GS", "V", "MA",
            "UNH", "LLY", "JNJ",
            "CAT", "GE", "HON",
        ]

        self.symbols = {}
        self.return_history = {}
        self.adx_ind = {}
        self.kc_ema = {}
        self.kc_atr = {}
        self.entry_prices = {}
        self.highest_prices = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym
            self.return_history[ticker] = []

            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)
            self.kc_ema[ticker] = self.ema(sym, 20, Resolution.DAILY)
            self.kc_atr[ticker] = self.atr(sym, 10, MovingAverageType.SIMPLE, Resolution.DAILY)

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_returns = []

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.max_positions = 5
        self.prev_prices = {}

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

        for ticker in self.tickers:
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
            return 1.0

        n = min(len(stock_returns), len(market_returns), self.beta_lookback)
        stock = stock_returns[-n:]
        market = market_returns[-n:]

        mean_stock = sum(stock) / len(stock)
        mean_market = sum(market) / len(market)

        cov = sum((s - mean_stock) * (m - mean_market) for s, m in zip(stock, market)) / len(stock)
        var_market = sum((m - mean_market) ** 2 for m in market) / len(market)

        if var_market == 0:
            return 1.0
        return cov / var_market

    def calculate_residual_momentum(self, ticker):
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

    def check_exits(self):
        if self.is_warming_up:
            return

        for ticker in list(self.entry_prices.keys()):
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

            should_exit = False
            reason = ""

            # Stop loss
            if pnl <= -0.06:
                should_exit = True
                reason = f"STOP({pnl:.1%})"

            # Trailing stop after 8% gain
            if pnl >= 0.08:
                drawdown = (price - self.highest_prices[ticker]) / self.highest_prices[ticker]
                if drawdown < -0.07:
                    should_exit = True
                    reason = f"TRAIL({pnl:+.1%})"

            # ADX trend reversal
            if self.adx_ind[ticker].is_ready:
                neg_di = self.adx_ind[ticker].negative_directional_index.current.value
                pos_di = self.adx_ind[ticker].positive_directional_index.current.value
                if neg_di > pos_di + 8:
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

        scores = []
        for ticker in self.tickers:
            if ticker in self.entry_prices:
                continue

            symbol = self.symbols[ticker]
            price = self.securities[symbol].price

            # Check all indicators ready
            if not self.adx_ind[ticker].is_ready:
                continue
            if not self.kc_ema[ticker].is_ready or not self.kc_atr[ticker].is_ready:
                continue

            result = self.calculate_residual_momentum(ticker)
            if result is None:
                continue

            residual_mom, beta = result

            # Filter 1: Positive residual momentum
            if residual_mom <= 0.01:
                continue

            # Filter 2: Strong trend (ADX > 20, +DI > -DI)
            adx = self.adx_ind[ticker].current.value
            pos_di = self.adx_ind[ticker].positive_directional_index.current.value
            neg_di = self.adx_ind[ticker].negative_directional_index.current.value

            if adx < 20 or pos_di <= neg_di:
                continue

            # Filter 3: Price above Keltner middle
            kc_mid = self.kc_ema[ticker].current.value
            if price < kc_mid:
                continue

            # Composite score
            score = residual_mom * (adx / 100)

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "residual_mom": residual_mom,
                "adx": adx,
                "score": score
            })

        scores.sort(key=lambda x: x["score"], reverse=True)

        current_positions = len(self.entry_prices)
        slots = self.max_positions - current_positions

        for s in scores[:slots]:
            ticker = s["ticker"]
            symbol = s["symbol"]
            price = self.securities[symbol].price

            weight = 1.0 / self.max_positions
            self.set_holdings(symbol, weight)
            self.entry_prices[ticker] = price
            self.highest_prices[ticker] = price
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} RM={s['residual_mom']:.3f} ADX={s['adx']:.0f}")
