from AlgorithmImports import *

class IndicatorDualSignal(QCAlgorithm):
    """
    Dual Signal Confirmation Strategy (EMA + Supertrend)

    CONCEPT:
    - Signal 1: EMA(10) > EMA(50) (trend is up)
    - Signal 2: Price > Supertrend line (momentum confirmed)
    - Buy only when BOTH signals agree (high conviction)
    - Sell when EITHER signal turns bearish

    WHY THIS MIGHT WORK:
    - Two independent trend measures must confirm
    - Reduces false positives significantly
    - Captures only the strongest trends
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

        # Supertrend parameters
        self.atr_period = 10
        self.multiplier = 3.0

        self.symbols = {}
        self.ema10_ind = {}
        self.ema50_ind = {}
        self.atr_ind = {}
        self.in_position = {}
        self.supertrend = {}
        self.trend_direction = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.ema10_ind[ticker] = self.ema(symbol, 10, Resolution.DAILY)
            self.ema50_ind[ticker] = self.ema(symbol, 50, Resolution.DAILY)
            self.atr_ind[ticker] = self.atr(symbol, self.atr_period, MovingAverageType.SIMPLE, Resolution.DAILY)
            self.in_position[ticker] = False
            self.supertrend[ticker] = 0
            self.trend_direction[ticker] = 1

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

            bar = data.bars[symbol]
            close = bar.close
            high = bar.high
            low = bar.low

            ema10 = self.ema10_ind[ticker].current.value
            ema50 = self.ema50_ind[ticker].current.value
            atr = self.atr_ind[ticker].current.value

            # Calculate Supertrend
            hl2 = (high + low) / 2
            upper_band = hl2 + (self.multiplier * atr)
            lower_band = hl2 - (self.multiplier * atr)

            prev_st = self.supertrend[ticker]
            prev_dir = self.trend_direction[ticker]

            if prev_st == 0:
                self.supertrend[ticker] = lower_band if close > hl2 else upper_band
                self.trend_direction[ticker] = 1 if close > hl2 else -1
                continue

            # Update Supertrend
            if prev_dir == 1:
                new_lower = max(lower_band, prev_st) if close > prev_st else lower_band
                if close < prev_st:
                    self.supertrend[ticker] = upper_band
                    self.trend_direction[ticker] = -1
                else:
                    self.supertrend[ticker] = new_lower
                    self.trend_direction[ticker] = 1
            else:
                new_upper = min(upper_band, prev_st) if close < prev_st else upper_band
                if close > prev_st:
                    self.supertrend[ticker] = lower_band
                    self.trend_direction[ticker] = 1
                else:
                    self.supertrend[ticker] = new_upper
                    self.trend_direction[ticker] = -1

            # Signal conditions
            ema_bullish = ema10 > ema50
            supertrend_bullish = self.trend_direction[ticker] == 1

            # BUY: Both signals bullish
            if ema_bullish and supertrend_bullish and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: EMA + Supertrend both bullish")

            # SELL: Either signal turns bearish
            elif self.in_position[ticker] and (not ema_bullish or not supertrend_bullish):
                self.liquidate(symbol)
                self.in_position[ticker] = False
                reason = "EMA bearish" if not ema_bullish else "Supertrend bearish"
                self.debug(f"SELL {ticker}: {reason}")
