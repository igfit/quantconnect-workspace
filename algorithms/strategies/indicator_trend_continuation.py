from AlgorithmImports import *

class IndicatorTrendContinuation(QCAlgorithm):
    """
    Trend Continuation Strategy (Multiple Timeframe Alignment)

    CONCEPT:
    - Only buy when ALL three conditions met:
      1. Price > 50-day SMA (long-term uptrend)
      2. Price > 20-day SMA (medium-term uptrend)
      3. RSI > 50 (momentum positive)
    - Hold until 2 of 3 conditions fail

    WHY THIS MIGHT WORK:
    - Multiple timeframe alignment = strong trend
    - RSI > 50 confirms buyers in control
    - Simple rules, high probability setups
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
        self.sma20_ind = {}
        self.sma50_ind = {}
        self.rsi_ind = {}
        self.in_position = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.sma20_ind[ticker] = self.sma(symbol, 20, Resolution.DAILY)
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)
            self.rsi_ind[ticker] = self.rsi(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
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

            if not all([self.sma20_ind[ticker].is_ready,
                       self.sma50_ind[ticker].is_ready,
                       self.rsi_ind[ticker].is_ready]):
                continue

            price = data.bars[symbol].close
            sma20 = self.sma20_ind[ticker].current.value
            sma50 = self.sma50_ind[ticker].current.value
            rsi = self.rsi_ind[ticker].current.value

            # Three conditions for alignment
            above_sma50 = price > sma50
            above_sma20 = price > sma20
            rsi_positive = rsi > 50

            # Count bullish conditions
            bullish_count = sum([above_sma50, above_sma20, rsi_positive])

            # BUY: All 3 conditions met
            if bullish_count == 3 and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: Full alignment (RSI={rsi:.1f})")

            # SELL: 2 or more conditions fail
            elif self.in_position[ticker] and bullish_count <= 1:
                self.liquidate(symbol)
                self.in_position[ticker] = False
                self.debug(f"SELL {ticker}: Alignment broken ({bullish_count}/3)")
