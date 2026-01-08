"""
Momentum Strategy: Diversified Small/Mid Cap Growth

GOAL: Work on larger basket of stocks, avoid mega-cap concentration
- Excludes FAANG, top semis (NVDA, AMD, AVGO)
- Focus on small/mid cap high-beta growth stocks
- 80+ stock universe for better diversification
- Max 8% per position to prevent concentration
"""

from AlgorithmImports import *


class MomentumDiversifiedGrowth(QCAlgorithm):

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
        self.top_n = 15  # More positions for diversification
        self.max_position_pct = 0.08  # Max 8% per stock
        self.use_regime_filter = True
        self.min_dollar_volume = 3_000_000  # Lower for smaller caps

        self.prev_short_mom = {}

        # DIVERSIFIED GROWTH UNIVERSE - NO MEGA-CAPS
        # Excludes: AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA, AVGO
        self.universe_tickers = [
            # Mid-cap Semis (not top 3)
            "QCOM", "MU", "AMAT", "LRCX", "KLAC", "MRVL", "ON", "TXN", "ADI",
            "SNPS", "CDNS", "MPWR", "SWKS", "QRVO", "WOLF",
            # Mid-cap Software/Cloud
            "CRM", "NOW", "INTU", "PANW", "VEEV", "WDAY", "CRWD", "DDOG",
            "ZS", "NET", "MDB", "SNOW", "OKTA", "TWLO", "HUBS", "BILL",
            # Fintech/Payments (not V/MA)
            "PYPL", "SQ", "AFRM", "SOFI", "UPST", "COIN",
            # E-commerce/Consumer
            "SHOP", "ETSY", "CHWY", "W", "PINS", "SNAP",
            # Travel/Leisure
            "BKNG", "RCL", "CCL", "MAR", "HLT", "WYNN", "LVS", "MGM",
            "ABNB", "EXPE", "UAL", "DAL", "AAL",
            # Energy (mid-cap)
            "OXY", "DVN", "SLB", "COP", "EOG", "PXD", "MRO", "APA",
            # Industrials
            "CAT", "DE", "URI", "PCAR", "CMI", "EMR", "ROK",
            # Consumer/Retail
            "NKE", "LULU", "CMG", "DECK", "SBUX", "DPZ", "YUM",
            "ULTA", "TJX", "ROST", "DG", "DLTR",
            # Biotech/Healthcare (high beta)
            "MRNA", "BNTX", "REGN", "VRTX", "BIIB", "ILMN",
            # Streaming/Media
            "NFLX", "ROKU", "SPOT", "TTD", "RBLX",
            # Finance (mid-cap)
            "GS", "MS", "SCHW", "IBKR", "HOOD",
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

        # Momentum-weighted but capped at max_position_pct
        total_mom = sum(scores[s] for s in top_symbols)
        raw_weights = {s: scores[s] / total_mom for s in top_symbols}

        # Cap weights and redistribute excess
        capped_weights = {}
        excess = 0
        uncapped_count = 0

        for s in top_symbols:
            if raw_weights[s] > self.max_position_pct:
                capped_weights[s] = self.max_position_pct
                excess += raw_weights[s] - self.max_position_pct
            else:
                capped_weights[s] = raw_weights[s]
                uncapped_count += 1

        # Redistribute excess proportionally to uncapped positions
        if uncapped_count > 0 and excess > 0:
            redistrib = excess / uncapped_count
            for s in top_symbols:
                if capped_weights[s] < self.max_position_pct:
                    capped_weights[s] = min(capped_weights[s] + redistrib, self.max_position_pct)

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, capped_weights[symbol])
