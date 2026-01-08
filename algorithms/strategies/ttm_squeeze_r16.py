# region imports
from AlgorithmImports import *
# endregion

class TTMSqueezeR16(QCAlgorithm):
    """
    Round 16 Strategy 2: TTM Squeeze Momentum

    Based on John Carter's TTM Squeeze indicator.
    Squeeze = Bollinger Bands inside Keltner Channels (low volatility)
    Breakout = Bands expand outside Keltner (high volatility)

    Signal: Buy on first "green dot" (squeeze fires) with positive momentum
    Exit: When momentum histogram starts declining (2 bars opposite color)

    Research: 77% win rate in backtests per QuantifiedStrategies
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # TTM Squeeze parameters
        self.bb_length = 20
        self.bb_mult = 2.0
        self.kc_length = 20
        self.kc_mult = 1.5
        self.mom_length = 12

        self.tickers = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
            "AMD", "NFLX", "CRM", "ADBE", "AVGO",
            "JPM", "GS", "V", "MA",
            "UNH", "LLY", "JNJ",
            "CAT", "GE", "HON",
        ]

        self.symbols = {}
        self.bb_ind = {}
        self.kc_upper = {}
        self.kc_lower = {}
        self.kc_mid = {}
        self.atr_ind = {}
        self.mom_ind = {}

        # Track squeeze state
        self.was_in_squeeze = {}
        self.mom_history = {}
        self.entry_prices = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            # Bollinger Bands
            self.bb_ind[ticker] = self.bb(sym, self.bb_length, self.bb_mult, MovingAverageType.SIMPLE, Resolution.DAILY)

            # Keltner Channel components
            self.kc_mid[ticker] = self.ema(sym, self.kc_length, Resolution.DAILY)
            self.atr_ind[ticker] = self.atr(sym, self.kc_length, MovingAverageType.SIMPLE, Resolution.DAILY)

            # Momentum (using ROC as proxy)
            self.mom_ind[ticker] = self.momp(sym, self.mom_length, Resolution.DAILY)

            self.was_in_squeeze[ticker] = False
            self.mom_history[ticker] = []

        # Market regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        self.max_positions = 6

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.trade
        )

        self.set_benchmark("SPY")
        self.set_warm_up(100, Resolution.DAILY)

    def is_in_squeeze(self, ticker):
        """Check if Bollinger Bands are inside Keltner Channels"""
        if not all([
            self.bb_ind[ticker].is_ready,
            self.kc_mid[ticker].is_ready,
            self.atr_ind[ticker].is_ready
        ]):
            return None

        bb_upper = self.bb_ind[ticker].upper_band.current.value
        bb_lower = self.bb_ind[ticker].lower_band.current.value

        kc_mid = self.kc_mid[ticker].current.value
        atr = self.atr_ind[ticker].current.value
        kc_upper = kc_mid + self.kc_mult * atr
        kc_lower = kc_mid - self.kc_mult * atr

        # Squeeze is ON when BB inside KC
        return bb_lower > kc_lower and bb_upper < kc_upper

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

            if not self.mom_ind[ticker].is_ready:
                continue

            in_squeeze = self.is_in_squeeze(ticker)
            if in_squeeze is None:
                continue

            mom = self.mom_ind[ticker].current.value
            self.mom_history[ticker].append(mom)
            if len(self.mom_history[ticker]) > 10:
                self.mom_history[ticker] = self.mom_history[ticker][-10:]

            price = self.securities[symbol].price

            # Check for squeeze firing (was in squeeze, now not)
            squeeze_fired = self.was_in_squeeze[ticker] and not in_squeeze

            if ticker not in self.entry_prices:
                # Entry: Squeeze fires with positive, increasing momentum
                if squeeze_fired and mom > 0:
                    if len(self.mom_history[ticker]) >= 2:
                        mom_increasing = self.mom_history[ticker][-1] > self.mom_history[ticker][-2]
                        if mom_increasing:
                            signals.append({
                                "ticker": ticker,
                                "symbol": symbol,
                                "mom": mom,
                                "score": mom
                            })
            else:
                # Exit conditions
                should_exit = False
                reason = ""

                # Exit on momentum reversal (2 declining bars)
                if len(self.mom_history[ticker]) >= 3:
                    last3 = self.mom_history[ticker][-3:]
                    if last3[-1] < last3[-2] < last3[-3]:
                        should_exit = True
                        reason = f"MOM_DECLINE"

                # Stop loss
                pnl = (price - self.entry_prices[ticker]) / self.entry_prices[ticker]
                if pnl <= -0.07:
                    should_exit = True
                    reason = f"STOP({pnl:.1%})"

                # Profit target
                if pnl >= 0.15:
                    should_exit = True
                    reason = f"PROFIT(+{pnl:.1%})"

                if should_exit:
                    self.liquidate(symbol)
                    self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                    del self.entry_prices[ticker]

            self.was_in_squeeze[ticker] = in_squeeze

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
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} SQUEEZE_FIRE (mom={s['mom']:.2f})")
