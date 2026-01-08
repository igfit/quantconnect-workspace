"""
Indicator Strategy: ADX Strong Trend

SIGNAL: ADX > 25 (strong trend) + Price above 20 EMA + +DI > -DI
- ADX measures trend strength (not direction)
- +DI/-DI determines trend direction
- Only trades strong, confirmed uptrends
- Uses No Top3 universe
"""

from AlgorithmImports import *


class ADXTrendStrategy(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.adx_period = 14
        self.adx_threshold = 25
        self.ema_period = 20
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

        self.adx_ind = {}
        self.ema_ind = {}
        self.volume_sma = {}
        for symbol in self.symbols:
            self.adx_ind[symbol] = self.adx(symbol, self.adx_period, Resolution.DAILY)
            self.ema_ind[symbol] = self.ema(symbol, self.ema_period, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        self.set_warm_up(self.adx_period + 10, Resolution.DAILY)

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
            if not self.adx_ind[symbol].is_ready:
                continue
            if not self.ema_ind[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue
            if self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue

            adx = self.adx_ind[symbol]
            adx_val = adx.current.value
            plus_di = adx.positive_directional_index.current.value
            minus_di = adx.negative_directional_index.current.value
            ema_val = self.ema_ind[symbol].current.value

            # Entry: Strong trend (ADX > 25) + Bullish (+DI > -DI) + Price above EMA
            if adx_val > self.adx_threshold and plus_di > minus_di and price > ema_val:
                # Score by trend strength * directional strength
                di_spread = plus_di - minus_di
                scores[symbol] = adx_val * di_spread

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
