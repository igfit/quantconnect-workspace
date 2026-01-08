from AlgorithmImports import *

class IndicatorEMAATRStop(QCAlgorithm):
    """
    EMA Crossover + ATR Trailing Stop Strategy

    CONCEPT:
    - Entry: EMA(10) crosses above EMA(50)
    - Exit: ATR trailing stop (2x ATR below high) OR bearish EMA cross
    - Let winners run, cut losers quickly

    WHY THIS MIGHT WORK:
    - ATR stop adapts to each stock's volatility
    - Protects profits during strong trends
    - Avoids giving back large gains in pullbacks
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
        self.atr_multiplier = 2.0

        self.symbols = {}
        self.ema10_ind = {}
        self.ema50_ind = {}
        self.atr_ind = {}
        self.prev_ema10 = {}
        self.prev_ema50 = {}
        self.in_position = {}
        self.highest_price = {}
        self.entry_price = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.ema10_ind[ticker] = self.ema(symbol, 10, Resolution.DAILY)
            self.ema50_ind[ticker] = self.ema(symbol, 50, Resolution.DAILY)
            self.atr_ind[ticker] = self.atr(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
            self.prev_ema10[ticker] = None
            self.prev_ema50[ticker] = None
            self.in_position[ticker] = False
            self.highest_price[ticker] = 0
            self.entry_price[ticker] = 0

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
                       self.atr_ind[ticker].is_ready]):
                continue

            price = data.bars[symbol].close
            ema10 = self.ema10_ind[ticker].current.value
            ema50 = self.ema50_ind[ticker].current.value
            atr = self.atr_ind[ticker].current.value

            if self.prev_ema10[ticker] is None:
                self.prev_ema10[ticker] = ema10
                self.prev_ema50[ticker] = ema50
                continue

            # Crossover detection
            bullish_cross = self.prev_ema10[ticker] <= self.prev_ema50[ticker] and ema10 > ema50
            bearish_cross = self.prev_ema10[ticker] >= self.prev_ema50[ticker] and ema10 < ema50

            if self.in_position[ticker]:
                # Update highest price for trailing stop
                if price > self.highest_price[ticker]:
                    self.highest_price[ticker] = price

                # Calculate trailing stop
                trailing_stop = self.highest_price[ticker] - (self.atr_multiplier * atr)

                # Exit: Price below trailing stop OR bearish EMA cross
                if price < trailing_stop or bearish_cross:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    pnl = (price - self.entry_price[ticker]) / self.entry_price[ticker] * 100
                    exit_reason = "ATR stop" if price < trailing_stop else "EMA cross"
                    self.debug(f"SELL {ticker}: {exit_reason}, P&L={pnl:.1f}%")

            else:
                # BUY: Bullish EMA cross
                if bullish_cross:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.in_position[ticker] = True
                    self.entry_price[ticker] = price
                    self.highest_price[ticker] = price
                    self.debug(f"BUY {ticker}: EMA cross at {price:.2f}")

            self.prev_ema10[ticker] = ema10
            self.prev_ema50[ticker] = ema50
