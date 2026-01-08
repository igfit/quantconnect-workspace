# region imports
from AlgorithmImports import *
# endregion

class DipBuyerStrategy(QCAlgorithm):
    """
    Round 12 Strategy 5: Dip Buyer (Mean Reversion)

    TRUE SIGNAL ALPHA: Buy short-term losers, sell after bounce.

    Rules:
    - Buy stocks down 5%+ in past 5 days (oversold dip)
    - But only if in long-term uptrend (price > 50 SMA)
    - Exit after 5 days OR 5% profit, whichever first
    - Alpha = timing mean reversion bounces
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.dip_threshold = -0.05  # 5% drop in 5 days
        self.profit_target = 0.05   # 5% bounce target
        self.max_hold_days = 5
        self.entry_dates = {}
        self.entry_prices = {}

        self.tickers = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
            "JPM", "V", "UNH", "HD", "JNJ", "XOM",
            "LLY", "ABBV", "PFE", "COST", "WMT", "DIS", "NFLX",
            "CRM", "AVGO", "AMD", "CAT", "GE", "BA", "GS", "BLK"
        ]

        self.symbols = {}
        self.roc_5d = {}  # 5-day rate of change
        self.sma_50 = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.roc_5d[ticker] = self.rocp(sym, 5, Resolution.DAILY)
            self.sma_50[ticker] = self.sma(sym, 50, Resolution.DAILY)

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

        # Check exits first
        self.check_exits()

        # Market regime
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            return

        # Check for dip entries
        self.check_entries()

    def check_exits(self):
        for ticker in list(self.entry_dates.keys()):
            symbol = self.symbols[ticker]
            if not self.portfolio[symbol].invested:
                if ticker in self.entry_dates:
                    del self.entry_dates[ticker]
                if ticker in self.entry_prices:
                    del self.entry_prices[ticker]
                continue

            days_held = (self.time - self.entry_dates[ticker]).days
            current_price = self.securities[symbol].price
            entry_price = self.entry_prices[ticker]
            pnl_pct = (current_price - entry_price) / entry_price

            should_exit = False
            reason = ""

            # Profit target (bounce captured)
            if pnl_pct >= self.profit_target:
                should_exit = True
                reason = f"BOUNCE(+{pnl_pct:.1%})"

            # Time exit
            elif days_held >= self.max_hold_days:
                should_exit = True
                reason = f"TIME({days_held}d, {pnl_pct:+.1%})"

            # Stop loss at -8%
            elif pnl_pct <= -0.08:
                should_exit = True
                reason = f"STOP({pnl_pct:.1%})"

            if should_exit:
                self.liquidate(symbol)
                self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                del self.entry_dates[ticker]
                del self.entry_prices[ticker]

    def check_entries(self):
        # Max 5 positions
        current_positions = len(self.entry_dates)
        if current_positions >= 5:
            return

        candidates = []
        for ticker in self.tickers:
            symbol = self.symbols[ticker]

            # Skip if already holding
            if ticker in self.entry_dates:
                continue

            if not self.roc_5d[ticker].is_ready or not self.sma_50[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma = self.sma_50[ticker].current.value
            roc = self.roc_5d[ticker].current.value

            # Entry conditions:
            # 1. Price still above 50 SMA (long-term uptrend intact)
            # 2. Dropped 5%+ in past 5 days (short-term dip)
            if price > sma and roc <= self.dip_threshold:
                candidates.append({
                    "ticker": ticker,
                    "symbol": symbol,
                    "roc": roc,
                    "price": price
                })

        # Sort by biggest dip (most oversold)
        candidates.sort(key=lambda x: x["roc"])

        # Enter top candidates
        slots = 5 - current_positions
        for c in candidates[:slots]:
            ticker = c["ticker"]
            symbol = c["symbol"]
            price = c["price"]

            self.set_holdings(symbol, 0.18)
            self.entry_dates[ticker] = self.time
            self.entry_prices[ticker] = price
            self.debug(f"{self.time.date()}: DIP BUY {ticker} ({c['roc']:.1%} in 5d) @ ${price:.2f}")
