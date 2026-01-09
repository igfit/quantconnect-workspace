"""
On-Balance Volume (OBV) Divergence Strategy

FIRST PRINCIPLES:
- OBV tracks cumulative volume flow (up days add volume, down days subtract)
- OBV divergence: Price makes new low but OBV doesn't = accumulation
- "Volume precedes price" - smart money accumulating before price moves

Theory: When OBV makes a higher low while price makes a lower low,
it signals that despite falling prices, more volume is going into
buying than selling. This often precedes a reversal.

Entry:
  - SPY > 200 SMA (bull market)
  - Price makes 10-day low
  - OBV > its level at the previous price low (bullish divergence)
  - RSI < 40 (confirming oversold)

Exit:
  - RSI > 55
  - OR 7 day time stop
"""

from AlgorithmImports import *


class OBVDivergence(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.lookback = 10
        self.rsi_entry = 40
        self.rsi_exit = 55

        self.position_size_dollars = 20000
        self.stop_loss_pct = 0.05
        self.max_holding_days = 7
        self.max_positions = 5

        self.entry_prices = {}
        self.entry_times = {}
        self.positions_count = 0

        self.tickers = ["TSLA", "NVDA", "AMD"]
        self.symbols = []
        self.indicators = {}
        self.price_history = {}
        self.obv_history = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)
            self.indicators[symbol] = {
                "obv": self.obv(symbol, Resolution.DAILY),
                "rsi": self.rsi(symbol, 5, MovingAverageType.WILDERS, Resolution.DAILY),
            }
            self.price_history[symbol] = []
            self.obv_history[symbol] = []
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.set_warm_up(220, Resolution.DAILY)
        self.set_benchmark("SPY")

        self.schedule.on(self.date_rules.every_day(), self.time_rules.before_market_close("SPY", 5), self.check_time_stops)

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Update history
        for symbol in self.symbols:
            if symbol in data and data[symbol] is not None:
                obv = self.indicators[symbol]["obv"]
                if obv.is_ready:
                    self.price_history[symbol].append(data[symbol].close)
                    self.obv_history[symbol].append(obv.current.value)
                    if len(self.price_history[symbol]) > self.lookback + 5:
                        self.price_history[symbol] = self.price_history[symbol][-self.lookback-5:]
                        self.obv_history[symbol] = self.obv_history[symbol][-self.lookback-5:]

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
            if not ind["obv"].is_ready or not ind["rsi"].is_ready:
                continue
            if len(self.price_history[symbol]) < self.lookback:
                continue

            price = data[symbol].close
            obv_current = ind["obv"].current.value
            rsi = ind["rsi"].current.value
            prices = self.price_history[symbol]
            obvs = self.obv_history[symbol]

            # Check for bullish divergence
            # Find the previous low in the lookback period
            prev_low_price = min(prices[:-1]) if len(prices) > 1 else price
            prev_low_idx = prices[:-1].index(prev_low_price) if prev_low_price in prices[:-1] else -1

            has_divergence = False
            if prev_low_idx >= 0 and len(obvs) > prev_low_idx:
                # Price making new low but OBV higher
                if price < prev_low_price and obv_current > obvs[prev_low_idx]:
                    has_divergence = True

            # Also check if current price is at/near lookback low
            is_near_low = price <= min(prices[-self.lookback:]) * 1.01

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
                # Entry: OBV divergence + RSI oversold + at/near low
                if has_divergence and rsi < self.rsi_entry and is_near_low:
                    shares = int(self.position_size_dollars / price)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.entry_times[symbol] = self.time
                        self.positions_count += 1
                        self.debug(f"{self.time.date()}: ENTRY {symbol} - OBV Divergence, RSI={rsi:.1f}")

    def check_time_stops(self):
        for symbol in list(self.entry_times.keys()):
            if (self.time - self.entry_times[symbol]).days >= self.max_holding_days:
                self.liquidate(symbol)
                if symbol in self.entry_prices: del self.entry_prices[symbol]
                if symbol in self.entry_times: del self.entry_times[symbol]
                self.positions_count = max(0, self.positions_count - 1)

    def on_end_of_algorithm(self):
        self.log(f"OBV Divergence: ${self.portfolio.total_portfolio_value:,.2f}")
