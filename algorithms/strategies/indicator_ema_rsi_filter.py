from AlgorithmImports import *

class IndicatorEMARSIFilter(QCAlgorithm):
    """
    EMA Crossover + RSI Filter Strategy

    CONCEPT:
    - Base signal: EMA(10) crosses above EMA(50)
    - Filter: Only buy when RSI(14) < 70 (not overbought)
    - Exit: EMA(10) crosses below EMA(50)

    WHY THIS MIGHT WORK:
    - Filters out late entries when momentum already exhausted
    - Combines trend-following (EMA) with mean-reversion filter (RSI)
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
        self.rsi_ind = {}
        self.prev_ema10 = {}
        self.prev_ema50 = {}
        self.in_position = {}

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

            # BUY: EMA cross + RSI not overbought
            if bullish_cross and rsi < 70 and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: EMA cross + RSI={rsi:.1f} (not overbought)")

            # SELL: Bearish EMA cross
            elif bearish_cross and self.in_position[ticker]:
                self.liquidate(symbol)
                self.in_position[ticker] = False
                self.debug(f"SELL {ticker}: EMA bearish cross")

            self.prev_ema10[ticker] = ema10
            self.prev_ema50[ticker] = ema50
