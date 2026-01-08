from AlgorithmImports import *

class IndicatorEMACDConfirm(QCAlgorithm):
    """
    EMA Crossover + MACD Confirmation Strategy

    CONCEPT:
    - Base signal: EMA(10) crosses above EMA(50)
    - Confirmation: MACD histogram > 0 (momentum building)
    - Exit: EMA cross down OR MACD histogram turns negative

    WHY THIS MIGHT WORK:
    - MACD histogram confirms momentum direction
    - Reduces whipsaws from false EMA crosses
    - Two independent momentum measures must agree
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
        self.ema10_ind = {}
        self.ema50_ind = {}
        self.macd_ind = {}
        self.prev_ema10 = {}
        self.prev_ema50 = {}
        self.in_position = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.ema10_ind[ticker] = self.ema(symbol, 10, Resolution.DAILY)
            self.ema50_ind[ticker] = self.ema(symbol, 50, Resolution.DAILY)
            self.macd_ind[ticker] = self.macd(symbol, 12, 26, 9, MovingAverageType.EXPONENTIAL, Resolution.DAILY)
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

            if not all([self.ema10_ind[ticker].is_ready,
                       self.ema50_ind[ticker].is_ready,
                       self.macd_ind[ticker].is_ready]):
                continue

            ema10 = self.ema10_ind[ticker].current.value
            ema50 = self.ema50_ind[ticker].current.value
            macd_hist = self.macd_ind[ticker].histogram.current.value

            if self.prev_ema10[ticker] is None:
                self.prev_ema10[ticker] = ema10
                self.prev_ema50[ticker] = ema50
                continue

            # Crossover detection
            bullish_cross = self.prev_ema10[ticker] <= self.prev_ema50[ticker] and ema10 > ema50
            bearish_cross = self.prev_ema10[ticker] >= self.prev_ema50[ticker] and ema10 < ema50

            # BUY: EMA cross + MACD histogram positive
            if bullish_cross and macd_hist > 0 and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: EMA cross + MACD hist={macd_hist:.2f}")

            # SELL: Bearish EMA cross OR MACD histogram turns negative
            elif self.in_position[ticker]:
                if bearish_cross or macd_hist < 0:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    self.debug(f"SELL {ticker}: {'EMA cross' if bearish_cross else 'MACD negative'}")

            self.prev_ema10[ticker] = ema10
            self.prev_ema50[ticker] = ema50
