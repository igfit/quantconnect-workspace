from AlgorithmImports import *

class EMASignalSectorETFs(QCAlgorithm):
    """
    EMA Crossover Signal on Sector ETFs

    CONCEPT:
    - Apply EMA(10/50) crossover to sector ETFs
    - Buy sector when EMA crosses bullish
    - Sell when EMA crosses bearish
    - Tests if EMA signal works without stock picking

    NO SINGLE-STOCK BIAS - pure sector rotation
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        self.sectors = [
            "XLK", "XLF", "XLV", "XLY", "XLP",
            "XLE", "XLI", "XLB", "XLU", "XLRE", "XLC",
        ]

        self.weight_per_sector = 1.0 / len(self.sectors)

        self.symbols = {}
        self.ema10_ind = {}
        self.ema50_ind = {}
        self.prev_ema10 = {}
        self.prev_ema50 = {}
        self.in_position = {}

        for ticker in self.sectors:
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

        for ticker in self.sectors:
            symbol = self.symbols[ticker]

            if symbol not in data.bars:
                continue

            if not self.ema10_ind[ticker].is_ready or not self.ema50_ind[ticker].is_ready:
                continue

            ema10 = self.ema10_ind[ticker].current.value
            ema50 = self.ema50_ind[ticker].current.value

            if self.prev_ema10[ticker] is None:
                self.prev_ema10[ticker] = ema10
                self.prev_ema50[ticker] = ema50
                continue

            bullish_cross = self.prev_ema10[ticker] <= self.prev_ema50[ticker] and ema10 > ema50
            bearish_cross = self.prev_ema10[ticker] >= self.prev_ema50[ticker] and ema10 < ema50

            if bullish_cross and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_sector)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: EMA cross")

            elif bearish_cross and self.in_position[ticker]:
                self.liquidate(symbol)
                self.in_position[ticker] = False
                self.debug(f"SELL {ticker}: EMA cross")

            self.prev_ema10[ticker] = ema10
            self.prev_ema50[ticker] = ema50
