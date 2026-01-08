from AlgorithmImports import *

class SignalSectorRotation(QCAlgorithm):
    """
    SIGNAL-DRIVEN Strategy 1: Sector ETF Momentum Rotation

    THESIS: The momentum SIGNAL is the edge, not stock selection.
    By trading sector ETFs instead of stocks, no single name can dominate.

    WHY THIS IS SIGNAL-DRIVEN:
    - 11 sector ETFs = diversified, no single stock dominance
    - Same momentum signal applied equally to all sectors
    - Returns should be spread across sectors, not concentrated

    Signal: 3-month momentum, buy top 3 sectors, equal weight
    Regime: SPY > 200 SMA
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # 11 S&P Sector ETFs
        self.sector_etfs = [
            "XLK",  # Technology
            "XLF",  # Financials
            "XLV",  # Healthcare
            "XLE",  # Energy
            "XLI",  # Industrials
            "XLY",  # Consumer Discretionary
            "XLP",  # Consumer Staples
            "XLU",  # Utilities
            "XLB",  # Materials
            "XLRE", # Real Estate
            "XLC",  # Communication Services
        ]

        self.symbols = {}
        self.momentum_ind = {}

        for etf in self.sector_etfs:
            symbol = self.add_equity(etf, Resolution.DAILY).symbol
            self.symbols[etf] = symbol
            self.momentum_ind[etf] = self.momp(symbol, 63, Resolution.DAILY)

        # Market regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_warm_up(210, Resolution.DAILY)

        # How many sectors to hold
        self.top_n = 3
        self.weight_per_sector = 1.0 / self.top_n  # Equal weight

    def rebalance(self):
        if self.is_warming_up:
            return

        if not self.spy_sma200.is_ready:
            return

        # Market regime check
        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            self.liquidate()
            return

        # Rank sectors by momentum
        sector_momentum = []
        for etf in self.sector_etfs:
            if not self.momentum_ind[etf].is_ready:
                continue
            mom = self.momentum_ind[etf].current.value
            if mom > 0:  # Only positive momentum
                sector_momentum.append({'etf': etf, 'momentum': mom})

        sector_momentum.sort(key=lambda x: x['momentum'], reverse=True)

        # Select top N sectors, equal weight
        target_holdings = {}
        for sector in sector_momentum[:self.top_n]:
            target_holdings[sector['etf']] = self.weight_per_sector

        # Liquidate non-targets
        for holding in self.portfolio.Values:
            if holding.invested and holding.symbol.value not in target_holdings:
                self.liquidate(holding.symbol)

        # Rebalance to equal weight
        for etf, weight in target_holdings.items():
            symbol = self.symbols[etf]
            self.set_holdings(symbol, weight)
