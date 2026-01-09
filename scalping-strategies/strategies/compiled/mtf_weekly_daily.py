"""
Multi-Timeframe Strategy: Weekly Trend + Daily Entry

FIRST PRINCIPLES:
- Higher timeframes show the dominant trend (noise filtered)
- Lower timeframes provide precise entry timing
- Buy pullbacks in the direction of the higher timeframe trend

Structure:
  WEEKLY: Determines DIRECTION
    - EMA(10) > EMA(20) = Bullish trend
    - Only take long entries in bullish trend

  DAILY: Determines ENTRY TIMING
    - RSI(5) < 35 = Oversold pullback in uptrend
    - This is "buying the dip" with trend confirmation

Theory: Weekly uptrend means institutions are accumulating.
Daily oversold in this context = short-term profit-taking, not trend change.
"""

from AlgorithmImports import *


class MTFWeeklyDaily(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Daily parameters
        self.rsi_period = 5
        self.rsi_entry = 35
        self.rsi_exit = 55

        # Weekly parameters
        self.weekly_ema_fast = 10
        self.weekly_ema_slow = 20

        self.position_size_dollars = 20000
        self.stop_loss_pct = 0.05
        self.max_holding_days = 5
        self.max_positions = 5

        self.entry_prices = {}
        self.entry_times = {}
        self.positions_count = 0

        self.tickers = ["TSLA", "NVDA", "AMD"]
        self.symbols = []
        self.daily_indicators = {}
        self.weekly_trend = {}  # True = bullish, False = bearish

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)

            # Daily indicators
            self.daily_indicators[symbol] = {
                "rsi": self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY),
            }

            # Weekly consolidator for trend
            weekly_consolidator = TradeBarConsolidator(timedelta(days=5))
            weekly_consolidator.data_consolidated += self.on_weekly_data
            self.subscription_manager.add_consolidator(symbol, weekly_consolidator)

            self.weekly_trend[symbol] = False

            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        # Weekly EMAs - we'll calculate manually from consolidated data
        self.weekly_prices = {s: [] for s in self.symbols}
        self.weekly_ema_fast_vals = {s: None for s in self.symbols}
        self.weekly_ema_slow_vals = {s: None for s in self.symbols}

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.set_warm_up(250, Resolution.DAILY)
        self.set_benchmark("SPY")

        self.schedule.on(self.date_rules.every_day(), self.time_rules.before_market_close("SPY", 5), self.check_time_stops)

    def on_weekly_data(self, sender, bar):
        """Handle weekly consolidated data"""
        symbol = bar.symbol

        # Add to price history
        self.weekly_prices[symbol].append(bar.close)
        if len(self.weekly_prices[symbol]) > 30:
            self.weekly_prices[symbol] = self.weekly_prices[symbol][-30:]

        # Calculate EMAs
        prices = self.weekly_prices[symbol]
        if len(prices) >= self.weekly_ema_slow:
            # Simple EMA calculation
            fast_mult = 2 / (self.weekly_ema_fast + 1)
            slow_mult = 2 / (self.weekly_ema_slow + 1)

            # Initialize EMAs with SMA
            if self.weekly_ema_fast_vals[symbol] is None:
                self.weekly_ema_fast_vals[symbol] = sum(prices[-self.weekly_ema_fast:]) / self.weekly_ema_fast
                self.weekly_ema_slow_vals[symbol] = sum(prices[-self.weekly_ema_slow:]) / self.weekly_ema_slow
            else:
                # Update EMAs
                self.weekly_ema_fast_vals[symbol] = (bar.close - self.weekly_ema_fast_vals[symbol]) * fast_mult + self.weekly_ema_fast_vals[symbol]
                self.weekly_ema_slow_vals[symbol] = (bar.close - self.weekly_ema_slow_vals[symbol]) * slow_mult + self.weekly_ema_slow_vals[symbol]

            # Determine trend
            self.weekly_trend[symbol] = self.weekly_ema_fast_vals[symbol] > self.weekly_ema_slow_vals[symbol]

    def on_data(self, data):
        if self.is_warming_up:
            return

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

            rsi = self.daily_indicators[symbol]["rsi"]
            if not rsi.is_ready:
                continue

            rsi_value = rsi.current.value
            price = data[symbol].close
            is_weekly_bullish = self.weekly_trend.get(symbol, False)

            if self.portfolio[symbol].invested:
                # Exit conditions
                if rsi_value > self.rsi_exit:
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
                # Entry: Weekly bullish + Daily oversold
                if is_weekly_bullish and rsi_value < self.rsi_entry:
                    shares = int(self.position_size_dollars / price)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.entry_times[symbol] = self.time
                        self.positions_count += 1
                        self.debug(f"{self.time.date()}: ENTRY {symbol} - Weekly BULL, Daily RSI={rsi_value:.1f}")

    def check_time_stops(self):
        for symbol in list(self.entry_times.keys()):
            if (self.time - self.entry_times[symbol]).days >= self.max_holding_days:
                self.liquidate(symbol)
                if symbol in self.entry_prices: del self.entry_prices[symbol]
                if symbol in self.entry_times: del self.entry_times[symbol]
                self.positions_count = max(0, self.positions_count - 1)

    def on_end_of_algorithm(self):
        self.log(f"MTF Weekly-Daily: ${self.portfolio.total_portfolio_value:,.2f}")
