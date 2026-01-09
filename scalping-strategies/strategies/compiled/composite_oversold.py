"""
Composite Oversold Indicator Strategy

FIRST PRINCIPLES:
- Single indicators give false signals; confluence is more reliable
- When MULTIPLE indicators agree on oversold, probability of bounce increases
- Weight indicators by their information content (don't double-count similar signals)

Custom Composite Indicator:
  Score = 0 to 100 (higher = more oversold)

  Components (weighted by independence):
  - RSI(5) < 30:      +30 points (momentum)
  - Stochastic < 20:  +25 points (relative position)
  - BB %B < 0:        +25 points (volatility-adjusted)
  - Price < 20 SMA:   +20 points (trend deviation)

Entry: Composite Score >= 75 (3+ indicators agreeing)
Exit: Composite Score <= 25 OR profit target 3%
"""

from AlgorithmImports import *


class CompositeOversold(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Composite indicator thresholds
        self.rsi_oversold = 30
        self.stoch_oversold = 20
        self.entry_score = 75  # Need 75+ score to enter
        self.exit_score = 25
        self.profit_target = 0.03  # 3% profit target

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
                "rsi": self.rsi(symbol, 5, MovingAverageType.WILDERS, Resolution.DAILY),
                "stoch": self.sto(symbol, 14, 3, 3, Resolution.DAILY),
                "bb": self.bb(symbol, 20, 2.0, MovingAverageType.SIMPLE, Resolution.DAILY),
                "sma20": self.sma(symbol, 20, Resolution.DAILY),
            }
            equity.set_slippage_model(ConstantSlippageModel(0.001))
            equity.set_fee_model(InteractiveBrokersFeeModel())

        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)
        self.set_warm_up(220, Resolution.DAILY)
        self.set_benchmark("SPY")

        self.schedule.on(self.date_rules.every_day(), self.time_rules.before_market_close("SPY", 5), self.check_time_stops)

    def calculate_composite_score(self, symbol, data):
        """Calculate composite oversold score (0-100)"""
        score = 0
        ind = self.indicators[symbol]

        if not all([ind["rsi"].is_ready, ind["stoch"].is_ready, ind["bb"].is_ready, ind["sma20"].is_ready]):
            return 0

        price = data[symbol].close

        # RSI component (30 points)
        rsi = ind["rsi"].current.value
        if rsi < self.rsi_oversold:
            score += 30

        # Stochastic component (25 points)
        stoch_k = ind["stoch"].stoch_k.current.value
        if stoch_k < self.stoch_oversold:
            score += 25

        # Bollinger Band %B component (25 points)
        bb = ind["bb"]
        bb_lower = bb.lower_band.current.value
        bb_upper = bb.upper_band.current.value
        bb_range = bb_upper - bb_lower
        if bb_range > 0:
            percent_b = (price - bb_lower) / bb_range
            if percent_b < 0:  # Below lower band
                score += 25

        # Price vs 20 SMA component (20 points)
        sma20 = ind["sma20"].current.value
        if price < sma20:
            score += 20

        return score

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

            price = data[symbol].close
            score = self.calculate_composite_score(symbol, data)

            if self.portfolio[symbol].invested:
                # Exit on low score OR profit target
                pnl_pct = (price - self.entry_prices.get(symbol, price)) / self.entry_prices.get(symbol, price) if symbol in self.entry_prices else 0

                if score <= self.exit_score or pnl_pct >= self.profit_target:
                    self.liquidate(symbol)
                    if symbol in self.entry_prices: del self.entry_prices[symbol]
                    if symbol in self.entry_times: del self.entry_times[symbol]
                    self.positions_count = max(0, self.positions_count - 1)
                # Stop loss
                elif pnl_pct < -self.stop_loss_pct:
                    self.liquidate(symbol)
                    if symbol in self.entry_prices: del self.entry_prices[symbol]
                    if symbol in self.entry_times: del self.entry_times[symbol]
                    self.positions_count = max(0, self.positions_count - 1)

            elif self.positions_count < self.max_positions:
                # Entry: High composite score
                if score >= self.entry_score:
                    shares = int(self.position_size_dollars / price)
                    if shares > 0:
                        self.market_order(symbol, shares)
                        self.entry_prices[symbol] = price
                        self.entry_times[symbol] = self.time
                        self.positions_count += 1
                        self.debug(f"{self.time.date()}: ENTRY {symbol} - Composite Score={score}")

    def check_time_stops(self):
        for symbol in list(self.entry_times.keys()):
            if (self.time - self.entry_times[symbol]).days >= self.max_holding_days:
                self.liquidate(symbol)
                if symbol in self.entry_prices: del self.entry_prices[symbol]
                if symbol in self.entry_times: del self.entry_times[symbol]
                self.positions_count = max(0, self.positions_count - 1)

    def on_end_of_algorithm(self):
        self.log(f"Composite Oversold: ${self.portfolio.total_portfolio_value:,.2f}")
