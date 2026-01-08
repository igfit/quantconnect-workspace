from AlgorithmImports import *

class IndicatorRSI2Connors(QCAlgorithm):
    """
    RSI-2 Mean Reversion Strategy (Larry Connors)

    SOURCE: "Short Term Trading Strategies That Work" by Larry Connors
    BACKTEST CLAIMS: 75% win rate on S&P 500, 0.5-0.66% avg gain per trade

    SIGNAL:
    - Buy when 2-period RSI < 10 AND price > 200 SMA (uptrend)
    - Sell when 2-period RSI > 90 OR price closes above 5 SMA

    This is a SHORT-TERM mean reversion strategy. Trades last 2-5 days.
    The edge comes from buying extreme oversold bounces in uptrends.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # 25-stock basket - diversified high-quality growth stocks
        self.basket = [
            # Mega-cap tech
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA",
            # Growth tech
            "AVGO", "AMD", "NFLX", "CRM", "NOW", "ADBE", "ORCL",
            # Financials
            "V", "MA", "JPM", "GS",
            # Healthcare
            "LLY", "UNH", "ABBV",
            # Consumer/Industrial
            "COST", "HD", "CAT", "GE", "HON"
        ]

        self.weight_per_stock = 0.04  # 4% per position (can hold up to 25)

        self.symbols = {}
        self.rsi2_ind = {}
        self.sma200_ind = {}
        self.sma5_ind = {}
        self.in_position = {}

        for ticker in self.basket:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            # Key: 2-period RSI (very sensitive)
            self.rsi2_ind[ticker] = self.RSI(symbol, 2, MovingAverageType.WILDERS, Resolution.DAILY)
            self.sma200_ind[ticker] = self.sma(symbol, 200)
            self.sma5_ind[ticker] = self.sma(symbol, 5)
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

            if not all([self.rsi2_ind[ticker].is_ready,
                       self.sma200_ind[ticker].is_ready,
                       self.sma5_ind[ticker].is_ready]):
                continue

            price = data.bars[symbol].close
            rsi2 = self.rsi2_ind[ticker].current.value
            sma200 = self.sma200_ind[ticker].current.value
            sma5 = self.sma5_ind[ticker].current.value

            in_uptrend = price > sma200

            # BUY: RSI-2 extremely oversold in uptrend
            if rsi2 < 10 and in_uptrend and not self.in_position[ticker]:
                self.set_holdings(symbol, self.weight_per_stock)
                self.in_position[ticker] = True
                self.debug(f"BUY {ticker}: RSI2={rsi2:.1f}")

            # SELL: RSI-2 overbought OR price above 5 SMA (Connors exit)
            elif self.in_position[ticker]:
                if rsi2 > 90 or price > sma5:
                    self.liquidate(symbol)
                    self.in_position[ticker] = False
                    self.debug(f"SELL {ticker}: RSI2={rsi2:.1f}")
