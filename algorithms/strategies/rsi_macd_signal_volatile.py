from AlgorithmImports import *

class RSIMACDSignalVolatile(QCAlgorithm):
    """
    RSI + MACD Combined Signal on Volatile Basket

    CONCEPT:
    - Buy when RSI crosses above 30 (oversold bounce) AND MACD histogram > 0
    - Sell when RSI > 70 (overbought) OR MACD histogram turns negative
    - Tests mean-reversion + momentum confirmation
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # 40-stock volatile basket
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
        self.rsi_ind = {}
        self.macd_ind = {}
        self.prev_rsi = {}
        self.in_position = {}

        for ticker in self.basket:
            try:
                symbol = self.add_equity(ticker, Resolution.DAILY).symbol
                self.symbols[ticker] = symbol
                self.rsi_ind[ticker] = self.rsi(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
                self.macd_ind[ticker] = self.macd(symbol, 12, 26, 9, MovingAverageType.EXPONENTIAL, Resolution.DAILY)
                self.prev_rsi[ticker] = 50
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

            if ticker not in self.rsi_ind or not self.rsi_ind[ticker].is_ready:
                continue
            if not self.macd_ind[ticker].is_ready:
                continue

            rsi = self.rsi_ind[ticker].current.value
            macd_hist = self.macd_ind[ticker].histogram.current.value

            # RSI crossover above 30 (bouncing from oversold)
            rsi_bounce = self.prev_rsi[ticker] <= 30 and rsi > 30

            # BUY: RSI bounce + MACD positive
            if rsi_bounce and macd_hist > 0 and not self.in_position[ticker]:
                if position_count < self.max_positions:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.in_position[ticker] = True
                    position_count += 1

            # SELL: Overbought OR MACD turns negative
            elif self.in_position[ticker]:
                if rsi > 70 or macd_hist < 0:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    position_count -= 1

            self.prev_rsi[ticker] = rsi
