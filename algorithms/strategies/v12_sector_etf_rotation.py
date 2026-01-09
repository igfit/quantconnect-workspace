"""
v12 SECTOR ETF ROTATION Strategy

Instead of picking individual stocks, rotate between sector ETFs.
This is more robust and doesn't rely on stock-specific selection.

Hold top 3 sector ETFs by momentum.
"""

from AlgorithmImports import *


class V12SectorETFRotation(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2019, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(lambda security: security.set_slippage_model(
            ConstantSlippageModel(0.001)
        ))
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE)

        # Sector ETFs
        self.sector_etfs = [
            "XLK",  # Technology
            "XLY",  # Consumer Discretionary
            "XLV",  # Healthcare
            "XLC",  # Communication Services
            "XLF",  # Financials
            "XLI",  # Industrials
            "XLE",  # Energy
            "XLB",  # Materials
            "XLP",  # Consumer Staples
            "QQQ",  # Tech-heavy Nasdaq
        ]

        self.etf_symbols = {}
        self.etf_momentum = {}

        for etf in self.sector_etfs:
            symbol = self.add_equity(etf, Resolution.DAILY).symbol
            self.etf_symbols[etf] = symbol
            self.etf_momentum[etf] = self.roc(symbol, 126, Resolution.DAILY)

        # Regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma_200 = self.sma(self.spy, 200, Resolution.DAILY)

        self.top_n = 3  # Hold top 3 sectors

        self.set_warm_up(140, Resolution.DAILY)

        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.maybe_rebalance
        )

        self.rebalance_week = 0
        self.set_benchmark("SPY")

    def maybe_rebalance(self):
        self.rebalance_week += 1
        if self.rebalance_week % 4 == 0:  # Monthly rebalance
            self.rebalance()

    def rebalance(self):
        if self.is_warming_up:
            return

        # Regime check
        if not self.spy_sma_200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        if spy_price < self.spy_sma_200.current.value:
            self.liquidate()
            return

        # Rank ETFs by momentum
        scores = {}
        for etf in self.sector_etfs:
            if self.etf_momentum[etf].is_ready:
                mom = self.etf_momentum[etf].current.value
                if mom > 0:  # Only positive momentum
                    scores[etf] = mom

        if len(scores) < 2:
            self.liquidate()
            return

        # Select top N
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_etfs = [etf for etf, _ in ranked[:self.top_n]]

        # Equal weight
        target_weight = 1.0 / len(top_etfs)

        # Exit positions not in top
        for holding in self.portfolio.values():
            if holding.invested:
                etf_name = str(holding.symbol.value)
                if etf_name not in top_etfs and etf_name != "SPY":
                    self.liquidate(holding.symbol)

        # Enter new positions
        for etf in top_etfs:
            symbol = self.etf_symbols[etf]
            self.set_holdings(symbol, target_weight)
