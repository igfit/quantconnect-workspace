# region imports
from AlgorithmImports import *
# endregion

class WeeklyTrendDailyResidualR17(QCAlgorithm):
    """
    Round 17 Strategy 1: Weekly Trend + Daily Residual Momentum

    Multi-timeframe approach:
    - WEEKLY: Trend filter (stock above 10 EMA, SPY above 20 SMA)
    - DAILY: Residual momentum for entry signal

    First Principles:
    - Weekly trend shows the "big picture" - only trade with it
    - Daily residual momentum captures firm-specific alpha
    - Combining both should reduce false signals

    Entry: Weekly uptrend + Daily positive residual momentum
    Exit: Weekly trend reversal OR daily trailing stop
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.lookback = 42  # Daily residual lookback
        self.beta_lookback = 126

        self.tickers = [
            "TSLA", "NVDA", "AMD", "META", "NFLX",
            "CRM", "AMZN", "AVGO", "GS", "CAT",
            "AAPL", "MSFT", "GOOGL",
        ]

        self.symbols = {}
        self.return_history = {}
        self.weekly_ema = {}
        self.weekly_bars = {}
        self.entry_prices = {}
        self.highest_prices = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym
            self.return_history[ticker] = []
            self.weekly_bars[ticker] = []

            # Weekly consolidator for EMA calculation
            weekly_consolidator = TradeBarConsolidator(Calendar.WEEKLY)
            weekly_consolidator.data_consolidated += lambda sender, bar, t=ticker: self.on_weekly_bar(t, bar)
            self.subscription_manager.add_consolidator(sym, weekly_consolidator)

        # SPY for market regime and beta
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_returns = []
        self.spy_weekly_bars = []

        # SPY weekly consolidator
        spy_weekly = TradeBarConsolidator(Calendar.WEEKLY)
        spy_weekly.data_consolidated += self.on_spy_weekly
        self.subscription_manager.add_consolidator(self.spy, spy_weekly)

        # VIX
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

    def on_weekly_bar(self, ticker, bar):
        """Store weekly bars for EMA calculation"""
        self.weekly_bars[ticker].append(bar.close)
        if len(self.weekly_bars[ticker]) > 52:
            self.weekly_bars[ticker] = self.weekly_bars[ticker][-52:]

    def on_spy_weekly(self, sender, bar):
        """Store SPY weekly bars"""
        self.spy_weekly_bars.append(bar.close)
        if len(self.spy_weekly_bars) > 52:
            self.spy_weekly_bars = self.spy_weekly_bars[-52:]

    def get_weekly_ema(self, prices, period):
        """Calculate EMA from weekly prices"""
        if len(prices) < period:
            return None
        k = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        for price in prices[period:]:
            ema = price * k + ema * (1 - k)
        return ema

    def is_weekly_uptrend(self, ticker):
        """Check if stock is in weekly uptrend"""
        if len(self.weekly_bars[ticker]) < 10:
            return False
        if len(self.spy_weekly_bars) < 20:
            return False

        # Stock above 10-week EMA
        stock_ema = self.get_weekly_ema(self.weekly_bars[ticker], 10)
        if stock_ema is None:
            return False
        current_price = self.weekly_bars[ticker][-1]
        if current_price < stock_ema:
            return False

        # SPY above 20-week SMA (market regime)
        spy_sma = sum(self.spy_weekly_bars[-20:]) / 20
        spy_price = self.spy_weekly_bars[-1]
        if spy_price < spy_sma:
            return False

        return True

    def get_vix(self):
        if self.vix in self.securities and self.securities[self.vix].price > 0:
            return self.securities[self.vix].price
        return 20

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Collect daily returns for residual calculation
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

            # Exit on weekly trend reversal
            if not self.is_weekly_uptrend(ticker):
                should_exit = True
                reason = f"WEEKLY_REV({pnl:+.1%})"

            # Stop loss
            if pnl <= -0.07:
                should_exit = True
                reason = f"STOP({pnl:.1%})"

            # Trailing stop after 10% gain
            if pnl >= 0.10:
                drawdown = (price - self.highest_prices[ticker]) / self.highest_prices[ticker]
                if drawdown < -0.08:
                    should_exit = True
                    reason = f"TRAIL({pnl:+.1%})"

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

        vix = self.get_vix()
        if vix > 30:
            return

        scores = []
        for ticker in self.tickers:
            if ticker in self.entry_prices:
                continue

            # WEEKLY FILTER: Must be in weekly uptrend
            if not self.is_weekly_uptrend(ticker):
                continue

            # DAILY SIGNAL: Positive residual momentum
            result = self.calculate_residual_momentum(ticker)
            if result is None:
                continue

            residual_mom, beta = result
            if residual_mom <= 0.01:
                continue

            scores.append({
                "ticker": ticker,
                "symbol": self.symbols[ticker],
                "residual_mom": residual_mom,
                "beta": beta,
                "score": residual_mom
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
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} RM={s['residual_mom']:.3f} WEEKLY_UP")
