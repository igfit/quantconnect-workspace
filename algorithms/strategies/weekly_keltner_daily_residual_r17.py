# region imports
from AlgorithmImports import *
# endregion

class WeeklyKeltnerDailyResidualR17(QCAlgorithm):
    """
    Round 17 Strategy 5: Weekly Keltner + Daily Residual Momentum

    Combines R16's best finding (residual momentum) with MTF Keltner:
    - WEEKLY: Price above Keltner middle (weekly trend up)
    - DAILY: Positive residual momentum (alpha signal)

    First Principles:
    - Weekly Keltner middle acts as trend/mean filter
    - Above weekly Keltner = strong weekly uptrend
    - Daily residual captures firm-specific alpha
    - Combined = trade alpha signals in weekly uptrends

    Entry: Weekly price > Keltner mid + Daily residual > 0
    Exit: Weekly price < Keltner mid OR daily stop
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.lookback = 42
        self.beta_lookback = 126

        # Keltner params
        self.kc_ema_period = 10  # Weekly EMA period
        self.kc_atr_mult = 1.5

        self.tickers = [
            "TSLA", "NVDA", "AMD", "META", "NFLX",
            "CRM", "AMZN", "AVGO", "GS", "CAT",
            "AAPL", "MSFT", "GOOGL",
        ]

        self.symbols = {}
        self.return_history = {}

        # Weekly Keltner data
        self.weekly_bars = {}
        self.weekly_kc = {}  # {ticker: {ema, atr, upper, mid, lower}}

        self.entry_prices = {}
        self.highest_prices = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym
            self.return_history[ticker] = []
            self.weekly_bars[ticker] = []
            self.weekly_kc[ticker] = {"mid": None}

            weekly = TradeBarConsolidator(Calendar.WEEKLY)
            weekly.data_consolidated += lambda sender, bar, t=ticker: self.on_weekly(t, bar)
            self.subscription_manager.add_consolidator(sym, weekly)

        # SPY
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_returns = []
        self.spy_weekly_bars = []

        spy_weekly = TradeBarConsolidator(Calendar.WEEKLY)
        spy_weekly.data_consolidated += self.on_spy_weekly
        self.subscription_manager.add_consolidator(self.spy, spy_weekly)

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

    def on_weekly(self, ticker, bar):
        self.weekly_bars[ticker].append({
            "high": bar.high,
            "low": bar.low,
            "close": bar.close
        })
        if len(self.weekly_bars[ticker]) > 30:
            self.weekly_bars[ticker] = self.weekly_bars[ticker][-30:]

        self.calculate_weekly_keltner(ticker)

    def on_spy_weekly(self, sender, bar):
        self.spy_weekly_bars.append(bar.close)
        if len(self.spy_weekly_bars) > 30:
            self.spy_weekly_bars = self.spy_weekly_bars[-30:]

    def calculate_weekly_keltner(self, ticker):
        bars = self.weekly_bars[ticker]
        if len(bars) < self.kc_ema_period + 1:
            return

        # Weekly EMA
        closes = [b["close"] for b in bars]
        k = 2 / (self.kc_ema_period + 1)
        ema = sum(closes[:self.kc_ema_period]) / self.kc_ema_period
        for c in closes[self.kc_ema_period:]:
            ema = c * k + ema * (1 - k)

        # Weekly ATR
        tr_list = []
        for i in range(1, len(bars)):
            high = bars[i]["high"]
            low = bars[i]["low"]
            prev_close = bars[i-1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)

        if len(tr_list) < self.kc_ema_period:
            return

        atr = sum(tr_list[-self.kc_ema_period:]) / self.kc_ema_period

        self.weekly_kc[ticker] = {
            "mid": ema,
            "upper": ema + self.kc_atr_mult * atr,
            "lower": ema - self.kc_atr_mult * atr
        }

    def is_weekly_above_keltner_mid(self, ticker):
        if len(self.weekly_bars[ticker]) < 2:
            return False
        kc = self.weekly_kc[ticker]
        if kc["mid"] is None:
            return False

        current_price = self.weekly_bars[ticker][-1]["close"]
        return current_price > kc["mid"]

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

    def calculate_residual_momentum(self, ticker):
        stock_rets = self.return_history[ticker]
        if len(stock_rets) < self.lookback or len(self.spy_returns) < self.lookback:
            return None

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

            # Exit: Weekly below Keltner mid
            if not self.is_weekly_above_keltner_mid(ticker):
                should_exit = True
                reason = f"WEEKLY_KC({pnl:+.1%})"

            if pnl <= -0.07:
                should_exit = True
                reason = f"STOP({pnl:.1%})"

            if pnl >= 0.10:
                dd = (price - self.highest_prices[ticker]) / self.highest_prices[ticker]
                if dd < -0.08:
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

            # WEEKLY: Above Keltner mid
            if not self.is_weekly_above_keltner_mid(ticker):
                continue

            # DAILY: Positive residual momentum
            result = self.calculate_residual_momentum(ticker)
            if result is None:
                continue

            rm, beta = result
            if rm <= 0.01:
                continue

            scores.append({
                "ticker": ticker,
                "symbol": self.symbols[ticker],
                "rm": rm,
                "beta": beta,
                "score": rm
            })

        scores.sort(key=lambda x: x["score"], reverse=True)
        current = len(self.entry_prices)
        slots = self.max_positions - current

        for s in scores[:slots]:
            ticker = s["ticker"]
            symbol = s["symbol"]
            price = self.securities[symbol].price
            weight = 1.0 / self.max_positions
            self.set_holdings(symbol, weight)
            self.entry_prices[ticker] = price
            self.highest_prices[ticker] = price
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} RM={s['rm']:.3f} WEEKLY_KC_UP")
