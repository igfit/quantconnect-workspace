from AlgorithmImports import *

class EMAVolatileMomentumFilter(QCAlgorithm):
    """
    EMA Crossover + Momentum Filter

    Only take EMA signals on stocks with positive 1-month momentum
    This filters out weak/declining stocks
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
        self.ema10_ind = {}
        self.ema50_ind = {}
        self.rsi_ind = {}
        self.roc_ind = {}  # 1-month momentum
        self.prev_ema10 = {}
        self.prev_ema50 = {}
        self.in_position = {}

        for ticker in self.basket:
            try:
                symbol = self.add_equity(ticker, Resolution.DAILY).symbol
                self.symbols[ticker] = symbol
                self.ema10_ind[ticker] = self.ema(symbol, 10, Resolution.DAILY)
                self.ema50_ind[ticker] = self.ema(symbol, 50, Resolution.DAILY)
                self.rsi_ind[ticker] = self.rsi(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
                self.roc_ind[ticker] = self.rocp(symbol, 21, Resolution.DAILY)  # 1 month
                self.prev_ema10[ticker] = None
                self.prev_ema50[ticker] = None
                self.in_position[ticker] = False
            except:
                pass

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(60, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up:
            return

        position_count = sum(1 for t in self.in_position.values() if t)

        for ticker in list(self.symbols.keys()):
            symbol = self.symbols[ticker]
            if symbol not in data.bars:
                continue
            if ticker not in self.ema10_ind or not self.ema10_ind[ticker].is_ready:
                continue
            if not all([self.ema50_ind[ticker].is_ready, self.rsi_ind[ticker].is_ready,
                       self.roc_ind[ticker].is_ready]):
                continue

            ema10 = self.ema10_ind[ticker].current.value
            ema50 = self.ema50_ind[ticker].current.value
            rsi = self.rsi_ind[ticker].current.value
            momentum = self.roc_ind[ticker].current.value

            if self.prev_ema10[ticker] is None:
                self.prev_ema10[ticker] = ema10
                self.prev_ema50[ticker] = ema50
                continue

            bullish_cross = self.prev_ema10[ticker] <= self.prev_ema50[ticker] and ema10 > ema50
            bearish_cross = self.prev_ema10[ticker] >= self.prev_ema50[ticker] and ema10 < ema50

            # Entry: Bullish cross + RSI filter + Positive momentum
            if bullish_cross and rsi < 70 and momentum > 0 and not self.in_position[ticker]:
                if position_count < self.max_positions:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.in_position[ticker] = True
                    position_count += 1

            # Exit: Bearish cross OR momentum turns negative
            elif self.in_position[ticker]:
                if bearish_cross or momentum < -0.10:  # 10% decline
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    position_count -= 1

            self.prev_ema10[ticker] = ema10
            self.prev_ema50[ticker] = ema50
