"""
Indicator Strategy: Bollinger Band Breakout

SIGNAL: Price breaks above upper Bollinger Band with momentum
- Entry: Price > Upper BB AND positive 1-month momentum
- Strong breakout signal (volatility expansion)
- Uses No Top3 universe
"""

from AlgorithmImports import *


class BBBreakoutStrategy(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.bb_period = 20
        self.bb_std = 2.0
        self.mom_period = 21
        self.top_n = 10
        self.use_regime_filter = True
        self.min_dollar_volume = 5_000_000

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

        self.bb_ind = {}
        self.mom_ind = {}
        self.volume_sma = {}
        for symbol in self.symbols:
            self.bb_ind[symbol] = self.bb(symbol, self.bb_period, self.bb_std, MovingAverageType.SIMPLE, Resolution.DAILY)
            self.mom_ind[symbol] = self.roc(symbol, self.mom_period, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        self.set_warm_up(self.bb_period + 10, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        self.set_benchmark("SPY")

    def rebalance(self):
        if self.is_warming_up:
            return

        if self.use_regime_filter:
            if not self.spy_sma.is_ready:
                return
            if self.securities[self.spy].price < self.spy_sma.current.value:
                self.liquidate()
                return

        scores = {}

        for symbol in self.symbols:
            if not self.bb_ind[symbol].is_ready:
                continue
            if not self.mom_ind[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue
            if self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue

            bb = self.bb_ind[symbol]
            upper_band = bb.upper_band.current.value
            middle_band = bb.middle_band.current.value
            mom = self.mom_ind[symbol].current.value

            # Entry: Price above upper BB AND positive momentum
            if price > upper_band and mom > 0:
                # Score by breakout strength (% above upper band)
                breakout_pct = (price - upper_band) / upper_band
                scores[symbol] = breakout_pct * (1 + mom)

        if len(scores) < 5:
            # Fallback: stocks near upper band with momentum
            for symbol in self.symbols:
                if symbol in scores:
                    continue
                if not self.bb_ind[symbol].is_ready:
                    continue
                if not self.mom_ind[symbol].is_ready:
                    continue
                if not self.securities[symbol].has_data:
                    continue

                price = self.securities[symbol].price
                if price < 5:
                    continue

                bb = self.bb_ind[symbol]
                upper_band = bb.upper_band.current.value
                middle_band = bb.middle_band.current.value
                mom = self.mom_ind[symbol].current.value

                # Near upper band (within 2%) with momentum
                if price > middle_band and price > upper_band * 0.98 and mom > 0:
                    scores[symbol] = mom

        if len(scores) < 5:
            return

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        weight = 1.0 / actual_n

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weight)
