# region imports
from AlgorithmImports import *
# endregion

class KeltnerBreakoutR16(QCAlgorithm):
    """
    Round 16 Strategy 5: Keltner Channel Breakout

    Volatility-based breakout strategy using Keltner Channels.
    Buy when price closes above upper channel (expansion).

    Research: 77% win rate per QuantifiedStrategies

    Signal: Buy on close above upper Keltner Channel
    Exit: Price touches middle EMA or falls below entry
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Keltner Channel parameters
        self.ema_period = 20
        self.atr_period = 10
        self.atr_mult = 2.0

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
        self.prev_close = {}
        self.entry_prices = {}
        self.highest_prices = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            # Keltner Channel components
            self.kc_ema[ticker] = self.ema(sym, self.ema_period, Resolution.DAILY)
            self.kc_atr[ticker] = self.atr(sym, self.atr_period, MovingAverageType.SIMPLE, Resolution.DAILY)
            self.prev_close[ticker] = None

        # Market regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # ADX for trend strength confirmation
        self.adx_spy = self.adx(self.spy, 14, Resolution.DAILY)

        self.max_positions = 6

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.trade
        )

        self.set_benchmark("SPY")
        self.set_warm_up(50, Resolution.DAILY)

    def get_keltner_bands(self, ticker):
        """Calculate Keltner Channel bands"""
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

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            return

        signals = []

        for ticker in self.tickers:
            symbol = self.symbols[ticker]
            kc_lower, kc_mid, kc_upper = self.get_keltner_bands(ticker)

            if kc_upper is None:
                continue

            bar = self.securities[symbol]
            price = bar.close

            if ticker not in self.entry_prices:
                # Buy signal: Close breaks above upper Keltner Channel
                # Confirm with previous close below upper (fresh breakout)
                if self.prev_close[ticker] is not None:
                    if price > kc_upper and self.prev_close[ticker] <= kc_upper:
                        # Calculate breakout strength
                        breakout_strength = (price - kc_upper) / kc_upper
                        signals.append({
                            "ticker": ticker,
                            "symbol": symbol,
                            "price": price,
                            "kc_upper": kc_upper,
                            "score": breakout_strength
                        })
            else:
                # Exit conditions
                should_exit = False
                reason = ""

                # Update highest price
                if ticker not in self.highest_prices:
                    self.highest_prices[ticker] = price
                self.highest_prices[ticker] = max(self.highest_prices[ticker], price)

                # Exit 1: Price touches middle EMA (trend weakening)
                if price < kc_mid:
                    should_exit = True
                    pnl = (price - self.entry_prices[ticker]) / self.entry_prices[ticker]
                    reason = f"KC_MID({pnl:+.1%})"

                # Exit 2: Trailing stop from high
                pnl = (price - self.entry_prices[ticker]) / self.entry_prices[ticker]
                if pnl > 0.05:  # Only after 5% gain
                    drawdown = (price - self.highest_prices[ticker]) / self.highest_prices[ticker]
                    if drawdown < -0.06:  # 6% trailing stop
                        should_exit = True
                        reason = f"TRAIL({pnl:+.1%})"

                # Stop loss
                if pnl <= -0.07:
                    should_exit = True
                    reason = f"STOP({pnl:.1%})"

                if should_exit:
                    self.liquidate(symbol)
                    self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                    del self.entry_prices[ticker]
                    if ticker in self.highest_prices:
                        del self.highest_prices[ticker]

            self.prev_close[ticker] = price

        # Execute entries - prioritize strongest breakouts
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
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} KC_BREAKOUT (upper={s['kc_upper']:.2f})")
