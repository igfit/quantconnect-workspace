"""
Keltner Channel Mean Reversion Strategy

FIRST PRINCIPLES:
- Keltner Channels use ATR (volatility-based) instead of std dev
- More adaptive to changing volatility than Bollinger Bands
- Touch of outer channel = extreme move, likely to revert to middle

Theory: Keltner Channels self-adjust to volatility.
When price touches the lower channel AND momentum is oversold,
we have a high-probability mean reversion setup to the middle channel.

Entry:
  - SPY > 200 SMA (bull market)
  - Price <= Lower Keltner Channel
  - RSI(5) < 35 (confirming oversold)

Exit:
  - Price >= Middle Channel (EMA 20)
  - OR RSI > 55
  - OR 5 day time stop
  - OR 5% stop loss
"""

from AlgorithmImports import *


class KeltnerReversion(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.keltner_period = 20
        self.keltner_mult = 2.0
        self.atr_period = 14
        self.rsi_period = 5
        self.rsi_entry = 35
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

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols.append(symbol)
            self.indicators[symbol] = {
                "kc": KeltnerChannels(self.keltner_period, self.keltner_mult, MovingAverageType.EXPONENTIAL),
                "rsi": self.rsi(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY),
            }
            self.register_indicator(symbol, self.indicators[symbol]["kc"], Resolution.DAILY)
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
            if not ind["kc"].is_ready or not ind["rsi"].is_ready:
                continue

            price = data[symbol].close
            kc = ind["kc"]
            rsi = ind["rsi"].current.value

            lower_channel = kc.lower_band.current.value
            middle_channel = kc.middle_band.current.value

            if self.portfolio[symbol].invested:
                # Exit at middle channel or RSI recovery
                if price >= middle_channel or rsi > self.rsi_exit:
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
                # Entry: Price at lower Keltner + RSI oversold
                if price <= lower_channel and rsi < self.rsi_entry:
                    shares = int(self.position_size_dollars / price)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.entry_times[symbol] = self.time
                        self.positions_count += 1
                        self.debug(f"{self.time.date()}: ENTRY {symbol} - KC Lower, RSI={rsi:.1f}")

    def check_time_stops(self):
        for symbol in list(self.entry_times.keys()):
            if (self.time - self.entry_times[symbol]).days >= self.max_holding_days:
                self.liquidate(symbol)
                if symbol in self.entry_prices: del self.entry_prices[symbol]
                if symbol in self.entry_times: del self.entry_times[symbol]
                self.positions_count = max(0, self.positions_count - 1)

    def on_end_of_algorithm(self):
        self.log(f"Keltner Reversion: ${self.portfolio.total_portfolio_value:,.2f}")
