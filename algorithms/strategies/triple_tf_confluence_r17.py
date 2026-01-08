# region imports
from AlgorithmImports import *
from datetime import timedelta
# endregion

class TripleTFConfluenceR17(QCAlgorithm):
    """
    Round 17 Strategy 4: Triple Timeframe Confluence

    Multi-timeframe approach using 3 timeframes:
    - WEEKLY: Trend direction (price > 10 EMA)
    - DAILY: Momentum confirmation (residual momentum positive)
    - 4H: Entry timing (momentum turning positive)

    First Principles:
    - Weekly shows the major trend
    - Daily confirms momentum/alpha
    - 4H provides precise entry timing
    - All 3 aligned = high probability setup

    Entry: Weekly up + Daily residual positive + 4H momentum up
    Exit: Any timeframe reverses OR stop/trailing
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.lookback = 42
        self.beta_lookback = 126

        self.tickers = [
            "TSLA", "NVDA", "AMD", "META", "NFLX",
            "CRM", "AMZN", "AVGO", "GS", "CAT",
            "AAPL", "MSFT", "GOOGL",
        ]

        self.symbols = {}
        self.return_history = {}

        # Weekly data
        self.weekly_bars = {}

        # Daily indicators
        self.daily_adx = {}

        # 4H data
        self.fourhour_bars = {}
        self.fourhour_mom = {}
        self.prev_fourhour_mom = {}

        self.entry_prices = {}
        self.highest_prices = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.HOUR)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym
            self.return_history[ticker] = []
            self.weekly_bars[ticker] = []
            self.fourhour_bars[ticker] = []
            self.fourhour_mom[ticker] = None
            self.prev_fourhour_mom[ticker] = None

            # Daily ADX
            self.daily_adx[ticker] = self.adx(sym, 14, Resolution.DAILY)

            # Weekly consolidator
            weekly = TradeBarConsolidator(Calendar.WEEKLY)
            weekly.data_consolidated += lambda sender, bar, t=ticker: self.on_weekly(t, bar)
            self.subscription_manager.add_consolidator(sym, weekly)

            # 4H consolidator
            four_hour = TradeBarConsolidator(timedelta(hours=4))
            four_hour.data_consolidated += lambda sender, bar, t=ticker: self.on_fourhour(t, bar)
            self.subscription_manager.add_consolidator(sym, four_hour)

        # SPY for residual
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_returns = []
        self.spy_weekly_bars = []

        spy_weekly = TradeBarConsolidator(Calendar.WEEKLY)
        spy_weekly.data_consolidated += self.on_spy_weekly
        self.subscription_manager.add_consolidator(self.spy, spy_weekly)

        # VIX
        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.max_positions = 4  # Concentrated
        self.prev_prices = {}

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.trade
        )

        self.set_benchmark("SPY")
        self.set_warm_up(200, Resolution.DAILY)

    def on_weekly(self, ticker, bar):
        self.weekly_bars[ticker].append(bar.close)
        if len(self.weekly_bars[ticker]) > 52:
            self.weekly_bars[ticker] = self.weekly_bars[ticker][-52:]

    def on_spy_weekly(self, sender, bar):
        self.spy_weekly_bars.append(bar.close)
        if len(self.spy_weekly_bars) > 52:
            self.spy_weekly_bars = self.spy_weekly_bars[-52:]

    def on_fourhour(self, ticker, bar):
        self.fourhour_bars[ticker].append(bar.close)
        if len(self.fourhour_bars[ticker]) > 30:
            self.fourhour_bars[ticker] = self.fourhour_bars[ticker][-30:]

        # 4H momentum (12 bars = ~2 days)
        if len(self.fourhour_bars[ticker]) >= 12:
            current = self.fourhour_bars[ticker][-1]
            past = self.fourhour_bars[ticker][-12]
            mom = (current - past) / past if past != 0 else 0
            self.prev_fourhour_mom[ticker] = self.fourhour_mom[ticker]
            self.fourhour_mom[ticker] = mom

    def get_weekly_ema(self, prices, period):
        if len(prices) < period:
            return None
        k = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        for price in prices[period:]:
            ema = price * k + ema * (1 - k)
        return ema

    def get_vix(self):
        if self.vix in self.securities and self.securities[self.vix].price > 0:
            return self.securities[self.vix].price
        return 20

    # WEEKLY: Uptrend
    def is_weekly_uptrend(self, ticker):
        if len(self.weekly_bars[ticker]) < 10:
            return False
        if len(self.spy_weekly_bars) < 20:
            return False

        stock_ema = self.get_weekly_ema(self.weekly_bars[ticker], 10)
        if stock_ema is None:
            return False

        current = self.weekly_bars[ticker][-1]
        if current < stock_ema:
            return False

        spy_sma = sum(self.spy_weekly_bars[-20:]) / 20
        if self.spy_weekly_bars[-1] < spy_sma:
            return False

        return True

    # DAILY: Positive residual momentum
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

    def calculate_residual_momentum(self, ticker):
        stock_rets = self.return_history[ticker]
        if len(stock_rets) < self.lookback or len(self.spy_returns) < self.lookback:
            return None

        # Simple beta
        n = min(len(stock_rets), len(self.spy_returns), self.beta_lookback)
        stock = stock_rets[-n:]
        market = self.spy_returns[-n:]
        mean_s = sum(stock) / len(stock)
        mean_m = sum(market) / len(market)
        cov = sum((s - mean_s) * (m - mean_m) for s, m in zip(stock, market)) / len(stock)
        var_m = sum((m - mean_m) ** 2 for m in market) / len(market)
        beta = cov / var_m if var_m > 0 else 1.0

        residuals = []
        n = min(len(stock_rets), len(self.spy_returns), self.lookback)
        for i in range(-n, 0):
            residual = stock_rets[i] - beta * self.spy_returns[i]
            residuals.append(residual)

        return sum(residuals)

    def is_daily_residual_positive(self, ticker):
        rm = self.calculate_residual_momentum(ticker)
        return rm is not None and rm > 0.01

    # 4H: Momentum turning positive
    def is_fourhour_momentum_up(self, ticker):
        if self.fourhour_mom[ticker] is None:
            return False
        if self.fourhour_mom[ticker] <= 0:
            return False
        if self.prev_fourhour_mom[ticker] is not None:
            if self.fourhour_mom[ticker] <= self.prev_fourhour_mom[ticker]:
                return False
        return True

    def is_fourhour_momentum_down(self, ticker):
        if self.fourhour_mom[ticker] is None:
            return False
        return self.fourhour_mom[ticker] < 0

    def trade(self):
        if self.is_warming_up:
            return

        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            return

        vix = self.get_vix()
        if vix > 30:
            return

        signals = []

        for ticker in self.tickers:
            symbol = self.symbols[ticker]
            price = self.securities[symbol].price

            if ticker not in self.entry_prices:
                # TRIPLE CONFLUENCE: Weekly + Daily + 4H
                weekly_ok = self.is_weekly_uptrend(ticker)
                daily_ok = self.is_daily_residual_positive(ticker)
                fourhour_ok = self.is_fourhour_momentum_up(ticker)

                if weekly_ok and daily_ok and fourhour_ok:
                    rm = self.calculate_residual_momentum(ticker)
                    mom_4h = self.fourhour_mom[ticker]
                    signals.append({
                        "ticker": ticker,
                        "symbol": symbol,
                        "rm": rm,
                        "mom_4h": mom_4h,
                        "score": rm * 100 + mom_4h * 10
                    })
            else:
                should_exit = False
                reason = ""

                if ticker not in self.highest_prices:
                    self.highest_prices[ticker] = price
                self.highest_prices[ticker] = max(self.highest_prices[ticker], price)

                pnl = (price - self.entry_prices[ticker]) / self.entry_prices[ticker]

                # Exit on weekly reversal
                if not self.is_weekly_uptrend(ticker):
                    should_exit = True
                    reason = f"WEEKLY_REV({pnl:+.1%})"

                # Exit on 4H momentum turning down
                if self.is_fourhour_momentum_down(ticker):
                    should_exit = True
                    reason = f"4H_DOWN({pnl:+.1%})"

                # Stop loss
                if pnl <= -0.07:
                    should_exit = True
                    reason = f"STOP({pnl:.1%})"

                # Trailing stop
                if pnl >= 0.10:
                    dd = (price - self.highest_prices[ticker]) / self.highest_prices[ticker]
                    if dd < -0.08:
                        should_exit = True
                        reason = f"TRAIL({pnl:+.1%})"

                if should_exit:
                    self.liquidate(symbol)
                    self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                    del self.entry_prices[ticker]
                    if ticker in self.highest_prices:
                        del self.highest_prices[ticker]

        signals.sort(key=lambda x: x["score"], reverse=True)
        current = len(self.entry_prices)
        slots = self.max_positions - current

        for s in signals[:slots]:
            ticker = s["ticker"]
            symbol = s["symbol"]
            price = self.securities[symbol].price
            weight = 1.0 / self.max_positions
            self.set_holdings(symbol, weight)
            self.entry_prices[ticker] = price
            self.highest_prices[ticker] = price
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} RM={s['rm']:.3f} 4H={s['mom_4h']:.3f} TRIPLE_CONF")
