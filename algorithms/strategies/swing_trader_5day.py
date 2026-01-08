# region imports
from AlgorithmImports import *
# endregion

class SwingTrader5DayStrategy(QCAlgorithm):
    """
    Round 12 Strategy 1: Swing Trader (Max 5 Day Hold)

    TRUE SIGNAL ALPHA: Profits come from entry timing, not holding winners.

    Rules:
    - Enter on pullback + momentum confirmation
    - Exit after 5 days OR 8% profit, whichever first
    - No position can compound over time
    - Alpha = correctly timing short-term swings
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.max_hold_days = 5
        self.profit_target = 0.08  # 8% profit target
        self.entry_dates = {}
        self.entry_prices = {}

        # Universe - same stocks but different strategy
        self.tickers = [
            "AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA",
            "JPM", "V", "UNH", "HD", "PG", "JNJ", "XOM", "CVX",
            "LLY", "ABBV", "PFE", "MRK", "COST", "WMT", "DIS", "NFLX",
            "CRM", "AVGO", "AMD", "INTC", "CAT", "GE", "BA"
        ]

        self.symbols = {}
        self.rsi_ind = {}
        self.sma_20 = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            equity.set_data_normalization_mode(DataNormalizationMode.ADJUSTED)
            sym = equity.symbol
            self.symbols[ticker] = sym

            self.rsi_ind[ticker] = self.rsi(sym, 14, MovingAverageType.WILDERS, Resolution.DAILY)
            self.sma_20[ticker] = self.sma(sym, 20, Resolution.DAILY)

        # SPY for regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Daily checks
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.daily_check
        )

        self.set_benchmark("SPY")
        self.set_warm_up(50, Resolution.DAILY)

    def daily_check(self):
        if self.is_warming_up:
            return

        # Check exits first
        self.check_exits()

        # Then check for new entries
        self.check_entries()

    def check_exits(self):
        """Exit after 5 days OR 8% profit."""
        for ticker in list(self.entry_dates.keys()):
            symbol = self.symbols[ticker]
            if not self.portfolio[symbol].invested:
                continue

            days_held = (self.time - self.entry_dates[ticker]).days
            current_price = self.securities[symbol].price
            entry_price = self.entry_prices[ticker]
            pnl_pct = (current_price - entry_price) / entry_price

            should_exit = False
            reason = ""

            # Time-based exit
            if days_held >= self.max_hold_days:
                should_exit = True
                reason = f"TIME({days_held}d)"

            # Profit target hit
            elif pnl_pct >= self.profit_target:
                should_exit = True
                reason = f"PROFIT(+{pnl_pct:.1%})"

            # Stop loss at -5%
            elif pnl_pct <= -0.05:
                should_exit = True
                reason = f"STOP({pnl_pct:.1%})"

            if should_exit:
                self.liquidate(symbol)
                self.debug(f"{self.time.date()}: EXIT {ticker} {reason}")
                del self.entry_dates[ticker]
                del self.entry_prices[ticker]

    def check_entries(self):
        """Enter on pullback within uptrend."""
        # Market regime
        spy_price = self.securities[self.spy].price
        if not self.spy_sma_200.is_ready or spy_price < self.spy_sma_200.current.value:
            return

        # Max 5 positions at a time
        current_positions = len([t for t in self.entry_dates.keys()
                                if self.portfolio[self.symbols[t]].invested])
        if current_positions >= 5:
            return

        candidates = []
        for ticker in self.tickers:
            symbol = self.symbols[ticker]

            # Skip if already holding
            if ticker in self.entry_dates:
                continue

            if not self.rsi_ind[ticker].is_ready or not self.sma_20[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma = self.sma_20[ticker].current.value
            rsi = self.rsi_ind[ticker].current.value

            # Entry conditions:
            # 1. Price above 20 SMA (uptrend)
            # 2. RSI pulled back to 40-55 range (not overbought, not oversold)
            # This catches pullbacks within uptrends
            if price > sma and 40 <= rsi <= 55:
                # Score by how close to ideal RSI (45)
                score = 1.0 - abs(rsi - 45) / 15
                candidates.append({"ticker": ticker, "symbol": symbol, "score": score, "rsi": rsi})

        # Sort by score, take top (5 - current)
        candidates.sort(key=lambda x: x["score"], reverse=True)
        slots_available = 5 - current_positions

        for c in candidates[:slots_available]:
            ticker = c["ticker"]
            symbol = c["symbol"]
            price = self.securities[symbol].price

            # Equal weight across 5 positions
            self.set_holdings(symbol, 0.19)  # ~19% each, leaving cash buffer

            self.entry_dates[ticker] = self.time
            self.entry_prices[ticker] = price
            self.debug(f"{self.time.date()}: ENTER {ticker} RSI={c['rsi']:.0f} @ ${price:.2f}")
