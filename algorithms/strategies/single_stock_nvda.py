from AlgorithmImports import *

class SingleStockNVDA(QCAlgorithm):
    """
    Single Stock NVDA with Momentum Filter

    Test: What returns could we get with NVDA alone using momentum timing?
    This establishes an upper bound for what's achievable.

    Signal: 3-month return > 0, Price > 50 SMA
    Position: 100% NVDA when signal active, cash otherwise
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Parameters
        self.lookback = 63  # 3 months
        self.sma_period = 50

        # Add NVDA
        self.nvda = self.add_equity("NVDA", Resolution.DAILY).symbol
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # Price windows
        self.nvda_prices = RollingWindow[float](self.lookback + 10)
        self.spy_prices = RollingWindow[float](self.lookback + 10)

        # SMA
        self.nvda_sma = self.sma(self.nvda, self.sma_period, Resolution.DAILY)

        # Warmup
        self.set_warm_up(self.lookback + 20)

        # Weekly check
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open(self.nvda, 30),
            self.check_signal
        )

    def on_data(self, data):
        if self.is_warming_up:
            return

        if data.bars.contains_key(self.nvda):
            self.nvda_prices.add(data.bars[self.nvda].close)
        if data.bars.contains_key(self.spy):
            self.spy_prices.add(data.bars[self.spy].close)

    def calculate_return(self, window):
        if not window.is_ready or window.count < self.lookback + 1:
            return None
        return (window[0] - window[self.lookback]) / window[self.lookback]

    def check_signal(self):
        if self.is_warming_up:
            return

        if not self.nvda_prices.is_ready or not self.nvda_sma.is_ready:
            return

        current_price = self.nvda_prices[0]
        nvda_return = self.calculate_return(self.nvda_prices)
        spy_return = self.calculate_return(self.spy_prices)

        if nvda_return is None or spy_return is None:
            return

        # Conditions: positive momentum, above SMA, beating SPY
        abs_momentum = nvda_return > 0
        trend_ok = current_price > self.nvda_sma.current.value
        rel_momentum = nvda_return > spy_return

        should_hold = abs_momentum and trend_ok

        if should_hold and not self.portfolio[self.nvda].invested:
            self.set_holdings(self.nvda, 1.0)
            self.debug(f"ENTER NVDA: Return={nvda_return*100:.1f}%, Price={current_price:.2f}")
        elif not should_hold and self.portfolio[self.nvda].invested:
            self.liquidate(self.nvda)
            self.debug(f"EXIT NVDA: Return={nvda_return*100:.1f}%, Price={current_price:.2f}")
