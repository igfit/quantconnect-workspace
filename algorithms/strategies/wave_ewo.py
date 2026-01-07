from AlgorithmImports import *
import numpy as np


class WaveEWO(QCAlgorithm):
    """
    Wave Elliott Wave Oscillator - EWO-inspired momentum indicator

    Based on the Elliott Wave Oscillator (5/34 SMA difference)
    with RSI momentum filter for confirmation.

    Formula: EWO = SMA(5) - SMA(34)

    Key characteristics:
    - Positive EWO = bullish wave (uptrend)
    - Negative EWO = bearish wave (downtrend)
    - Highest/lowest readings indicate Wave 3 (strongest momentum)
    - Divergence at extremes signals Wave 5 (trend exhaustion)

    Entry: EWO crosses above 0 with RSI > 40 (momentum confirmation)
    Exit: EWO crosses below 0 OR RSI drops below 30 (momentum failing)

    Hypothesis: Simpler than BX (uses SMA instead of EMA+RSI),
                captures similar trend dynamics with less lag
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.ticker = "TSLA"
        self.symbol = self.add_equity(self.ticker, Resolution.DAILY).symbol

        # EWO params (standard)
        self.fast_period = 5
        self.slow_period = 34

        # RSI filter
        self.rsi_period = 14
        self.rsi_entry_threshold = 40  # Don't enter if RSI < 40
        self.rsi_exit_threshold = 30   # Force exit if RSI < 30

        # Indicators
        self.sma_fast = self.sma(self.symbol, self.fast_period, Resolution.DAILY)
        self.sma_slow = self.sma(self.symbol, self.slow_period, Resolution.DAILY)
        self.rsi_indicator = self.rsi(self.symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY)

        # EWO tracking
        self.ewo = None
        self.prev_ewo = None
        self.ewo_window = RollingWindow[float](50)  # Track for divergence

        self.set_warm_up(50, Resolution.DAILY)
        self.set_benchmark("SPY")

    def on_data(self, data):
        if self.is_warming_up or self.symbol not in data:
            return
        if data[self.symbol] is None:
            return
        if not self.sma_fast.is_ready or not self.sma_slow.is_ready or not self.rsi_indicator.is_ready:
            return

        # Calculate EWO
        self.ewo = self.sma_fast.current.value - self.sma_slow.current.value
        self.ewo_window.add(self.ewo)

        rsi_val = self.rsi_indicator.current.value

        if self.prev_ewo is not None:
            # Zero-cross signals
            crossed_bullish = self.prev_ewo < 0 and self.ewo >= 0
            crossed_bearish = self.prev_ewo >= 0 and self.ewo < 0

            # Entry: EWO crosses bullish AND RSI confirms
            if crossed_bullish and rsi_val >= self.rsi_entry_threshold:
                if not self.portfolio[self.symbol].invested:
                    self.set_holdings(self.symbol, 1.0)
                    self.debug(f"{self.time}: BUY {self.ticker} - EWO: {self.ewo:.2f}, RSI: {rsi_val:.1f}")

            # Exit: EWO crosses bearish OR RSI fails
            elif self.portfolio[self.symbol].invested:
                if crossed_bearish:
                    self.liquidate(self.symbol)
                    self.debug(f"{self.time}: SELL {self.ticker} [EWO CROSS] - EWO: {self.ewo:.2f}, RSI: {rsi_val:.1f}")
                elif rsi_val < self.rsi_exit_threshold:
                    self.liquidate(self.symbol)
                    self.debug(f"{self.time}: SELL {self.ticker} [RSI FAIL] - EWO: {self.ewo:.2f}, RSI: {rsi_val:.1f}")

        self.prev_ewo = self.ewo

    def on_end_of_algorithm(self):
        self.log(f"Wave-EWO Final: ${self.portfolio.total_portfolio_value:,.2f}")
