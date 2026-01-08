"""
Momentum Signal Testing - Optimize Trading Signals

Using Claude V3 universe (fixed), iterate on:
1. Lookback period for momentum calculation
2. Number of positions (concentration)
3. Rebalancing frequency
4. Momentum quality filters

TEST 1: 3-month lookback, Top 10 positions (more concentrated, faster signals)
"""

from AlgorithmImports import *


class MomentumSignalTest(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # ============================================================
        # SIGNAL PARAMETERS TO TEST
        # ============================================================
        self.lookback_days = 63          # TEST: 3 months (vs 6 months)
        self.top_n = 10                  # TEST: Top 10 (vs 15)
        self.use_regime_filter = True
        self.min_dollar_volume = 5_000_000  # Increased liquidity requirement

        # ============================================================
        # CLAUDE V3 UNIVERSE (FIXED)
        # ============================================================
        self.universe_tickers = [
            # Semiconductors
            "NVDA", "AMD", "AVGO", "QCOM", "MU", "AMAT", "LRCX", "KLAC", "MRVL", "ON",
            "TXN", "ADI", "SNPS", "CDNS", "ASML",
            # Software leaders
            "CRM", "ADBE", "NOW", "INTU", "PANW", "VEEV", "WDAY",
            # Payments
            "V", "MA", "PYPL", "SQ",
            # E-commerce
            "AMZN", "SHOP",
            # Travel/Leisure
            "BKNG", "RCL", "CCL", "MAR", "HLT", "WYNN",
            # Energy
            "XOM", "CVX", "OXY", "DVN", "SLB", "COP",
            # Industrials
            "CAT", "DE", "URI", "BA",
            # Consumer growth
            "TSLA", "NKE", "LULU", "CMG", "DECK",
            # Banks
            "GS", "MS",
            # Streaming
            "NFLX", "ROKU",
        ]

        # Regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Add universe
        self.symbols = []
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                self.symbols.append(equity.symbol)
            except:
                pass

        # Momentum indicators
        self.momentum = {}
        self.volume_sma = {}
        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        self.set_warm_up(max(self.lookback_days, 200) + 10, Resolution.DAILY)

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_benchmark("SPY")

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

        # Score symbols
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
                dollar_volume = self.volume_sma[symbol].current.value * price
                if dollar_volume < self.min_dollar_volume:
                    continue

            scores[symbol] = self.momentum[symbol].current.value

        if len(scores) < self.top_n:
            return

        # Rank and select
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
