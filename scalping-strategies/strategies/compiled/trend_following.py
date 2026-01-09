"""
Simple Trend Following Strategy

FIRST PRINCIPLES:
- High-beta stocks TREND - don't fight it, follow it
- Moving average crossovers identify trend direction
- Enter when trend starts, exit when it ends

Theory: Since mean reversion failed on TSLA/NVDA/AMD, let's go with the trend.
When price is above rising moving averages, the path of least resistance is UP.
Don't predict reversals, just follow the trend.

Entry:
  - SPY > 200 SMA (bull market)
  - Price > 20 EMA > 50 EMA (uptrend structure)
  - Price just crossed above 20 EMA (fresh signal)

Exit:
  - Price < 20 EMA (trend broken)
  - OR 20 EMA < 50 EMA (trend reversed)
  - OR trailing stop 8%
"""

from AlgorithmImports import *


class TrendFollowing(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.fast_ema = 20
        self.slow_ema = 50
        self.trailing_stop_pct = 0.08

        self.position_size_dollars = 20000
        self.max_positions = 5

        self.entry_prices = {}
        self.highest_prices = {}
        self.positions_count = 0
        self.prev_above_fast = {}  # Track if price was below EMA yesterday

        self.tickers = ["TSLA", "NVDA", "AMD"]
        self.symbols = []
        self.indicators = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)
            self.indicators[symbol] = {
                "ema_fast": self.ema(symbol, self.fast_ema, Resolution.DAILY),
                "ema_slow": self.ema(symbol, self.slow_ema, Resolution.DAILY),
            }
            self.prev_above_fast[symbol] = False
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.set_warm_up(220, Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Regime filter
        if self.spy not in data or data[self.spy] is None or not self.spy_sma.is_ready or data[self.spy].close <= self.spy_sma.current.value:
            for s in self.symbols:
                if self.portfolio[s].invested:
                    self.liquidate(s)
            self.positions_count = 0
            self.entry_prices.clear()
            self.highest_prices.clear()
            return

        for symbol in self.symbols:
            if symbol not in data or data[symbol] is None:
                continue

            ind = self.indicators[symbol]
            if not ind["ema_fast"].is_ready or not ind["ema_slow"].is_ready:
                continue

            price = data[symbol].close
            ema_fast = ind["ema_fast"].current.value
            ema_slow = ind["ema_slow"].current.value

            price_above_fast = price > ema_fast
            fast_above_slow = ema_fast > ema_slow
            fresh_crossover = price_above_fast and not self.prev_above_fast.get(symbol, False)

            if self.portfolio[symbol].invested:
                # Update trailing stop
                if symbol in self.highest_prices:
                    self.highest_prices[symbol] = max(self.highest_prices[symbol], price)

                trailing_stop_price = self.highest_prices.get(symbol, price) * (1 - self.trailing_stop_pct)

                # Exit: Trend broken
                if price < ema_fast or not fast_above_slow or price < trailing_stop_price:
                    self.liquidate(symbol)
                    if symbol in self.entry_prices: del self.entry_prices[symbol]
                    if symbol in self.highest_prices: del self.highest_prices[symbol]
                    self.positions_count = max(0, self.positions_count - 1)

            elif self.positions_count < self.max_positions:
                # Entry: Fresh crossover above fast EMA, with uptrend structure
                if fresh_crossover and fast_above_slow:
                    shares = int(self.position_size_dollars / price)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.highest_prices[symbol] = price
                        self.positions_count += 1

            # Remember state for next day
            self.prev_above_fast[symbol] = price_above_fast

    def on_end_of_algorithm(self):
        self.log(f"Trend Following: ${self.portfolio.total_portfolio_value:,.2f}")
