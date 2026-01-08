from AlgorithmImports import *

class IndicatorFastEMADX(QCAlgorithm):
    """
    Fast EMA + ADX Filter Strategy

    CONCEPT:
    - Use faster EMAs (5/20) for quicker entries
    - Only trade when ADX > 25 (strong trend environment)
    - Exit on EMA cross down OR ADX < 20 (trend weakening)

    WHY THIS MIGHT WORK:
    - ADX filters out choppy/ranging markets
    - Only trades when momentum is strong
    - Faster EMAs catch more of the move
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
        self.ema20_ind = {}
        self.adx_ind = {}
        self.prev_ema5 = {}
        self.prev_ema20 = {}
        self.in_position = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.ema5_ind[ticker] = self.ema(symbol, 5, Resolution.DAILY)
            self.ema20_ind[ticker] = self.ema(symbol, 20, Resolution.DAILY)
            self.adx_ind[ticker] = self.adx(symbol, 14, Resolution.DAILY)
            self.prev_ema5[ticker] = None
            self.prev_ema20[ticker] = None
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

            if not all([self.ema5_ind[ticker].is_ready,
                       self.ema20_ind[ticker].is_ready,
                       self.adx_ind[ticker].is_ready]):
                continue

            ema5 = self.ema5_ind[ticker].current.value
            ema20 = self.ema20_ind[ticker].current.value
            adx = self.adx_ind[ticker].current.value

            if self.prev_ema5[ticker] is None:
                self.prev_ema5[ticker] = ema5
                self.prev_ema20[ticker] = ema20
                continue

            # Crossover detection
            bullish_cross = self.prev_ema5[ticker] <= self.prev_ema20[ticker] and ema5 > ema20
            bearish_cross = self.prev_ema5[ticker] >= self.prev_ema20[ticker] and ema5 < ema20

            # ADX filter: Strong trend environment
            strong_trend = adx > 25
            weak_trend = adx < 20

            # BUY: EMA cross + strong trend
            if bullish_cross and strong_trend and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: Fast EMA cross + ADX={adx:.1f}")

            # SELL: Bearish cross OR trend weakening
            elif self.in_position[ticker]:
                if bearish_cross or weak_trend:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    reason = "EMA cross" if bearish_cross else "ADX weak"
                    self.debug(f"SELL {ticker}: {reason}")

            self.prev_ema5[ticker] = ema5
            self.prev_ema20[ticker] = ema20
