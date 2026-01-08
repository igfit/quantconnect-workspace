# region imports
from AlgorithmImports import *
# endregion

class MeanReversionR13(QCAlgorithm):
    """
    Round 13 Strategy 3: Mean Reversion with Trend Filter

    SIGNAL ALPHA via oversold bounces in uptrending stocks.

    Thesis:
    - Buy quality stocks when temporarily oversold (RSI < 35)
    - But ONLY if long-term trend is up (price > 50 SMA)
    - Sell when RSI recovers to neutral (RSI > 50)
    - Different stocks get oversold at different times = diversification

    Rules:
    - Entry: RSI(14) < 35 AND price > SMA(50) AND ADX > 20
    - Exit: RSI(14) > 50 OR price < SMA(50) OR held > 10 days
    - Max 8 positions, equal weight
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.tickers = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "CRM", "AMD",
            "AMZN", "TSLA", "HD", "NKE",
            "UNH", "LLY", "ABBV", "JNJ",
            "JPM", "GS", "BLK", "V",
            "CAT", "HON", "GE", "UPS",
            "NFLX", "DIS", "COST", "PG"
        ]

        self.symbols = {}
        self.rsi_ind = {}
        self.sma_50 = {}
        self.adx_ind = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.rsi_ind[ticker] = self.rsi(sym, 14, MovingAverageType.WILDERS, Resolution.DAILY)
            self.sma_50[ticker] = self.sma(sym, 50, Resolution.DAILY)
            self.adx_ind[ticker] = self.adx(sym, 14, Resolution.DAILY)

        # Market regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Track entries
        self.entry_dates = {}
        self.max_positions = 8
        self.max_hold_days = 10

        # Daily check
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.check_signals
        )

        self.set_benchmark("SPY")
        self.set_warm_up(60, Resolution.DAILY)

    def check_signals(self):
        """Daily check for entries and exits."""
        if self.is_warming_up:
            return

        # Market regime filter
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            self.entry_dates.clear()
            return

        # Check exits first
        for ticker in list(self.entry_dates.keys()):
            symbol = self.symbols[ticker]

            if not self.portfolio[symbol].invested:
                del self.entry_dates[ticker]
                continue

            rsi_val = self.rsi_ind[ticker].current.value
            price = self.securities[symbol].price
            sma_val = self.sma_50[ticker].current.value
            days_held = (self.time - self.entry_dates[ticker]).days

            should_exit = False
            reason = ""

            # Exit conditions
            if rsi_val > 50:
                should_exit = True
                reason = f"RSI_RECOVER({rsi_val:.0f})"
            elif price < sma_val:
                should_exit = True
                reason = f"TREND_BREAK"
            elif days_held >= self.max_hold_days:
                should_exit = True
                reason = f"TIME({days_held}d)"

            if should_exit:
                self.liquidate(symbol)
                del self.entry_dates[ticker]
                self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")

        # Check entries (if room for new positions)
        current_positions = len(self.entry_dates)
        if current_positions >= self.max_positions:
            return

        # Find oversold opportunities
        candidates = []
        for ticker in self.tickers:
            if ticker in self.entry_dates:
                continue

            symbol = self.symbols[ticker]

            if not self.rsi_ind[ticker].is_ready:
                continue
            if not self.sma_50[ticker].is_ready:
                continue
            if not self.adx_ind[ticker].is_ready:
                continue

            rsi_val = self.rsi_ind[ticker].current.value
            price = self.securities[symbol].price
            sma_val = self.sma_50[ticker].current.value
            adx_val = self.adx_ind[ticker].current.value

            # Entry: Oversold but in uptrend
            if rsi_val < 35 and price > sma_val and adx_val > 20:
                candidates.append({
                    "ticker": ticker,
                    "symbol": symbol,
                    "rsi": rsi_val,
                    "adx": adx_val
                })

        # Sort by most oversold (lowest RSI)
        candidates.sort(key=lambda x: x["rsi"])

        # Enter up to max positions
        slots_available = self.max_positions - current_positions
        for c in candidates[:slots_available]:
            ticker = c["ticker"]
            symbol = c["symbol"]

            weight = 1.0 / self.max_positions
            self.set_holdings(symbol, weight)
            self.entry_dates[ticker] = self.time

            self.debug(f"{self.time.date()}: ENTER {ticker} RSI={c['rsi']:.0f}")
