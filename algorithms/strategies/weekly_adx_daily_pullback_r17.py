# region imports
from AlgorithmImports import *
# endregion

class WeeklyADXDailyPullbackR17(QCAlgorithm):
    """
    Round 17 Strategy 3: Weekly ADX Trend + Daily Pullback Entry

    Multi-timeframe approach:
    - WEEKLY: Strong trend confirmation (ADX > 20, +DI > -DI)
    - DAILY: Buy pullbacks to moving average within strong weekly trend

    First Principles:
    - Strong weekly trends tend to persist (momentum)
    - Daily pullbacks within trends offer better risk/reward
    - Buying dips in uptrends has positive expectancy

    Entry: Weekly strong uptrend + Daily pullback to 20 EMA
    Exit: Weekly trend weakens OR daily stop loss
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.tickers = [
            "TSLA", "NVDA", "AMD", "META", "NFLX",
            "CRM", "AMZN", "AVGO", "GS", "CAT",
            "AAPL", "MSFT", "GOOGL",
        ]

        self.symbols = {}
        self.daily_ema = {}
        self.daily_rsi = {}
        self.weekly_adx_data = {}  # Store weekly ADX components
        self.weekly_bars = {}
        self.entry_prices = {}
        self.highest_prices = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            # Daily indicators
            self.daily_ema[ticker] = self.ema(sym, 20, Resolution.DAILY)
            self.daily_rsi[ticker] = self.rsi(sym, 14, MovingAverageType.WILDERS, Resolution.DAILY)

            # Weekly bar storage for manual ADX
            self.weekly_bars[ticker] = []
            self.weekly_adx_data[ticker] = {
                "tr_list": [],
                "plus_dm_list": [],
                "minus_dm_list": [],
                "adx": None,
                "plus_di": None,
                "minus_di": None
            }

            # Weekly consolidator
            weekly = TradeBarConsolidator(Calendar.WEEKLY)
            weekly.data_consolidated += lambda sender, bar, t=ticker: self.on_weekly(t, bar)
            self.subscription_manager.add_consolidator(sym, weekly)

        # SPY regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # VIX
        vix = self.add_data(CBOE, "VIX", Resolution.DAILY)
        self.vix = vix.symbol

        self.max_positions = 5

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.trade
        )

        self.set_benchmark("SPY")
        self.set_warm_up(100, Resolution.DAILY)

    def on_weekly(self, ticker, bar):
        """Calculate weekly ADX components"""
        self.weekly_bars[ticker].append({
            "high": bar.high,
            "low": bar.low,
            "close": bar.close
        })

        if len(self.weekly_bars[ticker]) > 30:
            self.weekly_bars[ticker] = self.weekly_bars[ticker][-30:]

        self.calculate_weekly_adx(ticker)

    def calculate_weekly_adx(self, ticker):
        """Manual ADX calculation from weekly bars"""
        bars = self.weekly_bars[ticker]
        if len(bars) < 15:
            return

        data = self.weekly_adx_data[ticker]
        period = 14

        # Calculate TR, +DM, -DM for all bars
        tr_list = []
        plus_dm_list = []
        minus_dm_list = []

        for i in range(1, len(bars)):
            high = bars[i]["high"]
            low = bars[i]["low"]
            prev_close = bars[i-1]["close"]
            prev_high = bars[i-1]["high"]
            prev_low = bars[i-1]["low"]

            # True Range
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)

            # +DM and -DM
            plus_dm = max(0, high - prev_high) if high - prev_high > prev_low - low else 0
            minus_dm = max(0, prev_low - low) if prev_low - low > high - prev_high else 0
            plus_dm_list.append(plus_dm)
            minus_dm_list.append(minus_dm)

        if len(tr_list) < period:
            return

        # Smoothed TR, +DM, -DM (Wilder smoothing)
        def smooth(data, period):
            if len(data) < period:
                return None
            smoothed = sum(data[:period])
            for val in data[period:]:
                smoothed = smoothed - (smoothed / period) + val
            return smoothed

        tr_smooth = smooth(tr_list, period)
        plus_dm_smooth = smooth(plus_dm_list, period)
        minus_dm_smooth = smooth(minus_dm_list, period)

        if tr_smooth is None or tr_smooth == 0:
            return

        # +DI and -DI
        plus_di = 100 * plus_dm_smooth / tr_smooth
        minus_di = 100 * minus_dm_smooth / tr_smooth

        # DX and ADX
        dx_sum = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0

        data["plus_di"] = plus_di
        data["minus_di"] = minus_di
        data["adx"] = dx_sum  # Simplified - using DX as proxy for ADX

    def is_weekly_strong_uptrend(self, ticker):
        """Check if weekly trend is strong and up"""
        data = self.weekly_adx_data[ticker]
        if data["adx"] is None:
            return False

        # Strong trend: ADX > 20, +DI > -DI
        return data["adx"] > 20 and data["plus_di"] > data["minus_di"]

    def get_vix(self):
        if self.vix in self.securities and self.securities[self.vix].price > 0:
            return self.securities[self.vix].price
        return 20

    def is_daily_pullback(self, ticker):
        """Check if price is pulling back to 20 EMA"""
        if not self.daily_ema[ticker].is_ready or not self.daily_rsi[ticker].is_ready:
            return False

        symbol = self.symbols[ticker]
        price = self.securities[symbol].price
        ema = self.daily_ema[ticker].current.value
        rsi = self.daily_rsi[ticker].current.value

        # Pullback: price within 3% of EMA and RSI cooling off (40-55)
        distance_to_ema = (price - ema) / ema
        return -0.03 <= distance_to_ema <= 0.03 and 40 <= rsi <= 55

    def trade(self):
        if self.is_warming_up:
            return

        # Market regime
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
                # Entry: Weekly strong uptrend + Daily pullback
                if self.is_weekly_strong_uptrend(ticker) and self.is_daily_pullback(ticker):
                    adx = self.weekly_adx_data[ticker]["adx"]
                    rsi = self.daily_rsi[ticker].current.value
                    signals.append({
                        "ticker": ticker,
                        "symbol": symbol,
                        "adx": adx,
                        "rsi": rsi,
                        "score": adx
                    })
            else:
                # Exit conditions
                should_exit = False
                reason = ""

                if ticker not in self.highest_prices:
                    self.highest_prices[ticker] = price
                self.highest_prices[ticker] = max(self.highest_prices[ticker], price)

                pnl = (price - self.entry_prices[ticker]) / self.entry_prices[ticker]

                # Exit on weekly trend weakening
                if not self.is_weekly_strong_uptrend(ticker):
                    should_exit = True
                    reason = f"WEEKLY_WEAK({pnl:+.1%})"

                # Stop loss
                if pnl <= -0.06:
                    should_exit = True
                    reason = f"STOP({pnl:.1%})"

                # Trailing stop
                if pnl >= 0.10:
                    drawdown = (price - self.highest_prices[ticker]) / self.highest_prices[ticker]
                    if drawdown < -0.07:
                        should_exit = True
                        reason = f"TRAIL({pnl:+.1%})"

                if should_exit:
                    self.liquidate(symbol)
                    self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                    del self.entry_prices[ticker]
                    if ticker in self.highest_prices:
                        del self.highest_prices[ticker]

        # Execute entries
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
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} W_ADX={s['adx']:.0f} RSI={s['rsi']:.0f} PULLBACK")
