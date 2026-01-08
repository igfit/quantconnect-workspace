from AlgorithmImports import *

class IndicatorMomentumBreakout(QCAlgorithm):
    """
    Momentum Breakout Strategy (High Conviction)

    CONCEPT:
    - Buy only on NEW 20-day high AND EMA(10) > EMA(50)
    - This catches strong breakout moves with trend confirmation
    - Exit when price falls below EMA(21) OR makes 10-day low

    WHY THIS MIGHT WORK:
    - Breakouts signal institutional buying
    - New highs = path of least resistance is up
    - Strict entry = fewer but higher quality trades
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
        self.ema21_ind = {}
        self.max_ind = {}
        self.min_ind = {}
        self.in_position = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.ema10_ind[ticker] = self.ema(symbol, 10, Resolution.DAILY)
            self.ema50_ind[ticker] = self.ema(symbol, 50, Resolution.DAILY)
            self.ema21_ind[ticker] = self.ema(symbol, 21, Resolution.DAILY)
            self.max_ind[ticker] = self.MAX(symbol, 20, Resolution.DAILY)
            self.min_ind[ticker] = self.MIN(symbol, 10, Resolution.DAILY)
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
                       self.ema21_ind[ticker].is_ready,
                       self.max_ind[ticker].is_ready,
                       self.min_ind[ticker].is_ready]):
                continue

            price = data.bars[symbol].close
            ema10 = self.ema10_ind[ticker].current.value
            ema50 = self.ema50_ind[ticker].current.value
            ema21 = self.ema21_ind[ticker].current.value
            high_20d = self.max_ind[ticker].current.value
            low_10d = self.min_ind[ticker].current.value

            # EMA trend confirmation
            ema_bullish = ema10 > ema50

            # Breakout: Price at or near 20-day high
            at_breakout = price >= high_20d * 0.99  # Within 1% of high

            # BUY: New high + EMA bullish
            if at_breakout and ema_bullish and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: Breakout at {price:.2f} (20d high={high_20d:.2f})")

            # SELL: Below EMA(21) OR at 10-day low
            elif self.in_position[ticker]:
                if price < ema21 or price <= low_10d:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    reason = "below EMA21" if price < ema21 else "10d low"
                    self.debug(f"SELL {ticker}: {reason}")
