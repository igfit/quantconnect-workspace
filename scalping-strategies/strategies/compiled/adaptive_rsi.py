"""
Adaptive RSI Strategy

FIRST PRINCIPLES:
- Fixed RSI thresholds don't account for changing market conditions
- In high volatility, RSI extremes are less meaningful (noise)
- In low volatility, RSI extremes are more significant (true moves)

Custom Adaptive RSI:
  - Measure RSI relative to its recent standard deviation
  - RSI Z-Score = (RSI - RSI_mean) / RSI_std
  - Entry at RSI Z-Score < -2 (2 std devs below mean)
  - This adapts to the stock's typical RSI behavior

Theory: A stock that normally ranges RSI 40-60 showing RSI 25 is more
significant than a volatile stock that regularly hits RSI 20.
"""

from AlgorithmImports import *
import statistics


class AdaptiveRSI(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.rsi_period = 5
        self.lookback = 50  # For calculating RSI mean/std
        self.entry_zscore = -1.5  # 1.5 std devs below mean (relaxed)
        self.exit_zscore = 0.0    # Return to mean

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
        self.rsi_history = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)
            self.indicators[symbol] = {
                "rsi": self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY),
            }
            self.rsi_history[symbol] = []
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.set_warm_up(220, Resolution.DAILY)
        self.set_benchmark("SPY")

        self.schedule.on(self.date_rules.every_day(), self.time_rules.before_market_close("SPY", 5), self.check_time_stops)

    def calculate_rsi_zscore(self, symbol, current_rsi):
        """Calculate RSI Z-score relative to recent history"""
        history = self.rsi_history[symbol]
        if len(history) < 20:
            return 0

        mean_rsi = statistics.mean(history)
        std_rsi = statistics.stdev(history) if len(history) > 1 else 1

        if std_rsi < 0.1:  # Avoid division by near-zero
            std_rsi = 0.1

        return (current_rsi - mean_rsi) / std_rsi

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Update RSI history
        for symbol in self.symbols:
            if symbol in data and data[symbol] is not None:
                rsi = self.indicators[symbol]["rsi"]
                if rsi.is_ready:
                    self.rsi_history[symbol].append(rsi.current.value)
                    if len(self.rsi_history[symbol]) > self.lookback + 5:
                        self.rsi_history[symbol] = self.rsi_history[symbol][-self.lookback-5:]

        # Regime filter
        if self.spy not in data or data[self.spy] is None or not self.spy_sma.is_ready or data[self.spy].close <= self.spy_sma.current.value:
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

            rsi = self.indicators[symbol]["rsi"]
            if not rsi.is_ready:
                continue
            if len(self.rsi_history[symbol]) < self.lookback:
                continue

            rsi_value = rsi.current.value
            price = data[symbol].close
            rsi_zscore = self.calculate_rsi_zscore(symbol, rsi_value)

            if self.portfolio[symbol].invested:
                # Exit when RSI returns to mean
                if rsi_zscore > self.exit_zscore:
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
                # Entry: RSI significantly below its own mean
                if rsi_zscore < self.entry_zscore:
                    shares = int(self.position_size_dollars / price)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.entry_times[symbol] = self.time
                        self.positions_count += 1
                        self.debug(f"{self.time.date()}: ENTRY {symbol} - RSI={rsi_value:.1f}, Z={rsi_zscore:.2f}")

    def check_time_stops(self):
        for symbol in list(self.entry_times.keys()):
            if (self.time - self.entry_times[symbol]).days >= self.max_holding_days:
                self.liquidate(symbol)
                if symbol in self.entry_prices: del self.entry_prices[symbol]
                if symbol in self.entry_times: del self.entry_times[symbol]
                self.positions_count = max(0, self.positions_count - 1)

    def on_end_of_algorithm(self):
        self.log(f"Adaptive RSI: ${self.portfolio.total_portfolio_value:,.2f}")
