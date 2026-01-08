# region imports
from AlgorithmImports import *
# endregion

class RSIOscillatorStrategy(QCAlgorithm):
    """
    Round 12 Strategy 4: RSI Oscillator

    TRUE SIGNAL ALPHA: Trade the RSI oscillations, not the trend.

    Rules:
    - Buy when RSI crosses above 30 (oversold bounce)
    - Sell when RSI crosses above 70 (overbought)
    - Or exit after 10 days max
    - Alpha = timing RSI reversals
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.max_hold_days = 10
        self.entry_dates = {}
        self.prev_rsi = {}

        self.tickers = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
            "JPM", "V", "UNH", "HD", "JNJ", "XOM",
            "LLY", "ABBV", "PFE", "COST", "WMT", "DIS", "NFLX",
            "CRM", "AVGO", "AMD", "CAT", "GE", "BA", "GS"
        ]

        self.symbols = {}
        self.rsi_ind = {}
        self.sma_50 = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.rsi_ind[ticker] = self.rsi(sym, 14, MovingAverageType.WILDERS, Resolution.DAILY)
            self.sma_50[ticker] = self.sma(sym, 50, Resolution.DAILY)
            self.prev_rsi[ticker] = None

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.daily_check
        )

        self.set_benchmark("SPY")
        self.set_warm_up(60, Resolution.DAILY)

    def daily_check(self):
        if self.is_warming_up:
            return

        # Market regime
        spy_price = self.securities[self.spy].price
        bull_market = self.spy_sma_200.is_ready and spy_price > self.spy_sma_200.current.value

        for ticker in self.tickers:
            symbol = self.symbols[ticker]

            if not self.rsi_ind[ticker].is_ready or not self.sma_50[ticker].is_ready:
                continue

            rsi = self.rsi_ind[ticker].current.value
            prev_rsi = self.prev_rsi[ticker]
            price = self.securities[symbol].price
            sma = self.sma_50[ticker].current.value

            # Check exits first
            if self.portfolio[symbol].invested:
                should_exit = False
                reason = ""

                # RSI overbought exit
                if prev_rsi and prev_rsi < 70 and rsi >= 70:
                    should_exit = True
                    reason = f"RSI_HIGH({rsi:.0f})"

                # Time exit
                elif ticker in self.entry_dates:
                    days_held = (self.time - self.entry_dates[ticker]).days
                    if days_held >= self.max_hold_days:
                        should_exit = True
                        reason = f"TIME({days_held}d)"

                if should_exit:
                    self.liquidate(symbol)
                    self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                    if ticker in self.entry_dates:
                        del self.entry_dates[ticker]

            # Check entries
            else:
                # Only enter in bull market
                if not bull_market:
                    self.prev_rsi[ticker] = rsi
                    continue

                # Max 6 positions
                current_positions = sum(1 for t in self.tickers
                                       if self.portfolio[self.symbols[t]].invested)
                if current_positions >= 6:
                    self.prev_rsi[ticker] = rsi
                    continue

                # Entry: RSI crosses above 30 (oversold bounce) while in uptrend
                if prev_rsi and prev_rsi < 30 and rsi >= 30 and price > sma:
                    self.set_holdings(symbol, 0.15)
                    self.entry_dates[ticker] = self.time
                    self.debug(f"{self.time.date()}: ENTER {ticker} RSI crossed 30 ({prev_rsi:.0f}→{rsi:.0f})")

            self.prev_rsi[ticker] = rsi
