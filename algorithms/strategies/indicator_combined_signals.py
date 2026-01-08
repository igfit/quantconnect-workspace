from AlgorithmImports import *

class IndicatorCombinedSignals(QCAlgorithm):
    """
    INDICATOR SIGNAL Strategy 5: Combined Multi-Indicator

    SIGNAL: Buy when multiple indicators align (confirmation)
    - RSI < 40 (approaching oversold)
    - Price > EMA(50) (uptrend)
    - MACD histogram turning positive (momentum shift)

    Sell when:
    - RSI > 70 (overbought) OR
    - Price < EMA(50) (trend break)

    BASKET: Fixed high-quality stocks
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Fixed basket
        self.basket = [
            "NVDA", "META", "GOOGL", "AMZN", "MSFT",
            "AVGO", "AMD", "NFLX", "CRM", "NOW"
        ]

        self.weight_per_stock = 0.10

        self.symbols = {}
        self.rsi_ind = {}
        self.ema50_ind = {}
        self.macd_ind = {}
        self.prev_histogram = {}
        self.in_position = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.rsi_ind[ticker] = self.RSI(symbol, 14, MovingAverageType.WILDERS, Resolution.DAILY)
            self.ema50_ind[ticker] = self.ema(symbol, 50, Resolution.DAILY)
            self.macd_ind[ticker] = self.MACD(symbol, 12, 26, 9, MovingAverageType.EXPONENTIAL, Resolution.DAILY)
            self.prev_histogram[ticker] = None
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

            if not all([
                self.rsi_ind[ticker].is_ready,
                self.ema50_ind[ticker].is_ready,
                self.macd_ind[ticker].is_ready
            ]):
                continue

            price = data.bars[symbol].close
            rsi = self.rsi_ind[ticker].current.value
            ema50 = self.ema50_ind[ticker].current.value
            histogram = self.macd_ind[ticker].histogram.current.value

            # Check conditions
            in_uptrend = price > ema50
            rsi_favorable = rsi < 40  # Not overbought, approaching oversold
            rsi_overbought = rsi > 70

            # MACD histogram turning positive (momentum shift)
            macd_turning_up = False
            if self.prev_histogram[ticker] is not None:
                macd_turning_up = self.prev_histogram[ticker] < 0 and histogram > 0

            # BUY SIGNAL: Multiple confirmations
            # 1. In uptrend (price > EMA50)
            # 2. RSI favorable (< 40)
            # 3. MACD histogram turning positive
            if in_uptrend and rsi_favorable and macd_turning_up and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: RSI={rsi:.1f}, MACD Hist turning up")

            # SELL SIGNAL: RSI overbought OR trend break
            elif self.in_position[ticker]:
                if rsi_overbought or not in_uptrend:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    self.debug(f"SELL {ticker}: RSI={rsi:.1f}, Uptrend={in_uptrend}")

            # Update previous histogram
            self.prev_histogram[ticker] = histogram
