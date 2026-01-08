"""
Momentum Strategy: Broad Universe (100+ stocks)

GOAL: Maximum diversification, no single-stock dependency
- 100+ high-beta stocks across sectors
- Equal-weight positions (no momentum weighting)
- Top 20 positions at 5% each
- Excludes mega-caps (FAANG, top semis)
"""

from AlgorithmImports import *


class MomentumBroadUniverse(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        self.lookback_days = 126
        self.accel_period = 21
        self.top_n = 20  # More positions
        self.use_regime_filter = True
        self.min_dollar_volume = 2_000_000

        self.prev_short_mom = {}

        # BROAD UNIVERSE - 100+ HIGH-BETA STOCKS (NO MEGA-CAPS)
        self.universe_tickers = [
            # Semiconductors (mid-cap)
            "QCOM", "MU", "AMAT", "LRCX", "KLAC", "MRVL", "ON", "TXN", "ADI",
            "SNPS", "CDNS", "MPWR", "SWKS", "QRVO", "WOLF", "SLAB", "RMBS",
            # Software/SaaS
            "CRM", "NOW", "INTU", "PANW", "VEEV", "WDAY", "CRWD", "DDOG",
            "ZS", "NET", "MDB", "SNOW", "OKTA", "TWLO", "HUBS", "BILL",
            "DOCU", "FIVN", "ESTC", "CFLT", "SUMO", "S", "PATH",
            # Fintech
            "PYPL", "SQ", "AFRM", "SOFI", "UPST", "COIN", "HOOD", "LPRO",
            # E-commerce/Consumer Tech
            "SHOP", "ETSY", "CHWY", "W", "PINS", "SNAP", "MTCH", "BMBL",
            # Travel/Leisure
            "BKNG", "RCL", "CCL", "MAR", "HLT", "WYNN", "LVS", "MGM",
            "ABNB", "EXPE", "UAL", "DAL", "AAL", "LUV", "JBLU",
            # Energy
            "OXY", "DVN", "SLB", "COP", "EOG", "PXD", "MRO", "APA",
            "FANG", "HAL", "BKR", "NOV", "RIG",
            # Industrials
            "CAT", "DE", "URI", "PCAR", "CMI", "EMR", "ROK", "IR",
            "XYL", "TT", "GNRC", "PLUG", "ENPH", "SEDG", "RUN",
            # Consumer/Retail
            "NKE", "LULU", "CMG", "DECK", "SBUX", "DPZ", "YUM",
            "ULTA", "TJX", "ROST", "DG", "DLTR", "FIVE", "OLLI",
            # Biotech/Healthcare
            "MRNA", "BNTX", "REGN", "VRTX", "BIIB", "ILMN", "EXAS",
            "DXCM", "PODD", "ISRG", "ALGN", "HOLX", "TECH",
            # Streaming/Media/Gaming
            "NFLX", "ROKU", "SPOT", "TTD", "RBLX", "TTWO", "EA",
            "MTCH", "ZG", "OPEN", "CVNA",
            # Finance
            "GS", "MS", "SCHW", "IBKR", "LPLA", "RJF", "MKTX",
            # REITs (high beta)
            "AMT", "CCI", "EQIX", "DLR", "PSA",
            # Misc Growth
            "DASH", "DKNG", "PENN", "CHPT", "LCID", "RIVN",
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

        self.log(f"Added {len(self.symbols)} symbols to universe")

        self.momentum = {}
        self.short_mom = {}
        self.volume_sma = {}
        for symbol in self.symbols:
            self.momentum[symbol] = self.roc(symbol, self.lookback_days, Resolution.DAILY)
            self.short_mom[symbol] = self.roc(symbol, self.accel_period, Resolution.DAILY)
            self.volume_sma[symbol] = self.sma(symbol, 20, Resolution.DAILY, Field.VOLUME)

        self.set_warm_up(self.lookback_days + 10, Resolution.DAILY)

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
            if not self.momentum[symbol].is_ready:
                continue
            if not self.short_mom[symbol].is_ready:
                continue
            if not self.securities[symbol].has_data:
                continue

            price = self.securities[symbol].price
            if price < 5:
                continue
            if self.volume_sma[symbol].is_ready:
                if self.volume_sma[symbol].current.value * price < self.min_dollar_volume:
                    continue

            mom = self.momentum[symbol].current.value
            short_mom = self.short_mom[symbol].current.value
            prev_mom = self.prev_short_mom.get(symbol, 0)
            acceleration = short_mom - prev_mom
            self.prev_short_mom[symbol] = short_mom

            if mom > 0 and acceleration > 0:
                scores[symbol] = mom

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

        actual_n = min(self.top_n, len(scores))
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_symbols = [s for s, _ in ranked[:actual_n]]

        # EQUAL WEIGHT for maximum diversification
        weight = 1.0 / actual_n

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weight)
