"""
Creative Combo #5: Wave-EWO + MACD Fusion

Combine Wave-EWO's trend detection with MACD's momentum confirmation.

Wave-EWO: Primary trend signal (5/34 SMA)
MACD: Momentum confirmation (12/26/9)

Entry: EWO > 0 AND MACD histogram > 0 AND MACD rising
Exit: EWO < 0 OR MACD histogram turns negative

Hypothesis: EWO catches trend early, MACD confirms momentum
is accelerating. Double confirmation = higher win rate.
"""

from AlgorithmImports import *


class WaveMACDFusion(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # EWO parameters
        self.ewo_fast = 5
        self.ewo_slow = 34

        # MACD parameters
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9

        self.top_n = 10
        self.use_regime_filter = True

        # NO TOP3 UNIVERSE
        self.universe_tickers = [
            "AMD", "AVGO", "QCOM", "MU", "AMAT", "LRCX", "KLAC", "MRVL", "ON",
            "TXN", "ADI", "SNPS", "CDNS", "ASML",
            "CRM", "ADBE", "NOW", "INTU", "PANW", "VEEV", "WDAY",
            "V", "MA", "PYPL", "SQ",
            "AMZN", "SHOP",
            "BKNG", "RCL", "CCL", "MAR", "HLT", "WYNN",
            "XOM", "CVX", "OXY", "DVN", "SLB", "COP",
            "CAT", "DE", "URI", "BA",
            "NKE", "LULU", "CMG", "DECK",
            "GS", "MS",
            "NFLX", "ROKU",
        ]

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        self.symbols = []
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                self.symbols.append(equity.symbol)
            except:
                pass

        # EWO indicators
        self.sma_fast = {}
        self.sma_slow = {}

        # MACD indicators
        self.macd_ind = {}
        self.prev_histogram = {}

        for symbol in self.symbols:
            self.sma_fast[symbol] = self.sma(symbol, self.ewo_fast, Resolution.DAILY)
            self.sma_slow[symbol] = self.sma(symbol, self.ewo_slow, Resolution.DAILY)
            self.macd_ind[symbol] = self.macd(symbol, self.macd_fast, self.macd_slow,
                                               self.macd_signal, MovingAverageType.EXPONENTIAL,
                                               Resolution.DAILY)
            self.prev_histogram[symbol] = None

        self.set_warm_up(self.ewo_slow + 10, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        self.set_benchmark("SPY")

    def get_ewo(self, symbol):
        """Calculate EWO"""
        if not self.sma_fast[symbol].is_ready or not self.sma_slow[symbol].is_ready:
            return None
        return self.sma_fast[symbol].current.value - self.sma_slow[symbol].current.value

    def get_macd_histogram(self, symbol):
        """Get MACD histogram value"""
        if not self.macd_ind[symbol].is_ready:
            return None
        macd = self.macd_ind[symbol]
        return macd.current.value - macd.signal.current.value

    def rebalance(self):
        if self.is_warming_up:
            return

        # Regime filter
        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                return

        scores = {}

        for symbol in self.symbols:
            ewo = self.get_ewo(symbol)
            histogram = self.get_macd_histogram(symbol)
            prev_hist = self.prev_histogram.get(symbol)

            if ewo is None or histogram is None:
                if histogram is not None:
                    self.prev_histogram[symbol] = histogram
                continue

            if not self.securities[symbol].has_data:
                self.prev_histogram[symbol] = histogram
                continue

            price = self.securities[symbol].price
            if price < 5:
                self.prev_histogram[symbol] = histogram
                continue

            # Entry: EWO > 0 AND histogram > 0
            if ewo > 0 and histogram > 0:
                # Bonus for rising histogram (accelerating momentum)
                rising_bonus = 1.5 if (prev_hist is not None and histogram > prev_hist) else 1.0
                # Score by combined strength
                scores[symbol] = (ewo / price * 100 + histogram / price * 100) * rising_bonus

            self.prev_histogram[symbol] = histogram

        # Exit conditions
        for holding in list(self.portfolio.values()):
            if holding.invested and holding.symbol in self.symbols:
                ewo = self.get_ewo(holding.symbol)
                histogram = self.get_macd_histogram(holding.symbol)

                # Exit if EWO turns negative OR histogram turns negative
                if ewo is not None and ewo < 0:
                    self.liquidate(holding.symbol)
                elif histogram is not None and histogram < 0:
                    self.liquidate(holding.symbol)

        if len(scores) < 3:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        weight = 1.0 / actual_n

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols and holding.symbol != self.spy:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weight)
