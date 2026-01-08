"""
Momentum Strategy: Sector Diversified

ITERATION: Test if sector diversification improves risk-adjusted returns
- Max 2 stocks per sector
- Forces diversification across sectors
- Hypothesis: Lower correlation, lower drawdown, more stable returns
"""

from AlgorithmImports import *


class MomentumSectorDiversified(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # PARAMETERS
        self.lookback_days = 126
        self.accel_period = 21
        self.top_n = 10
        self.max_per_sector = 2  # Diversification limit
        self.use_regime_filter = True
        self.min_dollar_volume = 5_000_000

        self.prev_short_mom = {}

        # Sector classification
        self.sector_map = {
            # Semiconductors
            "NVDA": "Semi", "AMD": "Semi", "AVGO": "Semi", "QCOM": "Semi", "MU": "Semi",
            "AMAT": "Semi", "LRCX": "Semi", "KLAC": "Semi", "MRVL": "Semi", "ON": "Semi",
            "TXN": "Semi", "ADI": "Semi", "SNPS": "Semi", "CDNS": "Semi", "ASML": "Semi",
            # Software/Cloud
            "CRM": "Software", "ADBE": "Software", "NOW": "Software", "INTU": "Software",
            "PANW": "Software", "VEEV": "Software", "WDAY": "Software",
            # Payments
            "V": "Payments", "MA": "Payments", "PYPL": "Payments", "SQ": "Payments",
            # E-commerce
            "AMZN": "Ecomm", "SHOP": "Ecomm",
            # Travel/Leisure
            "BKNG": "Travel", "RCL": "Travel", "CCL": "Travel", "MAR": "Travel",
            "HLT": "Travel", "WYNN": "Travel",
            # Energy
            "XOM": "Energy", "CVX": "Energy", "OXY": "Energy", "DVN": "Energy",
            "SLB": "Energy", "COP": "Energy",
            # Industrials
            "CAT": "Industrial", "DE": "Industrial", "URI": "Industrial", "BA": "Industrial",
            # Consumer/EV
            "TSLA": "Consumer", "NKE": "Consumer", "LULU": "Consumer", "CMG": "Consumer", "DECK": "Consumer",
            # Finance
            "GS": "Finance", "MS": "Finance",
            # Streaming
            "NFLX": "Stream", "ROKU": "Stream",
        }

        self.universe_tickers = list(self.sector_map.keys())

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma = self.sma(self.spy, 200, Resolution.DAILY)

        self.symbols = []
        self.symbol_to_ticker = {}
        for ticker in self.universe_tickers:
            try:
                equity = self.add_equity(ticker, Resolution.DAILY)
                self.symbols.append(equity.symbol)
                self.symbol_to_ticker[equity.symbol] = ticker
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

    def get_sector(self, symbol):
        ticker = self.symbol_to_ticker.get(symbol, "")
        return self.sector_map.get(ticker, "Other")

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

        if len(scores) < 5:
            # Fallback
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

        # Rank by momentum, then apply sector diversification
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        top_symbols = []
        sector_counts = {}

        for symbol, _ in ranked:
            sector = self.get_sector(symbol)
            current_count = sector_counts.get(sector, 0)

            if current_count < self.max_per_sector:
                top_symbols.append(symbol)
                sector_counts[sector] = current_count + 1

            if len(top_symbols) >= self.top_n:
                break

        if len(top_symbols) < 5:
            return

        # Momentum-weighted
        total_mom = sum(scores[s] for s in top_symbols)
        weights = {s: scores[s] / total_mom for s in top_symbols}

        for holding in self.portfolio.values():
            if holding.invested and holding.symbol not in top_symbols:
                self.liquidate(holding.symbol)

        for symbol in top_symbols:
            self.set_holdings(symbol, weights[symbol])
