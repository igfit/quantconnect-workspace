from AlgorithmImports import *

class IndicatorRSIPullback(QCAlgorithm):
    """
    RSI Pullback Entry Strategy

    CONCEPT:
    - Wait for uptrend: EMA(10) > EMA(50)
    - Enter on pullback: RSI drops to 40-50 zone (not oversold, just cooling)
    - Exit: RSI > 70 (overbought) OR EMA cross down

    WHY THIS MIGHT WORK:
    - Buys dips in strong uptrends (better entries)
    - RSI 40-50 = healthy pullback, not panic selling
    - Professional "buy the dip" approach
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
        self.in_position = {}
        self.prev_rsi = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.ema10_ind[ticker] = self.ema(symbol, 10, Resolution.DAILY)
            self.ema50_ind[ticker] = self.ema(symbol, 50, Resolution.DAILY)
            self.rsi_ind[ticker] = self.rsi(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
            self.in_position[ticker] = False
            self.prev_rsi[ticker] = 50

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

            # Uptrend confirmation
            in_uptrend = ema10 > ema50

            # Pullback zone: RSI in 40-50 range
            in_pullback = 35 <= rsi <= 50

            # RSI coming down (was higher before)
            rsi_pulling_back = rsi < self.prev_rsi[ticker]

            # BUY: Uptrend + RSI pullback zone
            if in_uptrend and in_pullback and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: Pullback entry RSI={rsi:.1f}")

            # SELL: RSI overbought OR trend reversal
            elif self.in_position[ticker]:
                ema_bearish = ema10 < ema50
                if rsi > 75 or ema_bearish:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    reason = "RSI overbought" if rsi > 75 else "trend reversal"
                    self.debug(f"SELL {ticker}: {reason}")

            self.prev_rsi[ticker] = rsi
