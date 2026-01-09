"""
Volume Exhaustion Strategy

FIRST PRINCIPLES:
- When price drops on DECLINING volume, selling pressure is exhausted
- Capitulation happens on HIGH volume, then volume dries up
- Entry when: Price oversold + Volume below average = sellers done

Theory: Volume confirms price moves. A decline on low volume lacks conviction.
The "smart money" has finished selling, only weak hands remain.

Entry:
  - SPY > 200 SMA (bull market)
  - Price down 3+ days in a row
  - RSI(5) < 40 (oversold but not extreme)
  - Current volume < 50% of 20-day average (exhaustion)

Exit:
  - RSI > 55 OR volume spike (new buyers)
  - 5 day time stop
  - 5% stop loss
"""

from AlgorithmImports import *


class VolumeExhaustion(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Parameters derived from first principles
        self.rsi_period = 5
        self.rsi_entry = 40  # Not extreme - we want exhaustion, not capitulation
        self.rsi_exit = 55
        self.volume_lookback = 20
        self.volume_threshold = 0.7  # Volume < 70% of average (relaxed)
        self.consecutive_down_days = 2  # 2+ down days (relaxed)

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
        self.volume_history = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)
            self.indicators[symbol] = {
                "rsi": self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY),
            }
            self.price_history[symbol] = []
            self.volume_history[symbol] = []
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

        # Update price/volume history
        for symbol in self.symbols:
            if symbol in data and data[symbol] is not None:
                self.price_history[symbol].append(data[symbol].close)
                self.volume_history[symbol].append(data[symbol].volume)
                # Keep only needed history
                if len(self.price_history[symbol]) > self.volume_lookback + 5:
                    self.price_history[symbol] = self.price_history[symbol][-self.volume_lookback-5:]
                    self.volume_history[symbol] = self.volume_history[symbol][-self.volume_lookback-5:]

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
            if len(self.price_history[symbol]) < self.volume_lookback:
                continue

            rsi_value = rsi.current.value
            price = data[symbol].close
            volume = data[symbol].volume

            # Calculate volume ratio
            avg_volume = sum(self.volume_history[symbol][-self.volume_lookback:]) / self.volume_lookback
            volume_ratio = volume / avg_volume if avg_volume > 0 else 1.0

            # Count consecutive down days
            prices = self.price_history[symbol]
            down_days = 0
            for i in range(1, min(len(prices), 6)):
                if prices[-i] < prices[-i-1] if len(prices) > i else False:
                    down_days += 1
                else:
                    break

            if self.portfolio[symbol].invested:
                # Exit on RSI recovery OR volume spike (new buyers entering)
                if rsi_value > self.rsi_exit or volume_ratio > 1.5:
                    self.liquidate(symbol)
                    if symbol in self.entry_prices: del self.entry_prices[symbol]
                    if symbol in self.entry_times: del self.entry_times[symbol]
                    self.positions_count = max(0, self.positions_count - 1)
                # Stop loss
                elif symbol in self.entry_prices and (price - self.entry_prices[symbol]) / self.entry_prices[symbol] < -self.stop_loss_pct:
                    self.liquidate(symbol)
                    if symbol in self.entry_prices: del self.entry_prices[symbol]
                    if symbol in self.entry_times: del self.entry_times[symbol]
                    self.positions_count = max(0, self.positions_count - 1)

            elif self.positions_count < self.max_positions:
                # Entry: RSI oversold + consecutive down days + LOW volume (exhaustion)
                if (rsi_value < self.rsi_entry and
                    down_days >= self.consecutive_down_days and
                    volume_ratio < self.volume_threshold):

                    shares = int(self.position_size_dollars / price)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.entry_times[symbol] = self.time
                        self.positions_count += 1
                        self.debug(f"{self.time.date()}: ENTRY {symbol} - RSI={rsi_value:.1f}, VolRatio={volume_ratio:.2f}, DownDays={down_days}")

    def check_time_stops(self):
        for symbol in list(self.entry_times.keys()):
            if (self.time - self.entry_times[symbol]).days >= self.max_holding_days:
                self.liquidate(symbol)
                if symbol in self.entry_prices: del self.entry_prices[symbol]
                if symbol in self.entry_times: del self.entry_times[symbol]
                self.positions_count = max(0, self.positions_count - 1)

    def on_end_of_algorithm(self):
        self.log(f"Volume Exhaustion: ${self.portfolio.total_portfolio_value:,.2f}")
