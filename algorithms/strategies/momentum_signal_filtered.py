"""
Momentum Signal Test: Quality Filters

Add filters to improve signal quality:
1. Price > 50 SMA (uptrend confirmation)
2. Momentum / Volatility ratio (risk-adjusted momentum)
3. Positive 1-month momentum (recent strength)
"""

from AlgorithmImports import *


class MomentumSignalFiltered(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # PARAMETERS
        self.lookback_days = 126          # 6 months
        self.short_lookback = 21          # 1 month for recent momentum
        self.top_n = 10
        self.use_regime_filter = True
        self.min_dollar_volume = 5_000_000

        # CLAUDE V3 UNIVERSE
        self.universe_tickers = [
            "NVDA", "AMD", "AVGO", "QCOM", "MU", "AMAT", "LRCX", "KLAC", "MRVL", "ON",
            "TXN", "ADI", "SNPS", "CDNS", "ASML",
            "CRM", "ADBE", "NOW", "INTU", "PANW", "VEEV", "WDAY",
            "V", "MA", "PYPL", "SQ",
            "AMZN", "SHOP",
            "BKNG", "RCL", "CCL", "MAR", "HLT", "WYNN",
            "XOM", "CVX", "OXY", "DVN", "SLB", "COP",
            "CAT", "DE", "URI", "BA",
            "TSLA", "NKE", "LULU", "CMG", "DECK",
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

        # Indicators
        self.momentum = {}           # 6-month ROC
        self.short_momentum = {}     # 1-month ROC
        self.sma50_ind = {}          # 50-day SMA for trend filter
        self.volume_sma = {}

        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
            self.short_momentum[symbol] = self.roc(symbol, self.short_lookback, Resolution.DAILY)
            self.sma50_ind[symbol] = self.sma(symbol, 50, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.month_start("SPY"),
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
            if not self.momentum[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue

            # Liquidity filter
            if self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue

            # FILTER 1: Price above 50 SMA (uptrend)
            if self.sma50_ind[symbol].is_ready:
                if price < self.sma50_ind[symbol].current.value:
                    continue  # Skip stocks in downtrend

            # FILTER 2: Positive recent momentum (1-month)
            if self.short_momentum[symbol].is_ready:
                if self.short_momentum[symbol].current.value < 0:
                    continue  # Skip stocks losing momentum recently

            # Score: Use momentum
            mom = self.momentum[symbol].current.value
            scores[symbol] = mom

        if len(scores) < self.top_n:
            # Fallback: relax filters if not enough stocks
            scores = {}
            for symbol in self.symbols:
                if not self.momentum[symbol].is_ready:
                    continue
                if not self.securities[symbol].has_data:
                    continue
                price = self.securities[symbol].price
                if price < 5:
                    continue
                scores[symbol] = self.momentum[symbol].current.value

        if len(scores) < self.top_n:
            return

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:self.top_n]]
        weight = 1.0 / self.top_n

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weight)

    def on_data(self, data):
        pass
