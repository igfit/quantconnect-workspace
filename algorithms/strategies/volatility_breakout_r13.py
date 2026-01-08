# region imports
from AlgorithmImports import *
# endregion

class VolatilityBreakoutR13(QCAlgorithm):
    """
    Round 13 Strategy 6: Volatility Breakout

    SIGNAL ALPHA via breakout detection.

    Thesis:
    - Consolidation (low volatility) often precedes big moves
    - Buy when price breaks above consolidation range
    - Different stocks break out at different times = diversification

    Rules:
    - Entry: Price breaks above 20-day high AND ATR expanding
    - Exit: Trail stop at entry price OR -5% OR 10 days
    - Max 8 positions
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
        self.high_20d = {}
        self.atr_14 = {}
        self.atr_50 = {}  # Longer ATR for comparison
        self.sma_50 = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.high_20d[ticker] = self.max(sym, 20, Resolution.DAILY)
            self.atr_14[ticker] = self.atr(sym, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
            self.atr_50[ticker] = self.atr(sym, 50, MovingAverageType.SIMPLE, Resolution.DAILY)
            self.sma_50[ticker] = self.sma(sym, 50, Resolution.DAILY)

        # Market regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Track entries
        self.entry_dates = {}
        self.entry_prices = {}
        self.max_positions = 8
        self.stop_loss = -0.05
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
        """Daily check for breakouts and exits."""
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

            # Trail stop: exit if price falls back below entry
            if current_price < entry_price * 0.98:  # 2% below entry
                should_exit = True
                reason = f"TRAIL({pnl_pct:+.1%})"
            # Hard stop
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

        # Find breakout opportunities
        candidates = []
        for ticker in self.tickers:
            if ticker in self.entry_dates:
                continue

            symbol = self.symbols[ticker]

            if not self.high_20d[ticker].is_ready:
                continue
            if not self.atr_14[ticker].is_ready:
                continue
            if not self.atr_50[ticker].is_ready:
                continue
            if not self.sma_50[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            high_20d_val = self.high_20d[ticker].current.value
            atr_14_val = self.atr_14[ticker].current.value
            atr_50_val = self.atr_50[ticker].current.value
            sma_val = self.sma_50[ticker].current.value

            # Entry: New 20-day high + volatility expanding + uptrend
            is_breakout = price >= high_20d_val * 0.99  # Within 1% of 20-day high
            vol_expanding = atr_14_val > atr_50_val  # Short-term vol > long-term
            in_uptrend = price > sma_val

            if is_breakout and vol_expanding and in_uptrend:
                # Score by how much above 20-day high
                breakout_strength = (price / high_20d_val) - 1
                candidates.append({
                    "ticker": ticker,
                    "symbol": symbol,
                    "strength": breakout_strength,
                    "price": price
                })

        # Sort by breakout strength
        candidates.sort(key=lambda x: x["strength"], reverse=True)

        # Enter positions
        slots_available = self.max_positions - current_positions
        for c in candidates[:slots_available]:
            ticker = c["ticker"]
            symbol = c["symbol"]

            weight = 1.0 / self.max_positions
            self.set_holdings(symbol, weight)
            self.entry_dates[ticker] = self.time
            self.entry_prices[ticker] = c["price"]

            self.debug(f"{self.time.date()}: BREAKOUT {ticker} +{c['strength']:.1%}")
