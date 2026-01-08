# region imports
from AlgorithmImports import *
# endregion

class KeltnerMomentumR16(QCAlgorithm):
    """
    Round 16 Strategy 5b: Keltner Channel + Momentum Combo

    Combines Keltner breakout with momentum confirmation.
    Only enter breakouts when momentum is strong (ADX > 25).

    Improved from V1:
    - ADX trend filter
    - Tighter ATR multiplier (1.5)
    - Momentum confirmation
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Keltner parameters - tighter bands
        self.ema_period = 20
        self.atr_period = 10
        self.atr_mult = 1.5  # Tighter than standard 2.0

        self.tickers = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
            "AMD", "NFLX", "CRM", "ADBE", "AVGO",
            "JPM", "GS", "V", "MA",
            "UNH", "LLY", "JNJ",
            "CAT", "GE", "HON",
        ]

        self.symbols = {}
        self.kc_ema = {}
        self.kc_atr = {}
        self.adx_ind = {}
        self.momp_ind = {}
        self.prev_close = {}
        self.entry_prices = {}
        self.highest_prices = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.kc_ema[ticker] = self.ema(sym, self.ema_period, Resolution.DAILY)
            self.kc_atr[ticker] = self.atr(sym, self.atr_period, MovingAverageType.SIMPLE, Resolution.DAILY)
            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)
            self.momp_ind[ticker] = self.momp(sym, 20, Resolution.DAILY)
            self.prev_close[ticker] = None

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.max_positions = 5

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.trade
        )

        self.set_benchmark("SPY")
        self.set_warm_up(50, Resolution.DAILY)

    def get_vix(self):
        if self.vix in self.securities and self.securities[self.vix].price > 0:
            return self.securities[self.vix].price
        return 20

    def get_keltner_bands(self, ticker):
        if not self.kc_ema[ticker].is_ready or not self.kc_atr[ticker].is_ready:
            return None, None, None

        mid = self.kc_ema[ticker].current.value
        atr = self.kc_atr[ticker].current.value
        upper = mid + self.atr_mult * atr
        lower = mid - self.atr_mult * atr

        return lower, mid, upper

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
            kc_lower, kc_mid, kc_upper = self.get_keltner_bands(ticker)

            if kc_upper is None:
                continue

            if not self.adx_ind[ticker].is_ready or not self.momp_ind[ticker].is_ready:
                continue

            bar = self.securities[symbol]
            price = bar.close

            adx = self.adx_ind[ticker].current.value
            pos_di = self.adx_ind[ticker].positive_directional_index.current.value
            neg_di = self.adx_ind[ticker].negative_directional_index.current.value
            mom = self.momp_ind[ticker].current.value

            if ticker not in self.entry_prices:
                # Entry: Breakout + strong trend + positive momentum
                if self.prev_close[ticker] is not None:
                    fresh_breakout = price > kc_upper and self.prev_close[ticker] <= kc_upper
                    strong_trend = adx > 25 and pos_di > neg_di
                    positive_mom = mom > 0

                    if fresh_breakout and strong_trend and positive_mom:
                        signals.append({
                            "ticker": ticker,
                            "symbol": symbol,
                            "adx": adx,
                            "mom": mom,
                            "score": adx * mom / 100
                        })
            else:
                should_exit = False
                reason = ""

                if ticker not in self.highest_prices:
                    self.highest_prices[ticker] = price
                self.highest_prices[ticker] = max(self.highest_prices[ticker], price)

                pnl = (price - self.entry_prices[ticker]) / self.entry_prices[ticker]

                # Exit: Trend reversal
                if neg_di > pos_di + 5:
                    should_exit = True
                    reason = f"TREND_REV({pnl:+.1%})"

                # Exit: Price below mid channel
                if price < kc_mid:
                    should_exit = True
                    reason = f"KC_MID({pnl:+.1%})"

                # Trailing stop
                if pnl > 0.06:
                    drawdown = (price - self.highest_prices[ticker]) / self.highest_prices[ticker]
                    if drawdown < -0.05:
                        should_exit = True
                        reason = f"TRAIL({pnl:+.1%})"

                # Stop loss
                if pnl <= -0.06:
                    should_exit = True
                    reason = f"STOP({pnl:.1%})"

                if should_exit:
                    self.liquidate(symbol)
                    self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                    del self.entry_prices[ticker]
                    if ticker in self.highest_prices:
                        del self.highest_prices[ticker]

            self.prev_close[ticker] = price

        signals.sort(key=lambda x: x["score"], reverse=True)
        current_positions = len(self.entry_prices)
        slots = self.max_positions - current_positions

        for s in signals[:slots]:
            ticker = s["ticker"]
            symbol = s["symbol"]
            price = self.securities[symbol].price
            weight = 1.0 / self.max_positions
            self.set_holdings(symbol, weight)
            self.entry_prices[ticker] = price
            self.highest_prices[ticker] = price
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} ADX={s['adx']:.0f} MOM={s['mom']:.1f}")
