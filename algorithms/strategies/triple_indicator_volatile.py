from AlgorithmImports import *

class TripleIndicatorVolatile(QCAlgorithm):
    """
    Triple Indicator Confirmation (EMA + RSI + MACD)

    CONCEPT:
    - Buy only when ALL THREE indicators align:
      1. EMA(10) > EMA(50) (trend up)
      2. RSI between 40-70 (not oversold, not overbought)
      3. MACD histogram > 0 (momentum positive)
    - High conviction trades only
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
        self.macd_ind = {}
        self.in_position = {}
        self.was_aligned = {}

        for ticker in self.basket:
            try:
                symbol = self.add_equity(ticker, Resolution.DAILY).symbol
                self.symbols[ticker] = symbol
                self.ema10_ind[ticker] = self.ema(symbol, 10, Resolution.DAILY)
                self.ema50_ind[ticker] = self.ema(symbol, 50, Resolution.DAILY)
                self.rsi_ind[ticker] = self.rsi(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
                self.macd_ind[ticker] = self.macd(symbol, 12, 26, 9, MovingAverageType.EXPONENTIAL, Resolution.DAILY)
                self.in_position[ticker] = False
                self.was_aligned[ticker] = False
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

            if ticker not in self.ema10_ind:
                continue
            if not all([self.ema10_ind[ticker].is_ready, self.ema50_ind[ticker].is_ready,
                       self.rsi_ind[ticker].is_ready, self.macd_ind[ticker].is_ready]):
                continue

            ema10 = self.ema10_ind[ticker].current.value
            ema50 = self.ema50_ind[ticker].current.value
            rsi = self.rsi_ind[ticker].current.value
            macd_hist = self.macd_ind[ticker].histogram.current.value

            # Three conditions
            ema_bullish = ema10 > ema50
            rsi_ok = 40 <= rsi <= 70
            macd_positive = macd_hist > 0

            all_aligned = ema_bullish and rsi_ok and macd_positive

            # BUY: All three just aligned (wasn't aligned before)
            if all_aligned and not self.was_aligned[ticker] and not self.in_position[ticker]:
                if position_count < self.max_positions:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.in_position[ticker] = True
                    position_count += 1

            # SELL: Any condition fails
            elif self.in_position[ticker]:
                if not ema_bullish or rsi > 75 or macd_hist < -0.5:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    position_count -= 1

            self.was_aligned[ticker] = all_aligned
