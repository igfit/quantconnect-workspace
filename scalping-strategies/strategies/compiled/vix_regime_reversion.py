"""
VIX-Based Regime Mean Reversion Strategy

FIRST PRINCIPLES:
- VIX measures market fear/volatility expectations
- Low VIX (< 20) = complacent market, mean reversion works
- High VIX (> 25) = fear, momentum/crashes dominate

Theory: Mean reversion fails during high volatility periods because
fear drives momentum. In calm markets (low VIX), oversold bounces
are more reliable. VIX < 20 is historically "normal".

Entry:
  - SPY > 200 SMA (bull market)
  - VIX < 20 (low fear, stable market)
  - RSI(5) < 35 (oversold)

Exit:
  - RSI > 55 OR VIX > 25 (fear rising, abort)
  - 5 day time limit
  - 5% stop loss
"""

from AlgorithmImports import *


class VIXRegimeReversion(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.rsi_period = 5
        self.rsi_entry = 35
        self.rsi_exit = 55
        self.vix_low = 20   # Below = calm market
        self.vix_high = 25  # Above = fear, exit

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
            }
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        # Add VIX
        self.vix = self.add_index("VIX", Resolution.DAILY).symbol

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.set_warm_up(220, Resolution.DAILY)
        self.set_benchmark("SPY")

        self.schedule.on(self.date_rules.every_day(), self.time_rules.before_market_close("SPY", 5), self.check_time_stops)

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Get VIX value
        vix_value = None
        if self.vix in data and data[self.vix] is not None:
            vix_value = data[self.vix].close

        # Regime filter (SPY trend + VIX level)
        spy_bearish = self.spy not in data or data[self.spy] is None or not self.spy_sma.is_ready or data[self.spy].close <= self.spy_sma.current.value
        vix_high_fear = vix_value is None or vix_value > self.vix_high

        if spy_bearish:
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

            price = data[symbol].close
            rsi_value = rsi.current.value

            if self.portfolio[symbol].invested:
                # Exit: RSI recovery OR VIX spiking OR stop loss
                if rsi_value > self.rsi_exit or vix_high_fear:
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
                # Entry: Calm market (low VIX) + oversold
                if vix_value is not None and vix_value < self.vix_low and rsi_value < self.rsi_entry:
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
        self.log(f"VIX Regime Reversion: ${self.portfolio.total_portfolio_value:,.2f}")
