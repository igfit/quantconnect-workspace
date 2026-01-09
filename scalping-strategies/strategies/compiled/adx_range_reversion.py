"""
ADX Range-Filtered Mean Reversion Strategy

FIRST PRINCIPLES:
- Mean reversion ONLY works in ranging markets, NOT in trends
- ADX (Average Directional Index) measures trend strength
- ADX < 25 = no trend (ranging), ADX > 25 = trending

Theory: The failure of mean reversion in Round 2 was because we traded
during TRENDS. By filtering for ranging markets (ADX < 25), we only
take mean reversion trades when they're likely to work.

Entry:
  - SPY > 200 SMA (bull market)
  - ADX(14) < 25 (ranging, no trend)
  - RSI(5) < 35 (oversold in range)

Exit:
  - RSI > 55 OR ADX > 30 (trend starting, abort)
  - 5 day time limit
  - 5% stop loss
"""

from AlgorithmImports import *


class ADXRangeReversion(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.rsi_period = 5
        self.rsi_entry = 35
        self.rsi_exit = 55
        self.adx_period = 14
        self.adx_range_max = 25   # Below this = ranging
        self.adx_trend_exit = 30  # Above this = strong trend, exit

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

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)
            self.indicators[symbol] = {
                "rsi": self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY),
                "adx": self.adx(symbol, self.adx_period, Resolution.DAILY),
            }
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

            ind = self.indicators[symbol]
            if not ind["rsi"].is_ready or not ind["adx"].is_ready:
                continue

            price = data[symbol].close
            rsi_value = ind["rsi"].current.value
            adx_value = ind["adx"].current.value

            if self.portfolio[symbol].invested:
                # Exit: RSI recovery OR trend emerging OR stop loss
                if rsi_value > self.rsi_exit or adx_value > self.adx_trend_exit:
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
                # Entry: Ranging market (low ADX) + oversold
                if adx_value < self.adx_range_max and rsi_value < self.rsi_entry:
                    shares = int(self.position_size_dollars / price)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.entry_times[symbol] = self.time
                        self.positions_count += 1

    def check_time_stops(self):
        for symbol in list(self.entry_times.keys()):
            if (self.time - self.entry_times[symbol]).days >= self.max_holding_days:
                self.liquidate(symbol)
                if symbol in self.entry_prices: del self.entry_prices[symbol]
                if symbol in self.entry_times: del self.entry_times[symbol]
                self.positions_count = max(0, self.positions_count - 1)

    def on_end_of_algorithm(self):
        self.log(f"ADX Range Reversion: ${self.portfolio.total_portfolio_value:,.2f}")
