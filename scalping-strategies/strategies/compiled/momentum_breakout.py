"""
Momentum Breakout Strategy

FIRST PRINCIPLES:
- High-beta stocks TREND strongly - momentum beats mean reversion
- Instead of buying weakness (failed in Round 2), buy strength
- "The trend is your friend" - ride momentum, don't fight it

Theory: When RSI > 70, the stock is NOT "overbought" - it's showing STRENGTH.
Strong stocks tend to stay strong. This is the opposite of mean reversion.

Entry:
  - SPY > 200 SMA (bull market)
  - RSI(14) > 65 (strong momentum, not extreme)
  - Price > 20 SMA (confirming uptrend)

Exit:
  - RSI < 50 (momentum fading)
  - OR trailing stop 5%
  - OR 10 day time limit
"""

from AlgorithmImports import *


class MomentumBreakout(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.rsi_period = 14
        self.rsi_entry = 65  # Strong momentum
        self.rsi_exit = 50   # Momentum fading
        self.sma_period = 20

        self.position_size_dollars = 20000
        self.trailing_stop_pct = 0.05
        self.max_holding_days = 10
        self.max_positions = 5

        self.entry_prices = {}
        self.entry_times = {}
        self.highest_prices = {}  # For trailing stop
        self.positions_count = 0

        self.tickers = ["TSLA", "NVDA", "AMD"]
        self.symbols = []
        self.indicators = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)
            self.indicators[symbol] = {
                "rsi": self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY),
                "sma": self.sma(symbol, self.sma_period, Resolution.DAILY),
            }
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.set_warm_up(220, Resolution.DAILY)
        self.set_benchmark("SPY")

        self.schedule.on(self.date_rules.every_day(), self.time_rules.before_market_close("SPY", 5), self.check_stops)

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
            self.entry_times.clear()
            self.highest_prices.clear()
            return

        for symbol in self.symbols:
            if symbol not in data or data[symbol] is None:
                continue

            ind = self.indicators[symbol]
            if not ind["rsi"].is_ready or not ind["sma"].is_ready:
                continue

            price = data[symbol].close
            rsi_value = ind["rsi"].current.value
            sma_value = ind["sma"].current.value

            if self.portfolio[symbol].invested:
                # Update highest price for trailing stop
                if symbol in self.highest_prices:
                    self.highest_prices[symbol] = max(self.highest_prices[symbol], price)

                # Exit: RSI fading OR trailing stop
                trailing_stop_price = self.highest_prices.get(symbol, price) * (1 - self.trailing_stop_pct)

                if rsi_value < self.rsi_exit or price < trailing_stop_price:
                    self.liquidate(symbol)
                    if symbol in self.entry_prices: del self.entry_prices[symbol]
                    if symbol in self.entry_times: del self.entry_times[symbol]
                    if symbol in self.highest_prices: del self.highest_prices[symbol]
                    self.positions_count = max(0, self.positions_count - 1)

            elif self.positions_count < self.max_positions:
                # Entry: Strong momentum + price above SMA (confirming trend)
                if rsi_value > self.rsi_entry and price > sma_value:
                    shares = int(self.position_size_dollars / price)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.entry_times[symbol] = self.time
                        self.highest_prices[symbol] = price
                        self.positions_count += 1

    def check_stops(self):
        for symbol in list(self.entry_times.keys()):
            if (self.time - self.entry_times[symbol]).days >= self.max_holding_days:
                self.liquidate(symbol)
                if symbol in self.entry_prices: del self.entry_prices[symbol]
                if symbol in self.entry_times: del self.entry_times[symbol]
                if symbol in self.highest_prices: del self.highest_prices[symbol]
                self.positions_count = max(0, self.positions_count - 1)

    def on_end_of_algorithm(self):
        self.log(f"Momentum Breakout: ${self.portfolio.total_portfolio_value:,.2f}")
