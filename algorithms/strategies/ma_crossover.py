from AlgorithmImports import *


class MACrossoverStrategy(QCAlgorithm):
    """
    Simple Moving Average Crossover Strategy

    Strategy:
        - Go long when fast SMA crosses above slow SMA
        - Exit when fast SMA crosses below slow SMA
        - Trade a basket of liquid US equities

    Parameters:
        - fast_period: Fast SMA period (default: 50 days)
        - slow_period: Slow SMA period (default: 200 days)
        - symbols: List of equity symbols to trade

    Universe: Selected US large-cap equities
    Rebalance: On crossover signals
    """

    def initialize(self):
        # Backtest period
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        # Strategy parameters
        self.fast_period = 50
        self.slow_period = 200

        # Symbols to trade
        self.tickers = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL"]

        # Store indicators for each symbol
        self.fast_sma = {}
        self.slow_sma = {}
        self.previous_signal = {}

        # Add equities and create indicators
        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol

            # Create SMA indicators
            self.fast_sma[symbol] = self.sma(symbol, self.fast_period, Resolution.DAILY)
            self.slow_sma[symbol] = self.sma(symbol, self.slow_period, Resolution.DAILY)

            # Initialize signal state (None = no position yet)
            self.previous_signal[symbol] = None

            # Warm up indicators with historical data
            self.set_warm_up(self.slow_period, Resolution.DAILY)

        # Set SPY as benchmark for performance comparison
        self.set_benchmark("SPY")

    def on_data(self, data):
        """Check for crossover signals on each bar"""
        # Skip during warm-up
        if self.is_warming_up:
            return

        for symbol in self.fast_sma.keys():
            # Skip if no data for this symbol
            if symbol not in data or data[symbol] is None:
                continue

            # Skip if indicators not ready
            if not self.fast_sma[symbol].is_ready or not self.slow_sma[symbol].is_ready:
                continue

            fast = self.fast_sma[symbol].current.value
            slow = self.slow_sma[symbol].current.value

            # Determine current signal
            current_signal = fast > slow

            # Check for crossover
            if self.previous_signal[symbol] is not None:
                # Bullish crossover: go long
                if current_signal and not self.previous_signal[symbol]:
                    self.set_holdings(symbol, 1.0 / len(self.tickers))
                    self.debug(f"{self.time}: BUY {symbol} - Fast SMA ({fast:.2f}) crossed above Slow SMA ({slow:.2f})")

                # Bearish crossover: exit position
                elif not current_signal and self.previous_signal[symbol]:
                    self.liquidate(symbol)
                    self.debug(f"{self.time}: SELL {symbol} - Fast SMA ({fast:.2f}) crossed below Slow SMA ({slow:.2f})")

            # Update previous signal
            self.previous_signal[symbol] = current_signal

    def on_end_of_algorithm(self):
        """Log final portfolio value"""
        self.log(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
