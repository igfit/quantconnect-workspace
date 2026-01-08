from AlgorithmImports import *

class IndicatorEMACrossover(QCAlgorithm):
    """
    INDICATOR SIGNAL Strategy 2: EMA Crossover

    SIGNAL: Buy when EMA(10) crosses above EMA(50), Sell when crosses below
    BASKET: Fixed high-quality stocks

    Classic trend-following signal applied to each stock independently.
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
        self.ema10_ind = {}
        self.ema50_ind = {}
        self.prev_ema10 = {}
        self.prev_ema50 = {}
        self.in_position = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.ema10_ind[ticker] = self.ema(symbol, 10, Resolution.DAILY)
            self.ema50_ind[ticker] = self.ema(symbol, 50, Resolution.DAILY)
            self.prev_ema10[ticker] = None
            self.prev_ema50[ticker] = None
            self.in_position[ticker] = False

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(60, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up:
            return

        for ticker in self.basket:
            symbol = self.symbols[ticker]

            if symbol not in data.bars:
                continue

            if not self.ema10_ind[ticker].is_ready or not self.ema50_ind[ticker].is_ready:
                continue

            ema10 = self.ema10_ind[ticker].current.value
            ema50 = self.ema50_ind[ticker].current.value

            # Need previous values to detect crossover
            if self.prev_ema10[ticker] is None:
                self.prev_ema10[ticker] = ema10
                self.prev_ema50[ticker] = ema50
                continue

            # Detect crossovers
            bullish_cross = self.prev_ema10[ticker] <= self.prev_ema50[ticker] and ema10 > ema50
            bearish_cross = self.prev_ema10[ticker] >= self.prev_ema50[ticker] and ema10 < ema50

            # BUY SIGNAL: Bullish crossover
            if bullish_cross and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: EMA10={ema10:.2f} crossed above EMA50={ema50:.2f}")

            # SELL SIGNAL: Bearish crossover
            elif bearish_cross and self.in_position[ticker]:
                self.liquidate(symbol)
                self.in_position[ticker] = False
                self.debug(f"SELL {ticker}: EMA10={ema10:.2f} crossed below EMA50={ema50:.2f}")

            # Update previous values
            self.prev_ema10[ticker] = ema10
            self.prev_ema50[ticker] = ema50
