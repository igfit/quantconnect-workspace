# region imports
from AlgorithmImports import *
# endregion

class DipBuyerLooseR13(QCAlgorithm):
    """
    Round 13 Strategy 5: Dip Buyer with Loose Conditions

    SIGNAL ALPHA via buying dips in quality stocks.

    Thesis:
    - Buy when stock drops 3%+ from 5-day high (NOT oversold RSI)
    - Sell when stock recovers to breakeven or +3%
    - Different stocks dip at different times = natural diversification
    - Short holding period = many trades = signal alpha

    Rules:
    - Entry: Price < 97% of 5-day high AND price > 50 SMA (uptrend)
    - Exit: +3% from entry OR -5% stop OR 5 days max hold
    - Max 8 positions, 12.5% each
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
        self.sma_50 = {}
        self.high_5d = {}  # 5-day high

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.sma_50[ticker] = self.sma(sym, 50, Resolution.DAILY)
            self.high_5d[ticker] = self.max(sym, 5, Resolution.DAILY)

        # Market regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Track entries
        self.entry_dates = {}
        self.entry_prices = {}
        self.max_positions = 8
        self.profit_target = 0.03  # +3%
        self.stop_loss = -0.05     # -5%
        self.max_hold_days = 5
        self.dip_threshold = 0.97  # Buy when price < 97% of 5-day high

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
            self.entry_prices.clear()
            return

        # Check exits first
        for ticker in list(self.entry_dates.keys()):
            symbol = self.symbols[ticker]

            if not self.portfolio[symbol].invested:
                if ticker in self.entry_dates:
                    del self.entry_dates[ticker]
                if ticker in self.entry_prices:
                    del self.entry_prices[ticker]
                continue

            current_price = self.securities[symbol].price
            entry_price = self.entry_prices[ticker]
            pnl_pct = (current_price - entry_price) / entry_price
            days_held = (self.time - self.entry_dates[ticker]).days

            should_exit = False
            reason = ""

            # Profit target
            if pnl_pct >= self.profit_target:
                should_exit = True
                reason = f"PROFIT(+{pnl_pct:.1%})"
            # Stop loss
            elif pnl_pct <= self.stop_loss:
                should_exit = True
                reason = f"STOP({pnl_pct:.1%})"
            # Time exit
            elif days_held >= self.max_hold_days:
                should_exit = True
                reason = f"TIME({days_held}d,{pnl_pct:+.1%})"

            if should_exit:
                self.liquidate(symbol)
                del self.entry_dates[ticker]
                del self.entry_prices[ticker]
                self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")

        # Check entries
        current_positions = len(self.entry_dates)
        if current_positions >= self.max_positions:
            return

        # Find dip opportunities
        candidates = []
        for ticker in self.tickers:
            if ticker in self.entry_dates:
                continue

            symbol = self.symbols[ticker]

            if not self.sma_50[ticker].is_ready:
                continue
            if not self.high_5d[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma_val = self.sma_50[ticker].current.value
            high_5d_val = self.high_5d[ticker].current.value

            # Entry: Dip from recent high but still in uptrend
            dip_pct = price / high_5d_val
            if dip_pct < self.dip_threshold and price > sma_val:
                candidates.append({
                    "ticker": ticker,
                    "symbol": symbol,
                    "dip_pct": dip_pct,
                    "price": price
                })

        # Sort by biggest dip (lowest ratio)
        candidates.sort(key=lambda x: x["dip_pct"])

        # Enter positions
        slots_available = self.max_positions - current_positions
        for c in candidates[:slots_available]:
            ticker = c["ticker"]
            symbol = c["symbol"]

            weight = 1.0 / self.max_positions
            self.set_holdings(symbol, weight)
            self.entry_dates[ticker] = self.time
            self.entry_prices[ticker] = c["price"]

            self.debug(f"{self.time.date()}: ENTER {ticker} DIP={1-c['dip_pct']:.1%}")
