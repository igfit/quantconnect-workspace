"""
Dual Momentum Strategy

FIRST PRINCIPLES:
- Absolute momentum: Is the stock going UP? (12-month return > 0)
- Relative momentum: Is it beating alternatives? (vs SPY)
- Only buy stocks with BOTH positive absolute AND relative momentum

Theory: Stocks with momentum tend to continue. But we want the BEST
momentum stocks - those outperforming the market. This combines trend
following (absolute) with relative strength (relative).

Entry:
  - SPY > 200 SMA (bull market)
  - Stock 3-month return > 0 (absolute momentum)
  - Stock 3-month return > SPY 3-month return (relative momentum)
  - RSI(14) > 50 (confirming momentum)

Exit:
  - 3-month return < 0 (lost absolute momentum)
  - OR trailing stop 10%
"""

from AlgorithmImports import *


class DualMomentum(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.lookback = 63  # ~3 months
        self.rsi_period = 14
        self.rsi_threshold = 50
        self.trailing_stop_pct = 0.10

        self.position_size_dollars = 20000
        self.max_positions = 5

        self.entry_prices = {}
        self.highest_prices = {}
        self.positions_count = 0

        self.tickers = ["TSLA", "NVDA", "AMD"]
        self.symbols = []
        self.indicators = {}
        self.price_history = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)
            self.indicators[symbol] = {
                "rsi": self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY),
            }
            self.price_history[symbol] = []
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_prices = []
        self.set_warm_up(250, Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Update price histories
        if self.spy in data and data[self.spy] is not None:
            self.spy_prices.append(data[self.spy].close)
            if len(self.spy_prices) > self.lookback + 5:
                self.spy_prices = self.spy_prices[-self.lookback-5:]

        for symbol in self.symbols:
            if symbol in data and data[symbol] is not None:
                self.price_history[symbol].append(data[symbol].close)
                if len(self.price_history[symbol]) > self.lookback + 5:
                    self.price_history[symbol] = self.price_history[symbol][-self.lookback-5:]

        # Regime filter
        if self.spy not in data or data[self.spy] is None or not self.spy_sma.is_ready or data[self.spy].close <= self.spy_sma.current.value:
            for s in self.symbols:
                if self.portfolio[s].invested:
                    self.liquidate(s)
            self.positions_count = 0
            self.entry_prices.clear()
            self.highest_prices.clear()
            return

        # Calculate SPY momentum
        spy_momentum = 0
        if len(self.spy_prices) >= self.lookback:
            spy_momentum = (self.spy_prices[-1] / self.spy_prices[-self.lookback]) - 1

        for symbol in self.symbols:
            if symbol not in data or data[symbol] is None:
                continue

            if len(self.price_history[symbol]) < self.lookback:
                continue

            rsi = self.indicators[symbol]["rsi"]
            if not rsi.is_ready:
                continue

            price = data[symbol].close
            rsi_value = rsi.current.value

            # Calculate momentum
            prices = self.price_history[symbol]
            stock_momentum = (prices[-1] / prices[-self.lookback]) - 1

            absolute_momentum = stock_momentum > 0
            relative_momentum = stock_momentum > spy_momentum

            if self.portfolio[symbol].invested:
                # Update trailing stop
                if symbol in self.highest_prices:
                    self.highest_prices[symbol] = max(self.highest_prices[symbol], price)

                trailing_stop_price = self.highest_prices.get(symbol, price) * (1 - self.trailing_stop_pct)

                # Exit: Lost absolute momentum OR trailing stop
                if not absolute_momentum or price < trailing_stop_price:
                    self.liquidate(symbol)
                    if symbol in self.entry_prices: del self.entry_prices[symbol]
                    if symbol in self.highest_prices: del self.highest_prices[symbol]
                    self.positions_count = max(0, self.positions_count - 1)

            elif self.positions_count < self.max_positions:
                # Entry: Dual momentum (absolute + relative) + RSI confirming
                if absolute_momentum and relative_momentum and rsi_value > self.rsi_threshold:
                    shares = int(self.position_size_dollars / price)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.highest_prices[symbol] = price
                        self.positions_count += 1

    def on_end_of_algorithm(self):
        self.log(f"Dual Momentum: ${self.portfolio.total_portfolio_value:,.2f}")
