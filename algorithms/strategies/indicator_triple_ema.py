from AlgorithmImports import *

class IndicatorTripleEMA(QCAlgorithm):
    """
    Triple EMA Strategy (Fast Momentum)

    CONCEPT:
    - Use 3 EMAs: Fast (8), Medium (21), Slow (55)
    - Buy when Fast > Medium > Slow (stacked bullish)
    - Sell when Fast < Medium (momentum lost)

    WHY THIS MIGHT WORK:
    - Catches trends earlier than 10/50 cross
    - Multiple confirmation reduces false signals
    - Common professional setup (8/21/55 Fibonacci EMAs)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # 25-stock basket
        self.basket = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA",
            "AVGO", "AMD", "NFLX", "CRM", "NOW", "ADBE", "ORCL",
            "V", "MA", "JPM", "GS",
            "LLY", "UNH", "ABBV",
            "COST", "HD", "CAT", "GE", "HON"
        ]

        self.weight_per_stock = 0.04

        self.symbols = {}
        self.ema8_ind = {}
        self.ema21_ind = {}
        self.ema55_ind = {}
        self.in_position = {}
        self.prev_stacked = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.ema8_ind[ticker] = self.ema(symbol, 8, Resolution.DAILY)
            self.ema21_ind[ticker] = self.ema(symbol, 21, Resolution.DAILY)
            self.ema55_ind[ticker] = self.ema(symbol, 55, Resolution.DAILY)
            self.in_position[ticker] = False
            self.prev_stacked[ticker] = False

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

            if not all([self.ema8_ind[ticker].is_ready,
                       self.ema21_ind[ticker].is_ready,
                       self.ema55_ind[ticker].is_ready]):
                continue

            ema8 = self.ema8_ind[ticker].current.value
            ema21 = self.ema21_ind[ticker].current.value
            ema55 = self.ema55_ind[ticker].current.value

            # Check EMA stacking
            bullish_stack = ema8 > ema21 > ema55
            fast_below_medium = ema8 < ema21

            # BUY: EMAs just became stacked bullish
            if bullish_stack and not self.prev_stacked[ticker] and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: Triple EMA stacked bullish")

            # SELL: Fast EMA crossed below Medium
            elif fast_below_medium and self.in_position[ticker]:
                self.liquidate(symbol)
                self.in_position[ticker] = False
                self.debug(f"SELL {ticker}: EMA8 < EMA21")

            self.prev_stacked[ticker] = bullish_stack
