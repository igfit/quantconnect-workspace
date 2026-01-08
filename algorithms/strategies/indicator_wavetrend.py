from AlgorithmImports import *

class IndicatorWaveTrend(QCAlgorithm):
    """
    WaveTrend Oscillator Strategy (LazyBear)

    SOURCE: Popular TradingView indicator by LazyBear, combines ATR and SMA concepts

    CONCEPT:
    - WaveTrend is a momentum oscillator showing overbought/oversold
    - Uses exponential smoothing of price relative to average price
    - Crossovers of WT1 and WT2 lines signal entries

    SIGNAL:
    - Buy when WT1 crosses above WT2 AND both are below 0 (oversold)
    - Sell when WT1 crosses below WT2 AND both are above 0 (overbought)
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

        # WaveTrend parameters
        self.channel_length = 10
        self.avg_length = 21

        self.symbols = {}
        self.ema_price = {}  # EMA of HLC3
        self.ema_diff = {}   # EMA of abs(HLC3 - EMA)
        self.wt1 = {}
        self.wt2 = {}
        self.prev_wt1 = {}
        self.prev_wt2 = {}
        self.in_position = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.wt1[ticker] = 0
            self.wt2[ticker] = 0
            self.prev_wt1[ticker] = 0
            self.prev_wt2[ticker] = 0
            self.ema_price[ticker] = None
            self.ema_diff[ticker] = None
            self.in_position[ticker] = False

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(50, Resolution.DAILY)

        # EMA multipliers
        self.ema_mult_channel = 2 / (self.channel_length + 1)
        self.ema_mult_avg = 2 / (self.avg_length + 1)

    def on_data(self, data):
        if self.is_warming_up:
            return

        for ticker in self.basket:
            symbol = self.symbols[ticker]

            if symbol not in data.bars:
                continue

            bar = data.bars[symbol]
            hlc3 = (bar.high + bar.low + bar.close) / 3

            # Calculate WaveTrend
            # Step 1: EMA of HLC3
            if self.ema_price[ticker] is None:
                self.ema_price[ticker] = hlc3
                self.ema_diff[ticker] = 0
                continue

            self.ema_price[ticker] = (hlc3 - self.ema_price[ticker]) * self.ema_mult_channel + self.ema_price[ticker]

            # Step 2: EMA of absolute difference
            diff = abs(hlc3 - self.ema_price[ticker])
            self.ema_diff[ticker] = (diff - self.ema_diff[ticker]) * self.ema_mult_channel + self.ema_diff[ticker]

            # Step 3: Calculate CI (Channel Index)
            ci = (hlc3 - self.ema_price[ticker]) / (0.015 * self.ema_diff[ticker]) if self.ema_diff[ticker] != 0 else 0

            # Step 4: WT1 = EMA of CI
            self.prev_wt1[ticker] = self.wt1[ticker]
            self.wt1[ticker] = (ci - self.wt1[ticker]) * self.ema_mult_avg + self.wt1[ticker]

            # Step 5: WT2 = SMA of WT1 (using 4-period)
            self.prev_wt2[ticker] = self.wt2[ticker]
            self.wt2[ticker] = (self.wt1[ticker] - self.wt2[ticker]) * (2/5) + self.wt2[ticker]

            wt1 = self.wt1[ticker]
            wt2 = self.wt2[ticker]
            prev_wt1 = self.prev_wt1[ticker]
            prev_wt2 = self.prev_wt2[ticker]

            # Crossover detection
            bullish_cross = prev_wt1 <= prev_wt2 and wt1 > wt2
            bearish_cross = prev_wt1 >= prev_wt2 and wt1 < wt2

            # Trading signals
            if bullish_cross and wt1 < 0 and not self.in_position[ticker]:
                # Buy on bullish cross in oversold territory
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: WaveTrend bullish cross, WT1={wt1:.1f}")

            elif bearish_cross and wt1 > 0 and self.in_position[ticker]:
                # Sell on bearish cross in overbought territory
                self.liquidate(symbol)
                self.in_position[ticker] = False
                self.debug(f"SELL {ticker}: WaveTrend bearish cross, WT1={wt1:.1f}")
