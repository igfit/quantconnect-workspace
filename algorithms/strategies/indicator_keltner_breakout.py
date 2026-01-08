from AlgorithmImports import *

class IndicatorKeltnerBreakout(QCAlgorithm):
    """
    Keltner Channel Breakout Strategy

    SOURCE: QuantifiedStrategies.com backtest showed 77% win rate, profit factor 2.0

    CONCEPT:
    - Keltner Channels = EMA(20) +/- 2*ATR(10)
    - Breakout above upper band = strong momentum, ride the trend
    - Use ATR trailing stop for exits

    SIGNAL:
    - Buy when price closes above upper Keltner band
    - Exit when price closes below middle band (EMA) OR trailing stop hit
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
        self.kc_ind = {}
        self.atr_ind = {}
        self.in_position = {}
        self.entry_price = {}
        self.highest_price = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            # Keltner Channel (20, 2)
            self.kc_ind[ticker] = self.KC(symbol, 20, 2.0, MovingAverageType.EXPONENTIAL, Resolution.DAILY)
            self.atr_ind[ticker] = self.atr(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)
            self.in_position[ticker] = False
            self.entry_price[ticker] = 0
            self.highest_price[ticker] = 0

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(30, Resolution.DAILY)

        self.atr_stop_multiplier = 2.0

    def on_data(self, data):
        if self.is_warming_up:
            return

        for ticker in self.basket:
            symbol = self.symbols[ticker]

            if symbol not in data.bars:
                continue

            if not self.kc_ind[ticker].is_ready or not self.atr_ind[ticker].is_ready:
                continue

            price = data.bars[symbol].close
            kc_upper = self.kc_ind[ticker].upper_band.current.value
            kc_middle = self.kc_ind[ticker].middle_band.current.value
            atr = self.atr_ind[ticker].current.value

            if self.in_position[ticker]:
                # Update highest price for trailing stop
                if price > self.highest_price[ticker]:
                    self.highest_price[ticker] = price

                # Trailing stop: 2 ATR below highest
                trailing_stop = self.highest_price[ticker] - (self.atr_stop_multiplier * atr)

                # Exit: price below middle band OR trailing stop hit
                if price < kc_middle or price < trailing_stop:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    pnl = (price - self.entry_price[ticker]) / self.entry_price[ticker] * 100
                    self.debug(f"SELL {ticker}: P&L={pnl:.1f}%")

            else:
                # BUY: Breakout above upper Keltner
                if price > kc_upper:
                    self.set_holdings(symbol, self.weight_per_stock)
                    self.in_position[ticker] = True
                    self.entry_price[ticker] = price
                    self.highest_price[ticker] = price
                    self.debug(f"BUY {ticker}: Keltner breakout at {price:.2f}")
