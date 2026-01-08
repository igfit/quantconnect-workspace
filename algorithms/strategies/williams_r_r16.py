# region imports
from AlgorithmImports import *
# endregion

class WilliamsRR16(QCAlgorithm):
    """
    Round 16 Strategy 4: Williams %R Oversold Bounce

    Short lookback (2-5 days) Williams %R with extreme levels.
    Research shows 81% win rate with proper parameters.

    Signal: Buy when Williams %R < -90 (extremely oversold)
    Exit: When today's close > yesterday's high OR Williams %R > -30

    Source: QuantifiedStrategies (81% win rate backtest)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Williams %R parameters - short lookback per research
        self.lookback = 2  # Very short for sensitivity
        self.oversold = -90
        self.exit_level = -30

        self.tickers = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
            "AMD", "NFLX", "CRM", "ADBE", "AVGO",
            "JPM", "GS", "V", "MA",
            "UNH", "LLY", "JNJ",
            "CAT", "GE", "HON",
        ]

        self.symbols = {}
        self.williams_r = {}
        self.prev_high = {}
        self.entry_prices = {}
        self.entry_dates = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            # Williams %R indicator
            self.williams_r[ticker] = self.wilr(sym, self.lookback, Resolution.DAILY)
            self.prev_high[ticker] = None

        # Market regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        self.max_positions = 8

        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.trade
        )

        self.set_benchmark("SPY")
        self.set_warm_up(30, Resolution.DAILY)

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

            if not self.williams_r[ticker].is_ready:
                continue

            wilr = self.williams_r[ticker].current.value
            bar = self.securities[symbol]
            price = bar.close
            high = bar.high

            if ticker not in self.entry_prices:
                # Buy when extremely oversold
                if wilr < self.oversold:
                    signals.append({
                        "ticker": ticker,
                        "symbol": symbol,
                        "wilr": wilr,
                        "score": abs(wilr)  # More oversold = higher priority
                    })
            else:
                # Exit conditions
                should_exit = False
                reason = ""

                # Exit 1: Close > yesterday's high (per research)
                if self.prev_high[ticker] is not None and price > self.prev_high[ticker]:
                    should_exit = True
                    reason = f"CLOSE>PREV_HIGH"

                # Exit 2: Williams %R recovers above -30
                if wilr > self.exit_level:
                    should_exit = True
                    reason = f"WILR_EXIT({wilr:.0f})"

                # Stop loss
                pnl = (price - self.entry_prices[ticker]) / self.entry_prices[ticker]
                if pnl <= -0.05:
                    should_exit = True
                    reason = f"STOP({pnl:.1%})"

                # Time limit (5 days max per research)
                if ticker in self.entry_dates:
                    days_held = (self.time - self.entry_dates[ticker]).days
                    if days_held >= 5:
                        should_exit = True
                        reason = f"TIME({days_held}d, {pnl:+.1%})"

                if should_exit:
                    self.liquidate(symbol)
                    self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                    del self.entry_prices[ticker]
                    if ticker in self.entry_dates:
                        del self.entry_dates[ticker]

            # Update previous high for next bar
            self.prev_high[ticker] = high

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
            self.entry_dates[ticker] = self.time
            self.debug(f"{self.time.date()}: ENTER {ticker} @ ${price:.2f} WILR={s['wilr']:.0f}")
