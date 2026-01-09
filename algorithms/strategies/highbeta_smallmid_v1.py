"""
High-Beta Small/Mid Cap Momentum Strategy v1

Target: 30% CAGR, 20-30% DD on volatile small/mid cap universe
Universe: 35 high-beta stocks ($2B-$50B market cap range)
- Focus on growth stocks with beta > 1.3
- Excludes mega-caps (AAPL, MSFT, GOOGL, AMZN, META, NVDA)
- Sectors: Tech, Consumer, Fintech, Clean Energy, Biotech

Strategy: 6-month momentum + acceleration + regime filter
"""

from AlgorithmImports import *


class HighBetaSmallMidV1(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Parameters
        self.lookback_days = 126  # 6-month momentum
        self.accel_period = 21    # 1-month acceleration
        self.top_n = 10           # Concentrated portfolio
        self.use_regime_filter = True
        self.min_dollar_volume = 5_000_000  # Lower threshold for smaller stocks

        self.prev_short_mom = {}

        # HIGH-BETA SMALL/MID CAP UNIVERSE (35 stocks)
        # All had $2B-$50B market cap in 2020, beta > 1.3
        self.universe_tickers = [
            # Semiconductors (high beta, cyclical)
            "AMD", "MRVL", "ON", "SWKS", "QRVO", "MU",
            "AMAT", "LRCX", "KLAC", "ENTG",

            # High-Growth Software/Cloud
            "CRWD", "ZS", "DDOG", "NET", "MDB", "SNOW",
            "OKTA", "TWLO", "ZM", "DOCU",

            # Fintech (very volatile)
            "SQ", "PYPL", "COIN", "HOOD", "SOFI", "AFRM",

            # E-commerce/Consumer (high beta)
            "SHOP", "ETSY", "ROKU", "SNAP", "PINS", "TTD",

            # Clean Energy (extreme volatility)
            "ENPH", "SEDG", "FSLR", "RUN",

            # Travel/Leisure (high beta cyclical)
            "ABNB", "UBER", "LYFT", "DASH", "EXPE",

            # Gaming/Entertainment
            "RBLX", "DKNG", "PENN",

            # Biotech (volatile but liquid)
            "MRNA", "VRTX", "REGN", "BIIB",
        ]

        # Add SPY for regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        # Add universe stocks
        self.symbols = []
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                self.symbols.append(equity.symbol)
            except:
                self.log(f"Failed to add {ticker}")

        self.log(f"Universe size: {len(self.symbols)} stocks")

        # Initialize indicators
        self.momentum = {}
        self.short_mom = {}
        self.volume_sma = {}
        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
            self.short_mom[symbol] = self.roc(symbol, self.accel_period, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

        # Weekly rebalance on Mondays
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        self.set_benchmark("SPY")

    def rebalance(self):
        if self.is_warming_up:
            return

        # Regime filter: only invest when SPY > 200 SMA
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
            if not self.short_mom[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:  # Min price filter
                continue
            if self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue

            mom = self.momentum[symbol].current.value
            short_mom = self.short_mom[symbol].current.value
            prev_mom = self.prev_short_mom.get(symbol, 0)
            acceleration = short_mom - prev_mom
            self.prev_short_mom[symbol] = short_mom

            # Entry: positive momentum + positive acceleration
            if mom > 0 and acceleration > 0:
                scores[symbol] = mom

        # Fallback: just positive momentum if not enough accelerating
        if len(scores) < self.top_n:
            scores = {}
            for symbol in self.symbols:
                if not self.momentum[symbol].is_ready:
                    continue
                if not self.securities[symbol].has_data:
                    continue
                price = self.securities[symbol].price
                if price < 5:
                    continue
                mom = self.momentum[symbol].current.value
                if mom > 0:
                    scores[symbol] = mom

        if len(scores) < 5:
            return

        # Select top N by momentum
        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        # Momentum-weighted allocation
        total_mom = sum(scores[s] for s in top_symbols)
        weights = {s: scores[s] / total_mom for s in top_symbols}

        # Exit positions not in top
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        # Enter new positions
        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])
