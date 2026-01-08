from AlgorithmImports import *

class IndicatorMACDSignal(QCAlgorithm):
    """
    INDICATOR SIGNAL Strategy 3: MACD Signal Line Crossover

    SIGNAL: Buy when MACD crosses above signal line, Sell when crosses below
    BASKET: Fixed high-quality stocks

    MACD(12,26,9) is a momentum indicator that shows trend direction and strength.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Fixed basket
        self.basket = [
            "NVDA", "META", "GOOGL", "AMZN", "MSFT",
            "AVGO", "AMD", "NFLX", "CRM", "NOW"
        ]

        self.weight_per_stock = 0.10

        self.symbols = {}
        self.macd_ind = {}
        self.prev_macd = {}
        self.prev_signal = {}
        self.in_position = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.macd_ind[ticker] = self.MACD(symbol, 12, 26, 9, MovingAverageType.EXPONENTIAL, Resolution.DAILY)
            self.prev_macd[ticker] = None
            self.prev_signal[ticker] = None
            self.in_position[ticker] = False

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(35, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up:
            return

        for ticker in self.basket:
            symbol = self.symbols[ticker]

            if symbol not in data.bars:
                continue

            if not self.macd_ind[ticker].is_ready:
                continue

            macd_value = self.macd_ind[ticker].current.value
            signal_value = self.macd_ind[ticker].signal.current.value

            # Need previous values for crossover detection
            if self.prev_macd[ticker] is None:
                self.prev_macd[ticker] = macd_value
                self.prev_signal[ticker] = signal_value
                continue

            # Detect crossovers
            bullish_cross = self.prev_macd[ticker] <= self.prev_signal[ticker] and macd_value > signal_value
            bearish_cross = self.prev_macd[ticker] >= self.prev_signal[ticker] and macd_value < signal_value

            # BUY SIGNAL: MACD crosses above signal line
            if bullish_cross and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: MACD={macd_value:.2f} > Signal={signal_value:.2f}")

            # SELL SIGNAL: MACD crosses below signal line
            elif bearish_cross and self.in_position[ticker]:
                self.liquidate(symbol)
                self.in_position[ticker] = False
                self.debug(f"SELL {ticker}: MACD={macd_value:.2f} < Signal={signal_value:.2f}")

            # Update previous values
            self.prev_macd[ticker] = macd_value
            self.prev_signal[ticker] = signal_value
