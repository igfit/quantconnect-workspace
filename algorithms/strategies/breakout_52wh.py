from AlgorithmImports import *

class Breakout52WeekHigh(QCAlgorithm):
    """
    52-Week High Breakout Strategy

    Research shows stocks making new 52-week highs tend to continue higher.
    Buy on breakout to new high, hold while trend continues.

    Signal: Price makes new 52-week high
    Exit: Price falls below 20-day SMA
    Positions: Top 5 stocks making new highs
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Parameters
        self.num_positions = 5
        self.lookback_52w = 252
        self.exit_sma_period = 20  # Faster exit for breakout trades

        # Universe - focus on momentum stocks
        self.universe_tickers = [
            "NVDA", "TSLA", "AMD", "META", "AVGO", "AAPL", "MSFT", "GOOGL", "AMZN",
            "CRM", "NOW", "ADBE", "PANW", "CRWD", "NFLX",
            "AMAT", "LRCX", "MRVL",
            "COIN", "UBER", "ABNB",
            "V", "MA", "UNH"
        ]

        # Add securities
        self.symbols = {}
        for ticker in self.universe_tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            self.symbols[ticker] = equity.symbol

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # Data structures
        self.price_windows = {}
        for ticker in self.universe_tickers:
            self.price_windows[ticker] = RollingWindow[float](self.lookback_52w + 10)

        # Exit SMAs
        self.exit_smas = {}
        for ticker, symbol in self.symbols.items():
            self.exit_smas[ticker] = self.sma(symbol, self.exit_sma_period, Resolution.DAILY)

        # Track which stocks are in breakout mode
        self.in_breakout = set()

        # Warmup
        self.set_warm_up(self.lookback_52w + 20)

        # Daily check for breakouts
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.check_breakouts
        )

    def on_data(self, data):
        if self.is_warming_up:
            return

        for ticker, symbol in self.symbols.items():
            if data.bars.contains_key(symbol):
                self.price_windows[ticker].add(data.bars[symbol].close)

    def get_52w_high(self, ticker):
        window = self.price_windows.get(ticker)
        if window is None or not window.is_ready:
            return None

        # Get high over past 252 days (exclude today)
        high = 0
        for i in range(1, min(self.lookback_52w + 1, window.count)):
            if window[i] > high:
                high = window[i]
        return high

    def check_breakouts(self):
        if self.is_warming_up:
            return

        new_breakouts = []
        exits = []

        for ticker in self.universe_tickers:
            window = self.price_windows.get(ticker)
            sma = self.exit_smas.get(ticker)
            symbol = self.symbols.get(ticker)

            if window is None or not window.is_ready:
                continue
            if sma is None or not sma.is_ready:
                continue

            current_price = window[0]
            high_52w = self.get_52w_high(ticker)

            if high_52w is None:
                continue

            is_breakout = current_price > high_52w
            below_exit_sma = current_price < sma.current.value

            # Check for new breakouts
            if is_breakout and ticker not in self.in_breakout:
                new_breakouts.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'price': current_price,
                    'prev_high': high_52w,
                    'strength': (current_price - high_52w) / high_52w  # Breakout strength
                })

            # Check for exits
            if ticker in self.in_breakout and below_exit_sma:
                exits.append(ticker)

        # Process exits first
        for ticker in exits:
            symbol = self.symbols[ticker]
            if self.portfolio[symbol].invested:
                self.liquidate(symbol, f"Below 20 SMA")
                self.debug(f"EXIT: {ticker}")
            self.in_breakout.discard(ticker)

        # Sort new breakouts by strength
        new_breakouts.sort(key=lambda x: x['strength'], reverse=True)

        # Count current positions
        current_positions = sum(1 for t in self.in_breakout if self.portfolio[self.symbols[t]].invested)

        # Add new positions if we have room
        for breakout in new_breakouts:
            if current_positions >= self.num_positions:
                break

            ticker = breakout['ticker']
            symbol = breakout['symbol']

            # Calculate position size
            position_size = 1.0 / self.num_positions

            self.set_holdings(symbol, position_size)
            self.in_breakout.add(ticker)
            current_positions += 1

            self.debug(f"BREAKOUT: {ticker} @ {breakout['price']:.2f} (prev high: {breakout['prev_high']:.2f})")

        # Rebalance existing positions if needed
        if len(self.in_breakout) > 0:
            position_size = 1.0 / max(len(self.in_breakout), 1)
            for ticker in self.in_breakout:
                symbol = self.symbols[ticker]
                if self.portfolio[symbol].invested:
                    current_pct = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value
                    if abs(current_pct - position_size) > 0.05:
                        self.set_holdings(symbol, position_size)
