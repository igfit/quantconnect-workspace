"""
Swing Structure Strategy

FIRST PRINCIPLES:
- Price moves in swings (higher highs/higher lows in uptrend)
- A pullback to a prior swing low in an uptrend is strong support
- Buying near support with trend = high probability setup

Custom Indicator: Distance to Recent Swing Low
  - Track swing lows (local minima over 5 bars)
  - Entry when price approaches recent swing low
  - Combined with RSI confirmation

Theory: In an uptrend, previous resistance becomes support.
When price pulls back to test this support level AND is oversold,
institutional buyers step in to defend the level.
"""

from AlgorithmImports import *


class SwingStructure(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.swing_lookback = 5  # Bars on each side for swing detection
        self.proximity_threshold = 0.02  # Within 2% of swing low
        self.rsi_entry = 40
        self.rsi_exit = 55

        self.position_size_dollars = 20000
        self.stop_loss_pct = 0.05
        self.max_holding_days = 5
        self.max_positions = 5

        self.entry_prices = {}
        self.entry_times = {}
        self.positions_count = 0

        self.tickers = ["TSLA", "NVDA", "AMD"]
        self.symbols = []
        self.indicators = {}
        self.price_history = {}
        self.swing_lows = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)
            self.indicators[symbol] = {
                "rsi": self.rsi(symbol, 5, MovingAverageType.WILDERS, Resolution.DAILY),
                "sma50": self.sma(symbol, 50, Resolution.DAILY),
            }
            self.price_history[symbol] = []
            self.swing_lows[symbol] = []
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.set_warm_up(220, Resolution.DAILY)
        self.set_benchmark("SPY")

        self.schedule.on(self.date_rules.every_day(), self.time_rules.before_market_close("SPY", 5), self.check_time_stops)

    def find_swing_lows(self, prices):
        """Find swing lows in price history"""
        swing_lows = []
        if len(prices) < self.swing_lookback * 2 + 1:
            return swing_lows

        for i in range(self.swing_lookback, len(prices) - self.swing_lookback):
            is_swing_low = True
            for j in range(1, self.swing_lookback + 1):
                if prices[i] >= prices[i - j] or prices[i] >= prices[i + j]:
                    is_swing_low = False
                    break
            if is_swing_low:
                swing_lows.append(prices[i])

        return swing_lows[-3:] if len(swing_lows) > 3 else swing_lows  # Keep last 3

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Update price history and detect swing lows
        for symbol in self.symbols:
            if symbol in data and data[symbol] is not None:
                self.price_history[symbol].append(data[symbol].low)
                if len(self.price_history[symbol]) > 60:
                    self.price_history[symbol] = self.price_history[symbol][-60:]

                self.swing_lows[symbol] = self.find_swing_lows(self.price_history[symbol])

        # Regime filter
        if self.spy not in data or not self.spy_sma.is_ready or data[self.spy].close <= self.spy_sma.current.value:
            for s in self.symbols:
                if self.portfolio[s].invested:
                    self.liquidate(s)
            self.positions_count = 0
            self.entry_prices.clear()
            self.entry_times.clear()
            return

        for symbol in self.symbols:
            if symbol not in data or data[symbol] is None:
                continue

            ind = self.indicators[symbol]
            if not ind["rsi"].is_ready or not ind["sma50"].is_ready:
                continue
            if len(self.swing_lows[symbol]) == 0:
                continue

            price = data[symbol].close
            rsi = ind["rsi"].current.value
            sma50 = ind["sma50"].current.value

            # Check if price is near any recent swing low
            near_swing_low = False
            for swing_low in self.swing_lows[symbol]:
                distance_pct = (price - swing_low) / swing_low
                if -self.proximity_threshold <= distance_pct <= self.proximity_threshold:
                    near_swing_low = True
                    break

            # Is price in uptrend? (above 50 SMA)
            in_uptrend = price > sma50

            if self.portfolio[symbol].invested:
                if rsi > self.rsi_exit:
                    self.liquidate(symbol)
                    if symbol in self.entry_prices: del self.entry_prices[symbol]
                    if symbol in self.entry_times: del self.entry_times[symbol]
                    self.positions_count = max(0, self.positions_count - 1)
                elif symbol in self.entry_prices and (price - self.entry_prices[symbol]) / self.entry_prices[symbol] < -self.stop_loss_pct:
                    self.liquidate(symbol)
                    if symbol in self.entry_prices: del self.entry_prices[symbol]
                    if symbol in self.entry_times: del self.entry_times[symbol]
                    self.positions_count = max(0, self.positions_count - 1)

            elif self.positions_count < self.max_positions:
                # Entry: Uptrend + Near swing low + RSI oversold
                if in_uptrend and near_swing_low and rsi < self.rsi_entry:
                    shares = int(self.position_size_dollars / price)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.entry_times[symbol] = self.time
                        self.positions_count += 1
                        self.debug(f"{self.time.date()}: ENTRY {symbol} - Near swing low, RSI={rsi:.1f}")

    def check_time_stops(self):
        for symbol in list(self.entry_times.keys()):
            if (self.time - self.entry_times[symbol]).days >= self.max_holding_days:
                self.liquidate(symbol)
                if symbol in self.entry_prices: del self.entry_prices[symbol]
                if symbol in self.entry_times: del self.entry_times[symbol]
                self.positions_count = max(0, self.positions_count - 1)

    def on_end_of_algorithm(self):
        self.log(f"Swing Structure: ${self.portfolio.total_portfolio_value:,.2f}")
