from AlgorithmImports import *

class IndicatorATRTrailingStop(QCAlgorithm):
    """
    INDICATOR SIGNAL Strategy 6: ATR Trailing Stop Trend Following

    SIGNAL:
    - Buy when price breaks above 20-day high (breakout)
    - Trail stop at 2x ATR below highest price
    - Sell when price hits trailing stop

    BASKET: Fixed high-quality stocks

    This rides trends and lets winners run while cutting losers quickly.
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
        self.atr_ind = {}
        self.highest_ind = {}
        self.in_position = {}
        self.highest_since_entry = {}
        self.trailing_stop = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.atr_ind[ticker] = self.atr(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
            self.highest_ind[ticker] = self.MAX(symbol, 20, Resolution.DAILY)
            self.in_position[ticker] = False
            self.highest_since_entry[ticker] = 0
            self.trailing_stop[ticker] = 0

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(30, Resolution.DAILY)

        self.atr_multiplier = 2.0

    def on_data(self, data):
        if self.is_warming_up:
            return

        for ticker in self.basket:
            symbol = self.symbols[ticker]

            if symbol not in data.bars:
                continue

            if not self.atr_ind[ticker].is_ready or not self.highest_ind[ticker].is_ready:
                continue

            price = data.bars[symbol].close
            atr = self.atr_ind[ticker].current.value
            highest_20d = self.highest_ind[ticker].current.value

            if self.in_position[ticker]:
                # Update trailing stop
                if price > self.highest_since_entry[ticker]:
                    self.highest_since_entry[ticker] = price
                    self.trailing_stop[ticker] = price - (self.atr_multiplier * atr)

                # SELL SIGNAL: Price hits trailing stop
                if price <= self.trailing_stop[ticker]:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    self.debug(f"SELL {ticker}: Price={price:.2f} hit stop={self.trailing_stop[ticker]:.2f}")

            else:
                # BUY SIGNAL: Breakout above 20-day high
                if price >= highest_20d and atr > 0:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.in_position[ticker] = True
                    self.highest_since_entry[ticker] = price
                    self.trailing_stop[ticker] = price - (self.atr_multiplier * atr)
                    self.debug(f"BUY {ticker}: Breakout at {price:.2f}, Stop={self.trailing_stop[ticker]:.2f}")
