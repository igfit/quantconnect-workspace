"""
Money Flow Index (MFI) Divergence Strategy

FIRST PRINCIPLES:
- MFI = Volume-weighted RSI (considers where money is flowing)
- Divergence: Price makes new low but MFI doesn't = accumulation happening
- "Smart money" is buying even as price falls

Theory: MFI divergence shows institutional accumulation during weakness.
When price makes a lower low but MFI makes a higher low, buyers are
stepping in at better prices - a bullish setup.

Entry:
  - SPY > 200 SMA (bull market)
  - Price makes 10-day low
  - MFI(14) > previous low (bullish divergence)
  - MFI < 40 (still in oversold territory)

Exit:
  - MFI > 60 (overbought)
  - 7 day time stop
  - 5% stop loss
"""

from AlgorithmImports import *


class MFIDivergence(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.mfi_period = 14
        self.mfi_oversold = 40
        self.mfi_overbought = 60
        self.price_lookback = 10  # Look for 10-day lows

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
        self.mfi_history = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)
            self.indicators[symbol] = {
                "mfi": self.mfi(symbol, self.mfi_period, Resolution.DAILY),
            }
            self.price_history[symbol] = []
            self.mfi_history[symbol] = []
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
                mfi = self.indicators[symbol]["mfi"]
                if mfi.is_ready:
                    self.price_history[symbol].append(data[symbol].close)
                    self.mfi_history[symbol].append(mfi.current.value)
                    if len(self.price_history[symbol]) > self.price_lookback + 5:
                        self.price_history[symbol] = self.price_history[symbol][-self.price_lookback-5:]
                        self.mfi_history[symbol] = self.mfi_history[symbol][-self.price_lookback-5:]

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

            mfi = self.indicators[symbol]["mfi"]
            if not mfi.is_ready:
                continue
            if len(self.price_history[symbol]) < self.price_lookback:
                continue

            mfi_value = mfi.current.value
            price = data[symbol].close
            prices = self.price_history[symbol]
            mfis = self.mfi_history[symbol]

            # Check for bullish divergence
            is_price_low = price <= min(prices[-self.price_lookback:])

            # Find previous price low and corresponding MFI
            prev_low_idx = None
            prev_low_price = float('inf')
            for i in range(max(0, len(prices) - self.price_lookback), len(prices) - 3):
                if prices[i] < prev_low_price:
                    prev_low_price = prices[i]
                    prev_low_idx = i

            has_divergence = False
            if prev_low_idx is not None and is_price_low and len(mfis) > prev_low_idx:
                # Price making new low, but MFI higher than at previous low
                if price < prev_low_price and mfi_value > mfis[prev_low_idx]:
                    has_divergence = True

            if self.portfolio[symbol].invested:
                if mfi_value > self.mfi_overbought:
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
                # Entry: Bullish divergence + MFI still oversold
                if has_divergence and mfi_value < self.mfi_oversold:
                    shares = int(self.position_size_dollars / price)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.entry_times[symbol] = self.time
                        self.positions_count += 1
                        self.debug(f"{self.time.date()}: ENTRY {symbol} - MFI Divergence, MFI={mfi_value:.1f}")

    def check_time_stops(self):
        for symbol in list(self.entry_times.keys()):
            if (self.time - self.entry_times[symbol]).days >= self.max_holding_days:
                self.liquidate(symbol)
                if symbol in self.entry_prices: del self.entry_prices[symbol]
                if symbol in self.entry_times: del self.entry_times[symbol]
                self.positions_count = max(0, self.positions_count - 1)

    def on_end_of_algorithm(self):
        self.log(f"MFI Divergence: ${self.portfolio.total_portfolio_value:,.2f}")
