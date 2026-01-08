from AlgorithmImports import *

class MomentumPullbackEntry(QCAlgorithm):
    """
    Momentum + Pullback Entry Strategy

    THESIS: High momentum stocks are great, but entering on pullbacks
    gives better prices and higher returns.

    EDGE: Instead of buying at any price, wait for RSI < 40 dips.
    This reduces average entry price while still capturing momentum.

    RULES:
    - Universe: 20 mega-cap stocks
    - Watchlist: Stocks with 6-mo return > SPY, Price > 50 SMA
    - Entry: Buy when RSI(14) < 40 on a watchlist stock
    - Exit: RSI(14) > 70 OR Price < 50 SMA
    - Max 3 positions, equal weight
    - Daily monitoring for entries

    TARGET: 40%+ CAGR, >1.0 Sharpe, <35% Max DD
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Mega-cap universe
        self.symbols = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B",
            "JPM", "JNJ", "V", "UNH", "HD", "PG", "MA", "LLY", "AVGO", "COST",
            "MRK", "ABBV"
        ]

        # Add securities
        self.equities = {}
        for symbol in self.symbols:
            equity = self.add_equity(symbol, Resolution.DAILY)
            equity.set_leverage(1.0)
            self.equities[symbol] = equity.symbol

        # Add SPY
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark("SPY")

        # Indicators
        self.momentum = {}
        self.sma50 = {}
        self.rsi_ind = {}

        for symbol in self.symbols:
            sym = self.equities[symbol]
            self.momentum[symbol] = self.momp(sym, 126)  # 6-month momentum
            self.sma50[symbol] = self.sma(sym, 50)
            self.rsi_ind[symbol] = self.rsi(sym, 14)

        self.spy_momentum = self.momp(self.spy, 126)

        # Settings
        self.max_positions = 3
        self.rsi_entry = 40  # Buy when RSI < 40
        self.rsi_exit = 70   # Sell when RSI > 70
        self.watchlist = set()

        # Warmup
        self.set_warm_up(timedelta(days=140))

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Update watchlist monthly (first trading day)
        if self.time.day <= 5:
            self.update_watchlist()

        # Check for entry signals
        self.check_entries()

        # Check for exit signals
        self.check_exits()

    def update_watchlist(self):
        """Update watchlist with high momentum stocks."""
        if not self.spy_momentum.is_ready:
            return

        spy_mom = self.spy_momentum.current.value
        self.watchlist = set()

        for symbol in self.symbols:
            sym = self.equities[symbol]

            if not self.securities[sym].is_tradable:
                continue

            if not self.momentum[symbol].is_ready or not self.sma50[symbol].is_ready:
                continue

            price = self.securities[sym].price
            sma = self.sma50[symbol].current.value
            mom = self.momentum[symbol].current.value

            # Momentum > SPY and Price > SMA
            if mom > spy_mom and price > sma:
                self.watchlist.add(symbol)

        self.log(f"Watchlist updated: {list(self.watchlist)}")

    def check_entries(self):
        """Check for pullback entries on watchlist stocks."""
        current_positions = sum(1 for s in self.symbols if self.portfolio[self.equities[s]].invested)

        if current_positions >= self.max_positions:
            return

        # Priority: stocks with lowest RSI first (deepest pullback)
        candidates = []

        for symbol in self.watchlist:
            sym = self.equities[symbol]

            if self.portfolio[sym].invested:
                continue

            if not self.rsi_ind[symbol].is_ready:
                continue

            rsi_value = self.rsi_ind[symbol].current.value

            # Entry signal: RSI < 40 (pullback)
            if rsi_value < self.rsi_entry:
                candidates.append((symbol, rsi_value))

        if not candidates:
            return

        # Sort by RSI (lowest first = deepest pullback)
        candidates.sort(key=lambda x: x[1])

        # How many slots available?
        slots_available = self.max_positions - current_positions

        # Enter positions
        for symbol, rsi_value in candidates[:slots_available]:
            sym = self.equities[symbol]
            weight = 1.0 / self.max_positions
            self.set_holdings(sym, weight)
            self.log(f"ENTRY: {symbol} at RSI {rsi_value:.1f}")

    def check_exits(self):
        """Check for exit signals on current positions."""
        for symbol in self.symbols:
            sym = self.equities[symbol]

            if not self.portfolio[sym].invested:
                continue

            if not self.rsi_ind[symbol].is_ready or not self.sma50[symbol].is_ready:
                continue

            price = self.securities[sym].price
            sma = self.sma50[symbol].current.value
            rsi_value = self.rsi_ind[symbol].current.value

            # Exit: RSI > 70 (overbought) OR Price < SMA (trend break)
            if rsi_value > self.rsi_exit:
                self.liquidate(sym)
                self.log(f"EXIT (overbought): {symbol} at RSI {rsi_value:.1f}")
            elif price < sma:
                self.liquidate(sym)
                self.log(f"EXIT (trend break): {symbol} below 50 SMA")
