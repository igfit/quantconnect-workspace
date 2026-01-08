from AlgorithmImports import *

class IndicatorEMAFaster(QCAlgorithm):
    """
    Faster EMA Crossover Strategy (5/21)

    CONCEPT:
    - Use 5-day and 21-day EMAs instead of 10/50
    - Faster to capture momentum
    - RSI filter still applies (< 70)

    WHY THIS MIGHT WORK:
    - Catches trends earlier
    - More trades but captures more of the move
    - 5/21 is popular among active traders
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
        self.ema5_ind = {}
        self.ema21_ind = {}
        self.rsi_ind = {}
        self.prev_ema5 = {}
        self.prev_ema21 = {}
        self.in_position = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.ema5_ind[ticker] = self.ema(symbol, 5, Resolution.DAILY)
            self.ema21_ind[ticker] = self.ema(symbol, 21, Resolution.DAILY)
            self.rsi_ind[ticker] = self.rsi(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
            self.prev_ema5[ticker] = None
            self.prev_ema21[ticker] = None
            self.in_position[ticker] = False

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(30, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up:
            return

        for ticker in self.basket:
            symbol = self.symbols[ticker]

            if symbol not in data.bars:
                continue

            if not all([self.ema5_ind[ticker].is_ready,
                       self.ema21_ind[ticker].is_ready,
                       self.rsi_ind[ticker].is_ready]):
                continue

            ema5 = self.ema5_ind[ticker].current.value
            ema21 = self.ema21_ind[ticker].current.value
            rsi = self.rsi_ind[ticker].current.value

            if self.prev_ema5[ticker] is None:
                self.prev_ema5[ticker] = ema5
                self.prev_ema21[ticker] = ema21
                continue

            # Crossover detection
            bullish_cross = self.prev_ema5[ticker] <= self.prev_ema21[ticker] and ema5 > ema21
            bearish_cross = self.prev_ema5[ticker] >= self.prev_ema21[ticker] and ema5 < ema21

            # BUY: EMA cross + RSI not overbought
            if bullish_cross and rsi < 70 and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: Fast EMA cross + RSI={rsi:.1f}")

            # SELL: Bearish EMA cross
            elif bearish_cross and self.in_position[ticker]:
                self.liquidate(symbol)
                self.in_position[ticker] = False

            self.prev_ema5[ticker] = ema5
            self.prev_ema21[ticker] = ema21
