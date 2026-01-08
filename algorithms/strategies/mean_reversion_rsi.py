from AlgorithmImports import *

class MeanReversionRSI(QCAlgorithm):
    """
    Mean Reversion RSI Strategy

    Thesis: High-beta stocks tend to overshoot both up and down. When RSI drops
    below 30, the stock is oversold and likely to bounce. This contrarian approach
    profits from emotional overreaction and mean reversion.

    Rules:
    - Universe: High-beta mega-cap stocks (excluding NVDA)
    - Entry: Buy when RSI(14) < 30 (oversold)
    - Exit: Sell when RSI(14) > 70 (overbought) OR after 20 trading days
    - Filter: Only buy if price > 200 SMA (uptrend context)
    - Position: Equal weight, max 5 positions

    Edge: Contrarian approach - buys fear, sells greed.
    Works best on volatile stocks that overshoot.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe - high-beta stocks (excluding NVDA)
        self.tickers = [
            "TSLA", "AMD", "META", "AMZN", "GOOGL",
            "NFLX", "CRM", "SHOP", "UBER", "SQ",
            "COIN", "MSTR", "ROKU", "SNAP", "PLTR",
            "DKNG", "RBLX", "HOOD", "SOFI", "AFRM"
        ]

        # Add equities
        self.symbols = {}
        for ticker in self.tickers:
            try:
                self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol
            except:
                pass  # Some tickers may not exist for full period

        # RSI indicators (don't shadow self.rsi method!)
        self.rsi_ind = {}
        for ticker, symbol in self.symbols.items():
            self.rsi_ind[ticker] = self.rsi(symbol, 14, MovingAverageType.WILDERS, Resolution.DAILY)

        # 200 SMA for trend filter
        self.sma200_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma200_ind[ticker] = self.sma(symbol, 200, Resolution.DAILY)

        # Track positions and entry dates
        self.entry_dates = {}
        self.max_hold_days = 20
        self.max_positions = 5

        # RSI thresholds
        self.oversold = 30
        self.overbought = 70

        # Set benchmark
        self.set_benchmark("SPY")
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol

        # Warmup
        self.set_warm_up(210, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up:
            return

        current_date = self.time.date()

        # Check exits first
        for ticker in list(self.entry_dates.keys()):
            symbol = self.symbols.get(ticker)
            if symbol is None or not self.portfolio[symbol].invested:
                if ticker in self.entry_dates:
                    del self.entry_dates[ticker]
                continue

            # Exit conditions
            rsi_value = self.rsi_ind[ticker].current.value if self.rsi_ind[ticker].is_ready else 50
            days_held = (current_date - self.entry_dates[ticker]).days

            exit_overbought = rsi_value > self.overbought
            exit_time = days_held >= self.max_hold_days

            if exit_overbought or exit_time:
                reason = "overbought" if exit_overbought else "time limit"
                self.debug(f"{current_date}: EXIT {ticker} - {reason} (RSI={rsi_value:.1f}, days={days_held})")
                self.liquidate(symbol)
                del self.entry_dates[ticker]

        # Check entries
        current_positions = len(self.entry_dates)
        if current_positions >= self.max_positions:
            return  # Max positions reached

        for ticker, symbol in self.symbols.items():
            # Skip if already holding
            if ticker in self.entry_dates:
                continue

            # Skip if we've hit max positions
            if current_positions >= self.max_positions:
                break

            # Check indicators ready
            if not self.rsi_ind[ticker].is_ready or not self.sma200_ind[ticker].is_ready:
                continue

            # Check data exists
            if not data.contains_key(symbol):
                continue

            price = self.securities[symbol].price
            rsi_value = self.rsi_ind[ticker].current.value
            sma200 = self.sma200_ind[ticker].current.value

            # Entry conditions:
            # 1. RSI < 30 (oversold)
            # 2. Price > 200 SMA (still in uptrend context)
            if rsi_value < self.oversold and price > sma200:
                # Calculate position size (equal weight among max positions)
                weight = 0.95 / self.max_positions

                self.set_holdings(symbol, weight)
                self.entry_dates[ticker] = current_date
                current_positions += 1

                self.debug(f"{current_date}: ENTRY {ticker} - RSI={rsi_value:.1f}, price=${price:.2f}")
