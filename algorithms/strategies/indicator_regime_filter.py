from AlgorithmImports import *

class IndicatorRegimeFilter(QCAlgorithm):
    """
    Market Regime + EMA Strategy

    CONCEPT:
    - Only trade when SPY > 200 SMA (bull market regime)
    - Use EMA(10/50) crossover on individual stocks
    - Go to cash when SPY < 200 SMA

    WHY THIS MIGHT WORK:
    - Avoids bear market drawdowns
    - Momentum strategies work best in bull markets
    - 200 SMA is widely watched support level
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Market regime indicator
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)

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
        self.prev_ema10 = {}
        self.prev_ema50 = {}
        self.in_position = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.ema10_ind[ticker] = self.ema(symbol, 10, Resolution.DAILY)
            self.ema50_ind[ticker] = self.ema(symbol, 50, Resolution.DAILY)
            self.prev_ema10[ticker] = None
            self.prev_ema50[ticker] = None
            self.in_position[ticker] = False

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_warm_up(210, Resolution.DAILY)

        self.bull_market = True

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Check market regime
        if self.spy not in data.bars or not self.spy_sma200.is_ready:
            return

        spy_price = data.bars[self.spy].close
        sma200 = self.spy_sma200.current.value
        was_bull = self.bull_market
        self.bull_market = spy_price > sma200

        # If regime changed to bear, liquidate all
        if was_bull and not self.bull_market:
            self.liquidate()
            for ticker in self.basket:
                self.in_position[ticker] = False
            self.debug("BEAR MARKET - Liquidated all")
            return

        # Only trade in bull market
        if not self.bull_market:
            return

        for ticker in self.basket:
            symbol = self.symbols[ticker]

            if symbol not in data.bars:
                continue

            if not all([self.ema10_ind[ticker].is_ready,
                       self.ema50_ind[ticker].is_ready]):
                continue

            ema10 = self.ema10_ind[ticker].current.value
            ema50 = self.ema50_ind[ticker].current.value

            if self.prev_ema10[ticker] is None:
                self.prev_ema10[ticker] = ema10
                self.prev_ema50[ticker] = ema50
                continue

            # Crossover detection
            bullish_cross = self.prev_ema10[ticker] <= self.prev_ema50[ticker] and ema10 > ema50
            bearish_cross = self.prev_ema10[ticker] >= self.prev_ema50[ticker] and ema10 < ema50

            if bullish_cross and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: Bull regime EMA cross")

            elif bearish_cross and self.in_position[ticker]:
                self.liquidate(symbol)
                self.in_position[ticker] = False

            self.prev_ema10[ticker] = ema10
            self.prev_ema50[ticker] = ema50
