# region imports
from AlgorithmImports import *
# endregion

class SmallCapLowDDV1(QCAlgorithm):
    """
    Round 18 DD Reduction V1: Conservative Parameters

    Changes from ResidualSmallCapR18:
    1. Tighter VIX filter: VIX < 25 (was 35)
    2. Tighter stop loss: 7% (was 10%)
    3. Earlier trailing stop: Activate at 8% gain (was 12%)
    4. Reduced positions: Max 4 (was 5)
    5. Higher momentum threshold: 0.04 (was 0.03)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.lookback = 42
        self.beta_lookback = 126

        # Small/Mid-Cap High-Beta Universe
        self.tickers = [
            # Fintech
            "SOFI", "UPST", "AFRM", "HOOD", "BILL",
            # EV / Clean Energy
            "RIVN", "LCID", "PLUG", "FCEL", "CHPT",
            # Crypto-adjacent
            "RIOT", "MARA", "COIN",
            # Gaming / Entertainment
            "DKNG", "RBLX", "U",
            # Cloud / SaaS
            "NET", "DDOG", "MDB", "CRWD", "ZS", "GTLB",
            # Data / AI
            "PLTR", "PATH", "SNOW",
        ]

        self.symbols = {}
        self.return_history = {}
        self.adx_ind = {}
        self.entry_prices = {}
        self.highest_prices = {}

        for ticker in self.tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
                sym = equity.symbol
                self.symbols[ticker] = sym
                self.return_history[ticker] = []
                self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)
            except:
                self.debug(f"Could not add {ticker}")

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_returns = []

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        # DD Reduction: Fewer positions
        self.max_positions = 4
        self.prev_prices = {}

        # DD Reduction: Tighter stop parameters
        self.stop_loss_pct = 0.07          # Was 0.10
        self.trailing_activation = 0.08    # Was 0.12
        self.trailing_stop_pct = 0.10      # Was 0.12
        self.vix_threshold = 25            # Was 35
        self.momentum_threshold = 0.04     # Was 0.03

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

    def check_exits(self):
        if self.is_warming_up:
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

            should_exit = False
            reason = ""

            # Tighter stop loss
            if pnl <= -self.stop_loss_pct:
                should_exit = True
                reason = f"STOP({pnl:.1%})"

            # Earlier trailing stop activation
            if pnl >= self.trailing_activation:
                drawdown = (price - self.highest_prices[ticker]) / self.highest_prices[ticker]
                if drawdown < -self.trailing_stop_pct:
                    should_exit = True
                    reason = f"TRAIL({pnl:+.1%})"

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

    def rebalance(self):
        if self.is_warming_up:
            return

        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            for t in list(self.entry_prices.keys()):
                self._cleanup(t)
            return

        # Tighter VIX filter
        vix = self.get_vix()
        if vix > self.vix_threshold:
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

            # Higher momentum threshold
            if residual_mom <= self.momentum_threshold:
                continue

            # ADX filter
            if ticker in self.adx_ind and self.adx_ind[ticker].is_ready:
                adx = self.adx_ind[ticker].current.value
                pos_di = self.adx_ind[ticker].positive_directional_index.current.value
                neg_di = self.adx_ind[ticker].negative_directional_index.current.value

                if adx < 20 or pos_di <= neg_di:
                    continue

                score = residual_mom * (adx / 100) * beta
            else:
                score = residual_mom * beta

            scores.append({
                "ticker": ticker,
                "symbol": symbol,
                "residual_mom": residual_mom,
                "beta": beta,
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
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} RM={s['residual_mom']:.3f}")
