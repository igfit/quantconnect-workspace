from AlgorithmImports import *

class BBReversalVolatile(QCAlgorithm):
    """
    Bollinger Band Mean Reversion on Volatile Stocks

    CONCEPT:
    - Buy when price touches lower BB (oversold)
    - Confirm with RSI < 35 (truly oversold)
    - Sell at middle BB or upper BB
    - Works best on volatile, mean-reverting stocks
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
        self.bb_ind = {}
        self.rsi_ind = {}
        self.in_position = {}
        self.entry_price = {}

        for ticker in self.basket:
            try:
                symbol = self.add_equity(ticker, Resolution.DAILY).symbol
                self.symbols[ticker] = symbol
                self.bb_ind[ticker] = self.BB(symbol, 20, 2, MovingAverageType.SIMPLE, Resolution.DAILY)
                self.rsi_ind[ticker] = self.rsi(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
                self.in_position[ticker] = False
                self.entry_price[ticker] = 0
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

            if ticker not in self.bb_ind or not self.bb_ind[ticker].is_ready:
                continue
            if not self.rsi_ind[ticker].is_ready:
                continue

            price = data.bars[symbol].close
            lower_bb = self.bb_ind[ticker].lower_band.current.value
            middle_bb = self.bb_ind[ticker].middle_band.current.value
            upper_bb = self.bb_ind[ticker].upper_band.current.value
            rsi = self.rsi_ind[ticker].current.value

            # BUY: Price at/below lower BB + RSI oversold
            if price <= lower_bb and rsi < 35 and not self.in_position[ticker]:
                if position_count < self.max_positions:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.in_position[ticker] = True
                    self.entry_price[ticker] = price
                    position_count += 1

            # SELL: Price at middle BB (target) or upper BB (extended)
            elif self.in_position[ticker]:
                # Take profit at middle BB or if RSI overbought
                if price >= middle_bb or rsi > 70:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    position_count -= 1
                # Stop loss: 10% below entry
                elif price < self.entry_price[ticker] * 0.90:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    position_count -= 1
