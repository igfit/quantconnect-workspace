from AlgorithmImports import *

class DualMomentumStrategy(QCAlgorithm):
    """
    Dual Momentum Strategy - Combines absolute and relative momentum

    Logic:
    - Absolute Momentum: Stock's return over lookback > 0
    - Relative Momentum: Stock's return > SPY's return over lookback
    - Entry: Both conditions true
    - Exit: Either condition fails

    Parameters:
    - lookback_period: 63 days (~3 months)
    - rebalance_frequency: Weekly (to avoid whipsaws)

    Based on Gary Antonacci's Dual Momentum research.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        # Parameters
        self.lookback_period = 63  # ~3 months of trading days

        # Add equities
        self.symbol = self.add_equity("TSLA", Resolution.DAILY).symbol
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # Rolling windows for returns calculation
        self.symbol_prices = RollingWindow[float](self.lookback_period + 1)
        self.spy_prices = RollingWindow[float](self.lookback_period + 1)

        # Weekly rebalancing to avoid daily whipsaws
        self.last_rebalance = self.time
        self.rebalance_days = 5  # Weekly

        # Track position state
        self.in_position = False

        # Warmup
        self.set_warm_up(self.lookback_period + 10)

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Update price windows
        if data.bars.contains_key(self.symbol):
            self.symbol_prices.add(data.bars[self.symbol].close)
        if data.bars.contains_key(self.spy):
            self.spy_prices.add(data.bars[self.spy].close)

        # Check if windows are ready
        if not self.symbol_prices.is_ready or not self.spy_prices.is_ready:
            return

        # Only rebalance weekly (unless exiting on stop)
        days_since_rebalance = (self.time - self.last_rebalance).days
        if days_since_rebalance < self.rebalance_days:
            return

        self.last_rebalance = self.time

        # Calculate returns over lookback period
        symbol_return = self.calculate_return(self.symbol_prices)
        spy_return = self.calculate_return(self.spy_prices)

        # Dual momentum conditions
        absolute_momentum = symbol_return > 0
        relative_momentum = symbol_return > spy_return

        current_price = self.symbol_prices[0]

        if not self.portfolio[self.symbol].invested:
            # Entry: Both momentum conditions must be true
            if absolute_momentum and relative_momentum:
                self.set_holdings(self.symbol, 1.0)
                self.in_position = True
                self.debug(f"ENTRY: Price={current_price:.2f}, StockRet={symbol_return*100:.1f}%, SPYRet={spy_return*100:.1f}%")
        else:
            # Exit: Either momentum condition fails
            exit_signal = False
            exit_reason = ""

            if not absolute_momentum:
                exit_signal = True
                exit_reason = "Absolute Mom Fail"
            elif not relative_momentum:
                exit_signal = True
                exit_reason = "Relative Mom Fail"

            if exit_signal:
                self.liquidate(self.symbol, exit_reason)
                self.in_position = False
                self.debug(f"EXIT ({exit_reason}): Price={current_price:.2f}, StockRet={symbol_return*100:.1f}%, SPYRet={spy_return*100:.1f}%")

    def calculate_return(self, window):
        """Calculate return over the lookback period"""
        if not window.is_ready:
            return 0
        current = window[0]
        past = window[self.lookback_period]
        if past == 0:
            return 0
        return (current - past) / past
