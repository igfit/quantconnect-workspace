from AlgorithmImports import *

class IndicatorBollingerBands(QCAlgorithm):
    """
    INDICATOR SIGNAL Strategy 4: Bollinger Band Mean Reversion

    SIGNAL: Buy when price touches lower band, Sell when touches upper band
    BASKET: Fixed high-quality stocks

    Bollinger Bands (20, 2) show volatility. Price tends to revert to the mean.
    Combined with trend filter (price > 200 SMA) for higher probability.
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
        self.bb_ind = {}
        self.sma200_ind = {}
        self.in_position = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.bb_ind[ticker] = self.bb(symbol, 20, 2, MovingAverageType.SIMPLE, Resolution.DAILY)
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

            if not self.bb_ind[ticker].is_ready or not self.sma200_ind[ticker].is_ready:
                continue

            price = data.bars[symbol].close
            upper = self.bb_ind[ticker].upper_band.current.value
            lower = self.bb_ind[ticker].lower_band.current.value
            middle = self.bb_ind[ticker].middle_band.current.value
            sma200 = self.sma200_ind[ticker].current.value

            # Trend filter - only trade in uptrend
            in_uptrend = price > sma200

            # BUY SIGNAL: Price at lower band in uptrend (oversold bounce)
            if price <= lower and in_uptrend and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: Price={price:.2f} at lower BB={lower:.2f}")

            # SELL SIGNAL: Price at upper band OR trend breaks
            elif self.in_position[ticker]:
                if price >= upper or not in_uptrend:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    self.debug(f"SELL {ticker}: Price={price:.2f}, Upper BB={upper:.2f}")
