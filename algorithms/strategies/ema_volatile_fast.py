from AlgorithmImports import *

class EMAVolatileFast(QCAlgorithm):
    """
    Faster EMA (5/20) on Volatile Basket

    Hypothesis: Faster EMAs catch momentum earlier on volatile stocks
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        self.basket = [
            "AMD", "MU", "QCOM", "INTC", "AMAT", "LRCX", "KLAC", "MRVL",
            "ZM", "DOCU", "SNOW", "CRWD", "NET", "DDOG", "OKTA", "TWLO",
            "TSLA", "NIO", "RIVN", "LCID", "DASH", "ABNB", "UBER", "LYFT",
            "COIN", "HOOD", "SQ", "PYPL", "AFRM", "UPST",
            "MRNA", "BNTX", "REGN", "VRTX",
            "FSLR", "ENPH", "XOM", "OXY",
        ]

        self.max_positions = 15
        self.weight_per_stock = 0.067

        self.symbols = {}
        self.ema5_ind = {}
        self.ema20_ind = {}
        self.rsi_ind = {}
        self.prev_ema5 = {}
        self.prev_ema20 = {}
        self.in_position = {}

        for ticker in self.basket:
            try:
                symbol = self.add_equity(ticker, Resolution.DAILY).symbol
                self.symbols[ticker] = symbol
                self.ema5_ind[ticker] = self.ema(symbol, 5, Resolution.DAILY)
                self.ema20_ind[ticker] = self.ema(symbol, 20, Resolution.DAILY)
                self.rsi_ind[ticker] = self.rsi(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
                self.prev_ema5[ticker] = None
                self.prev_ema20[ticker] = None
                self.in_position[ticker] = False
            except:
                pass

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(30, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up:
            return

        position_count = sum(1 for t in self.in_position.values() if t)

        for ticker in list(self.symbols.keys()):
            symbol = self.symbols[ticker]
            if symbol not in data.bars:
                continue
            if ticker not in self.ema5_ind or not self.ema5_ind[ticker].is_ready:
                continue
            if not self.ema20_ind[ticker].is_ready or not self.rsi_ind[ticker].is_ready:
                continue

            ema5 = self.ema5_ind[ticker].current.value
            ema20 = self.ema20_ind[ticker].current.value
            rsi = self.rsi_ind[ticker].current.value

            if self.prev_ema5[ticker] is None:
                self.prev_ema5[ticker] = ema5
                self.prev_ema20[ticker] = ema20
                continue

            bullish_cross = self.prev_ema5[ticker] <= self.prev_ema20[ticker] and ema5 > ema20
            bearish_cross = self.prev_ema5[ticker] >= self.prev_ema20[ticker] and ema5 < ema20

            if bullish_cross and rsi < 70 and not self.in_position[ticker]:
                if position_count < self.max_positions:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.in_position[ticker] = True
                    position_count += 1

            elif bearish_cross and self.in_position[ticker]:
                self.liquidate(symbol)
                self.in_position[ticker] = False
                position_count -= 1

            self.prev_ema5[ticker] = ema5
            self.prev_ema20[ticker] = ema20
