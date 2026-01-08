from AlgorithmImports import *

class BreakoutWithVolume(QCAlgorithm):
    """
    Breakout with Volume Strategy

    Thesis: When a stock breaks to new 52-week highs with above-average volume,
    it signals institutional buying. This supply/demand imbalance often leads
    to sustained momentum as institutions continue accumulating.

    Rules:
    - Universe: Mega-cap stocks (excluding NVDA)
    - Entry: Buy when price hits 52-week high AND volume > 1.5x 20-day average
    - Exit: 20% trailing stop OR price closes below 50 SMA
    - Position: Equal weight, max 5 positions

    Edge: Follows institutional money flow. Volume confirms conviction.
    Classic trend-following approach based on Darvas Box / O'Neil CANSLIM.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Universe - mega-caps excluding NVDA
        self.tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "TSLA", "AMD", "AVGO", "CRM", "ORCL",
            "ADBE", "NFLX", "CSCO", "INTC", "QCOM",
            "TXN", "IBM", "NOW", "UBER", "SHOP"
        ]

        # Add equities
        self.symbols = {}
        for ticker in self.tickers:
            self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol

        # 52-week high (252 trading days)
        self.high_252 = {}
        for ticker, symbol in self.symbols.items():
            self.high_252[ticker] = self.max(symbol, 252, Resolution.DAILY)

        # 20-day average volume
        self.avg_volume = {}
        for ticker, symbol in self.symbols.items():
            self.avg_volume[ticker] = SimpleMovingAverage(20)
            self.register_indicator(symbol, self.avg_volume[ticker], Resolution.DAILY, Field.VOLUME)

        # 50-day SMA for exit
        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        # Track positions and trailing stops
        self.trailing_stops = {}  # ticker -> highest price since entry
        self.entry_prices = {}
        self.trailing_pct = 0.20  # 20% trailing stop
        self.max_positions = 5
        self.volume_multiplier = 1.5

        # Set benchmark
        self.set_benchmark("SPY")
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol

        # Warmup
        self.set_warm_up(260, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up:
            return

        current_date = self.time.date()

        # Update trailing stops and check exits
        for ticker in list(self.trailing_stops.keys()):
            symbol = self.symbols.get(ticker)
            if symbol is None or not self.portfolio[symbol].invested:
                if ticker in self.trailing_stops:
                    del self.trailing_stops[ticker]
                if ticker in self.entry_prices:
                    del self.entry_prices[ticker]
                continue

            if not data.contains_key(symbol):
                continue

            price = self.securities[symbol].price
            sma50 = self.sma50_ind[ticker].current.value if self.sma50_ind[ticker].is_ready else 0

            # Update trailing high
            if price > self.trailing_stops[ticker]:
                self.trailing_stops[ticker] = price

            # Calculate trailing stop level
            stop_level = self.trailing_stops[ticker] * (1 - self.trailing_pct)

            # Exit conditions
            exit_trailing_stop = price < stop_level
            exit_sma = price < sma50 and sma50 > 0

            if exit_trailing_stop or exit_sma:
                reason = "trailing stop" if exit_trailing_stop else "below 50 SMA"
                gain_pct = (price / self.entry_prices[ticker] - 1) * 100
                self.debug(f"{current_date}: EXIT {ticker} - {reason}, gain={gain_pct:.1f}%")
                self.liquidate(symbol)
                del self.trailing_stops[ticker]
                del self.entry_prices[ticker]

        # Check for new breakout entries
        current_positions = len(self.trailing_stops)
        if current_positions >= self.max_positions:
            return

        for ticker, symbol in self.symbols.items():
            # Skip if already holding
            if ticker in self.trailing_stops:
                continue

            if current_positions >= self.max_positions:
                break

            # Check indicators ready
            if not all([
                self.high_252[ticker].is_ready,
                self.avg_volume[ticker].is_ready,
                self.sma50_ind[ticker].is_ready
            ]):
                continue

            if not data.contains_key(symbol):
                continue

            bar = data.bars.get(symbol)
            if bar is None:
                continue

            price = bar.close
            high_52wk = self.high_252[ticker].current.value
            volume = bar.volume
            avg_vol = self.avg_volume[ticker].current.value

            # Breakout conditions:
            # 1. Price at or near 52-week high (within 1%)
            # 2. Volume > 1.5x average
            near_high = price >= high_52wk * 0.99
            volume_surge = volume > avg_vol * self.volume_multiplier

            if near_high and volume_surge and avg_vol > 0:
                weight = 0.95 / self.max_positions
                self.set_holdings(symbol, weight)

                self.trailing_stops[ticker] = price
                self.entry_prices[ticker] = price
                current_positions += 1

                vol_ratio = volume / avg_vol
                self.debug(f"{current_date}: ENTRY {ticker} - Breakout! price=${price:.2f}, vol={vol_ratio:.1f}x avg")
