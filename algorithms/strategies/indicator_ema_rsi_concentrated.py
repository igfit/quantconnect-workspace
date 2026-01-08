from AlgorithmImports import *

class IndicatorEMARSIConcentrated(QCAlgorithm):
    """
    EMA-RSI Strategy with Concentrated Bets

    CONCEPT:
    - Same EMA(10/50) + RSI<70 filter
    - BUT: Only hold max 10 positions at 10% each
    - Prioritize newest signals (freshest momentum)

    WHY THIS MIGHT WORK:
    - More conviction per trade
    - Less diversification drag
    - Captures bigger swings
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

        self.max_positions = 10
        self.weight_per_stock = 0.10

        self.symbols = {}
        self.ema10_ind = {}
        self.ema50_ind = {}
        self.rsi_ind = {}
        self.prev_ema10 = {}
        self.prev_ema50 = {}
        self.in_position = {}
        self.position_count = 0

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.ema10_ind[ticker] = self.ema(symbol, 10, Resolution.DAILY)
            self.ema50_ind[ticker] = self.ema(symbol, 50, Resolution.DAILY)
            self.rsi_ind[ticker] = self.rsi(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
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
                       self.rsi_ind[ticker].is_ready]):
                continue

            ema10 = self.ema10_ind[ticker].current.value
            ema50 = self.ema50_ind[ticker].current.value
            rsi = self.rsi_ind[ticker].current.value

            if self.prev_ema10[ticker] is None:
                self.prev_ema10[ticker] = ema10
                self.prev_ema50[ticker] = ema50
                continue

            # Crossover detection
            bullish_cross = self.prev_ema10[ticker] <= self.prev_ema50[ticker] and ema10 > ema50
            bearish_cross = self.prev_ema10[ticker] >= self.prev_ema50[ticker] and ema10 < ema50

            # BUY: EMA cross + RSI not overbought + room for position
            if bullish_cross and rsi < 70 and not self.in_position[ticker]:
                if self.position_count < self.max_positions:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.in_position[ticker] = True
                    self.position_count += 1
                    self.debug(f"BUY {ticker}: Position {self.position_count}/{self.max_positions}")

            # SELL: Bearish EMA cross
            elif bearish_cross and self.in_position[ticker]:
                self.liquidate(symbol)
                self.in_position[ticker] = False
                self.position_count -= 1
                self.debug(f"SELL {ticker}: Position count now {self.position_count}")

            self.prev_ema10[ticker] = ema10
            self.prev_ema50[ticker] = ema50
