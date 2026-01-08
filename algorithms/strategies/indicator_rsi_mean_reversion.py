from AlgorithmImports import *

class IndicatorRSIMeanReversion(QCAlgorithm):
    """
    INDICATOR SIGNAL Strategy 1: RSI Mean Reversion

    SIGNAL: Buy when RSI(14) < 30 (oversold), Sell when RSI(14) > 70 (overbought)
    BASKET: Fixed high-quality stocks

    The RSI signal determines WHEN to be in each stock.
    Each stock is traded independently based on its own RSI.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Fixed basket - high quality, high beta stocks
        self.basket = [
            "NVDA", "META", "GOOGL", "AMZN", "MSFT",
            "AVGO", "AMD", "NFLX", "CRM", "NOW"
        ]

        self.weight_per_stock = 0.10  # 10% each when invested

        self.symbols = {}
        self.rsi_ind = {}
        self.sma200_ind = {}
        self.in_position = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.rsi_ind[ticker] = self.RSI(symbol, 14, MovingAverageType.WILDERS, Resolution.DAILY)
            self.sma200_ind[ticker] = self.sma(symbol, 200)
            self.in_position[ticker] = False

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(210, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up:
            return

        for ticker in self.basket:
            symbol = self.symbols[ticker]

            if symbol not in data.bars:
                continue

            if not self.rsi_ind[ticker].is_ready or not self.sma200_ind[ticker].is_ready:
                continue

            price = data.bars[symbol].close
            rsi = self.rsi_ind[ticker].current.value
            sma200 = self.sma200_ind[ticker].current.value

            # Only trade in uptrend (price > 200 SMA)
            in_uptrend = price > sma200

            # BUY SIGNAL: RSI oversold in uptrend
            if rsi < 30 and in_uptrend and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: RSI={rsi:.1f}")

            # SELL SIGNAL: RSI overbought OR trend breaks
            elif self.in_position[ticker]:
                if rsi > 70 or not in_uptrend:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    self.debug(f"SELL {ticker}: RSI={rsi:.1f}, Uptrend={in_uptrend}")
