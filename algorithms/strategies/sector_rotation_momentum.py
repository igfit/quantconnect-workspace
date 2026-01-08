from AlgorithmImports import *

class SectorRotationMomentum(QCAlgorithm):
    """
    Sector Rotation Momentum Strategy

    Thesis: Sectors rotate based on economic cycles. Tech leads in growth periods,
    financials benefit from rising rates, energy from inflation. Rotating between
    top-performing sectors captures these regime shifts.

    Rules:
    - Universe: 9 sector ETFs (XLK, XLF, XLV, XLY, XLI, XLE, XLC, XLB, XLRE)
    - Entry: Buy top 3 sectors by 3-month momentum
    - Exit: Monthly rebalance - sell sectors no longer in top 3
    - Filter: SPY > 200 SMA (bull market) - go to TLT in bear market
    - Position size: Equal weight across top 3 sectors

    Edge: Diversified across sectors, not dependent on single stocks like NVDA.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Sector ETFs universe
        self.sectors = [
            "XLK",  # Technology
            "XLF",  # Financials
            "XLV",  # Healthcare
            "XLY",  # Consumer Discretionary
            "XLI",  # Industrials
            "XLE",  # Energy
            "XLC",  # Communication Services
            "XLB",  # Materials
            "XLRE", # Real Estate
        ]

        # Add sector ETFs
        self.sector_symbols = {}
        for ticker in self.sectors:
            self.sector_symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol

        # Market regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Safe haven for bear markets
        self.tlt = self.add_equity("TLT", Resolution.DAILY).symbol

        # Momentum indicators (63 trading days = ~3 months)
        self.momentum_ind = {}
        for ticker, symbol in self.sector_symbols.items():
            self.momentum_ind[ticker] = self.momp(symbol, 63, Resolution.DAILY)

        # Number of sectors to hold
        self.top_n = 3

        # Track current holdings
        self.current_sectors = []

        # Set benchmark
        self.set_benchmark("SPY")

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start(1),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        # Warmup period
        self.set_warm_up(210, Resolution.DAILY)

    def rebalance(self):
        if self.is_warming_up:
            return

        # Check market regime
        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            # Bear market - rotate to bonds
            self.liquidate_sectors()
            if not self.portfolio[self.tlt].invested:
                self.set_holdings(self.tlt, 0.95)
                self.debug(f"{self.time.date()}: Bear market - rotating to TLT")
            return

        # Bull market - liquidate TLT if held
        if self.portfolio[self.tlt].invested:
            self.liquidate(self.tlt)

        # Calculate momentum for all sectors
        momentum_scores = {}
        for ticker, symbol in self.sector_symbols.items():
            if self.momentum_ind[ticker].is_ready:
                momentum_scores[ticker] = self.momentum_ind[ticker].current.value

        if len(momentum_scores) < self.top_n:
            return

        # Rank by momentum and select top N
        sorted_sectors = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        top_sectors = [ticker for ticker, _ in sorted_sectors[:self.top_n]]

        # Log selection
        self.debug(f"{self.time.date()}: Top sectors: {top_sectors}")
        for ticker, score in sorted_sectors[:self.top_n]:
            self.debug(f"  {ticker}: {score:.2f}%")

        # Liquidate sectors no longer in top N
        for ticker in self.current_sectors:
            if ticker not in top_sectors:
                self.liquidate(self.sector_symbols[ticker])

        # Equal weight across top sectors
        weight = 0.95 / self.top_n
        for ticker in top_sectors:
            self.set_holdings(self.sector_symbols[ticker], weight)

        self.current_sectors = top_sectors

    def liquidate_sectors(self):
        """Liquidate all sector positions"""
        for ticker, symbol in self.sector_symbols.items():
            if self.portfolio[symbol].invested:
                self.liquidate(symbol)
        self.current_sectors = []

    def on_data(self, data):
        pass
