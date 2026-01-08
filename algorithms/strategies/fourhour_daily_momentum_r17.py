# region imports
from AlgorithmImports import *
from datetime import timedelta
# endregion

class FourHourDailyMomentumR17(QCAlgorithm):
    """
    Round 17 Strategy 2: 4H Momentum + Daily Trend

    Multi-timeframe approach:
    - 4H: Momentum shift detection (catches turns early)
    - DAILY: Trend confirmation (ADX, price > EMA)

    First Principles:
    - 4H bars catch momentum shifts before daily bars
    - Daily trend filter prevents trading against the trend
    - Combining gives early entry with confirmation

    Entry: 4H momentum positive AND daily trend up
    Exit: 4H momentum turns negative OR daily trend reversal
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
        self.daily_adx = {}
        self.daily_ema = {}
        self.fourhour_bars = {}
        self.fourhour_mom = {}
        self.prev_fourhour_mom = {}
        self.entry_prices = {}
        self.highest_prices = {}

        for ticker in self.tickers:
            # Use minute resolution for 4H consolidation
            equity = self.add_equity(ticker, Resolution.HOUR)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            # Daily indicators
            self.daily_adx[ticker] = self.adx(sym, 14, Resolution.DAILY)
            self.daily_ema[ticker] = self.ema(sym, 20, Resolution.DAILY)

            # 4H bar storage (we'll calculate momentum from these)
            self.fourhour_bars[ticker] = []
            self.fourhour_mom[ticker] = None
            self.prev_fourhour_mom[ticker] = None

            # 4-hour consolidator
            four_hour = TradeBarConsolidator(timedelta(hours=4))
            four_hour.data_consolidated += lambda sender, bar, t=ticker: self.on_four_hour(t, bar)
            self.subscription_manager.add_consolidator(sym, four_hour)

        # SPY for regime
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
        self.set_warm_up(50, Resolution.DAILY)

    def on_four_hour(self, ticker, bar):
        """Process 4H bars and calculate momentum"""
        self.fourhour_bars[ticker].append(bar.close)
        if len(self.fourhour_bars[ticker]) > 30:
            self.fourhour_bars[ticker] = self.fourhour_bars[ticker][-30:]

        # Calculate 4H momentum (12-period = ~2 days of 4H bars)
        if len(self.fourhour_bars[ticker]) >= 12:
            current = self.fourhour_bars[ticker][-1]
            past = self.fourhour_bars[ticker][-12]
            mom = (current - past) / past if past != 0 else 0

            self.prev_fourhour_mom[ticker] = self.fourhour_mom[ticker]
            self.fourhour_mom[ticker] = mom

    def get_vix(self):
        if self.vix in self.securities and self.securities[self.vix].price > 0:
            return self.securities[self.vix].price
        return 20

    def is_daily_uptrend(self, ticker):
        """Check daily trend using ADX and EMA"""
        if not self.daily_adx[ticker].is_ready or not self.daily_ema[ticker].is_ready:
            return False

        adx = self.daily_adx[ticker].current.value
        pos_di = self.daily_adx[ticker].positive_directional_index.current.value
        neg_di = self.daily_adx[ticker].negative_directional_index.current.value

        symbol = self.symbols[ticker]
        price = self.securities[symbol].price
        ema = self.daily_ema[ticker].current.value

        # Daily uptrend: ADX > 20, +DI > -DI, price > EMA
        return adx > 20 and pos_di > neg_di and price > ema

    def is_fourhour_momentum_positive(self, ticker):
        """Check if 4H momentum is positive and turning up"""
        if self.fourhour_mom[ticker] is None:
            return False

        # Positive momentum
        if self.fourhour_mom[ticker] <= 0:
            return False

        # Momentum increasing (turning up)
        if self.prev_fourhour_mom[ticker] is not None:
            if self.fourhour_mom[ticker] <= self.prev_fourhour_mom[ticker]:
                return False

        return True

    def is_fourhour_momentum_negative(self, ticker):
        """Check if 4H momentum is turning negative"""
        if self.fourhour_mom[ticker] is None:
            return False

        # Momentum negative and decreasing
        if self.fourhour_mom[ticker] < 0:
            if self.prev_fourhour_mom[ticker] is not None:
                if self.fourhour_mom[ticker] < self.prev_fourhour_mom[ticker]:
                    return True
        return False

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
                # Entry: Daily uptrend + 4H momentum positive
                if self.is_daily_uptrend(ticker) and self.is_fourhour_momentum_positive(ticker):
                    mom_4h = self.fourhour_mom[ticker]
                    adx = self.daily_adx[ticker].current.value
                    signals.append({
                        "ticker": ticker,
                        "symbol": symbol,
                        "mom_4h": mom_4h,
                        "adx": adx,
                        "score": mom_4h * adx
                    })
            else:
                # Exit conditions
                should_exit = False
                reason = ""

                if ticker not in self.highest_prices:
                    self.highest_prices[ticker] = price
                self.highest_prices[ticker] = max(self.highest_prices[ticker], price)

                pnl = (price - self.entry_prices[ticker]) / self.entry_prices[ticker]

                # Exit on 4H momentum turning negative
                if self.is_fourhour_momentum_negative(ticker):
                    should_exit = True
                    reason = f"4H_MOM_NEG({pnl:+.1%})"

                # Exit on daily trend reversal
                if not self.is_daily_uptrend(ticker):
                    should_exit = True
                    reason = f"DAILY_REV({pnl:+.1%})"

                # Stop loss
                if pnl <= -0.07:
                    should_exit = True
                    reason = f"STOP({pnl:.1%})"

                # Trailing stop
                if pnl >= 0.08:
                    drawdown = (price - self.highest_prices[ticker]) / self.highest_prices[ticker]
                    if drawdown < -0.06:
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
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} 4H_MOM={s['mom_4h']:.3f} ADX={s['adx']:.0f}")
