from AlgorithmImports import *

class MeanReversionOversold(QCAlgorithm):
    """
    Mean Reversion Oversold Strategy

    Hypothesis: Buy stocks that are oversold (RSI < 30) and below
    their 50 SMA, expecting a bounce back to the mean.

    Signal: RSI < 30 AND Price < 50 SMA (oversold in downtrend)
    Exit: RSI > 50 OR Price > 50 SMA (back to mean)
    Positions: Up to 5 oversold stocks (20% each)
    Check: Daily
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # === PARAMETERS ===
        self.num_positions = 5
        self.rsi_period = 14
        self.rsi_oversold = 30
        self.rsi_exit = 50
        self.sma_period = 50

        # === UNIVERSE - Large liquid stocks ===
        self.universe_tickers = [
            "NVDA", "TSLA", "AMD", "META", "AVGO", "AAPL", "MSFT", "GOOGL", "AMZN",
            "CRM", "NOW", "ADBE", "PANW", "CRWD", "NFLX",
            "AMAT", "LRCX", "MRVL",
            "V", "MA", "UNH", "JPM", "HD", "COST"
        ]

        # === ADD SECURITIES ===
        self.symbols = {}
        for ticker in self.universe_tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            self.symbols[ticker] = equity.symbol

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # === INDICATORS ===
        self.rsi_indicators = {}
        self.sma_indicators = {}

        for ticker, symbol in self.symbols.items():
            self.rsi_indicators[ticker] = self.rsi(symbol, self.rsi_period, Resolution.DAILY)
            self.sma_indicators[ticker] = self.sma(symbol, self.sma_period, Resolution.DAILY)

        # Track entry conditions
        self.entry_prices = {}

        # === WARMUP ===
        self.set_warm_up(self.sma_period + 20)

        # === DAILY CHECK ===
        self.schedule.on(
            self.date_rules.every_day(self.spy),
            self.time_rules.after_market_open(self.spy, 30),
            self.check_signals
        )

    def check_signals(self):
        if self.is_warming_up:
            return

        # Check exits first
        exits = []
        for ticker, symbol in self.symbols.items():
            if not self.portfolio[symbol].invested:
                continue

            rsi = self.rsi_indicators.get(ticker)
            sma = self.sma_indicators.get(ticker)

            if rsi is None or sma is None:
                continue
            if not rsi.is_ready or not sma.is_ready:
                continue

            current_price = self.securities[symbol].price
            rsi_value = rsi.current.value
            sma_value = sma.current.value

            # Exit when mean reverts (RSI > 50 or price back above SMA)
            if rsi_value > self.rsi_exit or current_price > sma_value:
                exits.append(ticker)
                entry = self.entry_prices.get(ticker, current_price)
                gain = (current_price - entry) / entry * 100
                self.debug(f"EXIT {ticker}: RSI={rsi_value:.0f}, Gain={gain:.1f}%")

        for ticker in exits:
            symbol = self.symbols[ticker]
            self.liquidate(symbol)
            if ticker in self.entry_prices:
                del self.entry_prices[ticker]

        # Count current positions
        current_positions = sum(1 for t in self.universe_tickers
                                if self.portfolio[self.symbols[t]].invested)

        if current_positions >= self.num_positions:
            return

        # Look for new entries
        oversold = []
        for ticker in self.universe_tickers:
            if self.portfolio[self.symbols[ticker]].invested:
                continue

            rsi = self.rsi_indicators.get(ticker)
            sma = self.sma_indicators.get(ticker)

            if rsi is None or sma is None:
                continue
            if not rsi.is_ready or not sma.is_ready:
                continue

            current_price = self.securities[self.symbols[ticker]].price
            rsi_value = rsi.current.value
            sma_value = sma.current.value

            # Oversold condition: RSI < 30 AND price below SMA
            if rsi_value < self.rsi_oversold and current_price < sma_value:
                oversold.append({
                    'ticker': ticker,
                    'symbol': self.symbols[ticker],
                    'rsi': rsi_value,
                    'price': current_price
                })

        # Sort by most oversold (lowest RSI)
        oversold.sort(key=lambda x: x['rsi'])

        # Add positions
        for stock in oversold:
            if current_positions >= self.num_positions:
                break

            ticker = stock['ticker']
            symbol = stock['symbol']

            position_size = 1.0 / self.num_positions
            self.set_holdings(symbol, position_size)
            self.entry_prices[ticker] = stock['price']
            current_positions += 1

            self.debug(f"ENTRY {ticker}: RSI={stock['rsi']:.0f}, Price={stock['price']:.2f}")
