"""
Volatility Compression Strategy

FIRST PRINCIPLES:
- Markets alternate between low and high volatility
- After compression (low volatility), expansion follows
- Direction of expansion is indicated by trend context

Theory: Volatility compression is like a coiled spring.
When ATR falls below its average, energy is building up.
Combined with oversold conditions in an uptrend = explosive bounce potential.

Custom Indicator: Volatility Compression Score
  - ATR Percentile: Where is current ATR vs last 50 bars?
  - Bollinger Band Width: Narrow bands = compression

Entry:
  - SPY > 200 SMA (bull market)
  - ATR < 50th percentile of last 50 bars (compressed)
  - BB Width < 50th percentile (narrow bands)
  - RSI < 40 (oversold during compression)

Exit:
  - ATR > 75th percentile (expansion happened)
  - OR RSI > 60
  - OR 7 day time stop
"""

from AlgorithmImports import *


class VolatilityCompression(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.atr_period = 14
        self.bb_period = 20
        self.lookback = 50
        self.compression_percentile = 50
        self.expansion_percentile = 75
        self.rsi_entry = 40
        self.rsi_exit = 60

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
        self.atr_history = {}
        self.bbw_history = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)
            self.indicators[symbol] = {
                "atr": self.atr(symbol, self.atr_period, MovingAverageType.SIMPLE, Resolution.DAILY),
                "bb": self.bb(symbol, self.bb_period, 2.0, MovingAverageType.SIMPLE, Resolution.DAILY),
                "rsi": self.rsi(symbol, 5, MovingAverageType.WILDERS, Resolution.DAILY),
            }
            self.atr_history[symbol] = []
            self.bbw_history[symbol] = []
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.set_warm_up(250, Resolution.DAILY)
        self.set_benchmark("SPY")

        self.schedule.on(self.date_rules.every_day(), self.time_rules.before_market_close("SPY", 5), self.check_time_stops)

    def calculate_percentile(self, value, history):
        """Calculate percentile rank of value in history"""
        if len(history) < 10:
            return 50
        count_below = sum(1 for h in history if h < value)
        return (count_below / len(history)) * 100

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Update history
        for symbol in self.symbols:
            if symbol in data and data[symbol] is not None:
                ind = self.indicators[symbol]
                if ind["atr"].is_ready and ind["bb"].is_ready:
                    atr_val = ind["atr"].current.value
                    bb_width = ind["bb"].upper_band.current.value - ind["bb"].lower_band.current.value

                    self.atr_history[symbol].append(atr_val)
                    self.bbw_history[symbol].append(bb_width)

                    if len(self.atr_history[symbol]) > self.lookback + 5:
                        self.atr_history[symbol] = self.atr_history[symbol][-self.lookback-5:]
                        self.bbw_history[symbol] = self.bbw_history[symbol][-self.lookback-5:]

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
            if not all([ind["atr"].is_ready, ind["bb"].is_ready, ind["rsi"].is_ready]):
                continue
            if len(self.atr_history[symbol]) < self.lookback:
                continue

            price = data[symbol].close
            atr_val = ind["atr"].current.value
            bb_width = ind["bb"].upper_band.current.value - ind["bb"].lower_band.current.value
            rsi_val = ind["rsi"].current.value

            atr_pct = self.calculate_percentile(atr_val, self.atr_history[symbol])
            bbw_pct = self.calculate_percentile(bb_width, self.bbw_history[symbol])

            if self.portfolio[symbol].invested:
                # Exit on expansion or RSI recovery
                if atr_pct > self.expansion_percentile or rsi_val > self.rsi_exit:
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
                # Entry: Compression (low ATR + narrow BB) + Oversold
                if (atr_pct < self.compression_percentile and
                    bbw_pct < self.compression_percentile and
                    rsi_val < self.rsi_entry):

                    shares = int(self.position_size_dollars / price)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.entry_times[symbol] = self.time
                        self.positions_count += 1
                        self.debug(f"{self.time.date()}: ENTRY {symbol} - Compression, ATR%={atr_pct:.0f}, BBW%={bbw_pct:.0f}, RSI={rsi_val:.1f}")

    def check_time_stops(self):
        for symbol in list(self.entry_times.keys()):
            if (self.time - self.entry_times[symbol]).days >= self.max_holding_days:
                self.liquidate(symbol)
                if symbol in self.entry_prices: del self.entry_prices[symbol]
                if symbol in self.entry_times: del self.entry_times[symbol]
                self.positions_count = max(0, self.positions_count - 1)

    def on_end_of_algorithm(self):
        self.log(f"Volatility Compression: ${self.portfolio.total_portfolio_value:,.2f}")
