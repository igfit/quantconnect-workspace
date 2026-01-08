from AlgorithmImports import *

class SectorBalancedMomentum(QCAlgorithm):
    """
    Sector-Balanced Momentum Strategy

    THESIS: Force diversification across sectors to avoid concentration in tech.
    The 2020-2024 period was dominated by tech/AI - sector balance ensures
    the strategy isn't just a tech bet.

    EDGE:
    - Momentum effect works across all sectors
    - Sector balance reduces correlation risk
    - Market regime filter avoids bear markets

    RULES:
    - Max 2 stocks per sector
    - Pick top momentum stock from each sector that qualifies
    - Total 8-10 positions across 5+ sectors
    - Bull market filter (SPY > 200 SMA)
    - Monthly rebalancing

    TARGET: 20%+ CAGR, >0.8 Sharpe, <25% Max DD, true diversification
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Define universe by sector (3-5 top stocks per sector)
        self.sector_stocks = {
            "Technology": ["AAPL", "MSFT", "CRM", "ADBE", "ORCL"],
            "Semiconductors": ["AMD", "AVGO", "QCOM", "INTC", "MU"],  # No NVDA
            "Consumer Discretionary": ["AMZN", "TSLA", "HD", "NKE", "SBUX"],
            "Communication": ["GOOGL", "META", "NFLX", "DIS", "CMCSA"],
            "Healthcare": ["UNH", "LLY", "JNJ", "PFE", "ABBV"],
            "Financials": ["JPM", "V", "MA", "GS", "BAC"],
            "Industrials": ["CAT", "HON", "UNP", "RTX", "DE"],
            "Consumer Staples": ["COST", "PG", "KO", "PEP", "WMT"],
            "Energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
        }

        # Settings
        self.max_per_sector = 2
        self.min_sectors = 4
        self.rebalance_month = -1

        # Flatten and add all securities
        self.all_symbols = []
        self.symbol_to_sector = {}
        self.equities = {}

        for sector, stocks in self.sector_stocks.items():
            for symbol in stocks:
                self.all_symbols.append(symbol)
                self.symbol_to_sector[symbol] = sector
                equity = self.add_equity(symbol, Resolution.DAILY)
                equity.set_leverage(1.0)
                self.equities[symbol] = equity.symbol

        # SPY for regime
        spy = self.add_equity("SPY", Resolution.DAILY)
        self.spy = spy.symbol
        self.set_benchmark("SPY")

        # Indicators
        self.momentum = {}
        self.sma50 = {}

        for symbol in self.all_symbols:
            sym = self.equities[symbol]
            self.momentum[symbol] = self.momp(sym, 126)
            self.sma50[symbol] = self.sma(sym, 50)

        self.spy_sma200 = self.sma(self.spy, 200)
        self.spy_momentum = self.momp(self.spy, 126)

        # Monthly rebalancing
        self.schedule.on(
            self.date_rules.month_start(5),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_warm_up(timedelta(days=210))

    def rebalance(self):
        if self.is_warming_up:
            return

        if self.time.month == self.rebalance_month:
            return
        self.rebalance_month = self.time.month

        # Market regime check
        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        spy_sma = self.spy_sma200.current.value

        if spy_price < spy_sma:
            self.log(f"BEAR: SPY < 200 SMA. Liquidating.")
            self.liquidate()
            return

        spy_mom = self.spy_momentum.current.value if self.spy_momentum.is_ready else 0

        # Score stocks by sector
        sector_candidates = {sector: [] for sector in self.sector_stocks.keys()}

        for symbol in self.all_symbols:
            sym = self.equities[symbol]
            sector = self.symbol_to_sector[symbol]

            if not self.securities[sym].is_tradable:
                continue

            if not self.momentum[symbol].is_ready or not self.sma50[symbol].is_ready:
                continue

            price = self.securities[sym].price
            sma_value = self.sma50[symbol].current.value
            mom_value = self.momentum[symbol].current.value

            # Qualify: above SMA, positive momentum, beats SPY
            if price > sma_value and mom_value > 0 and mom_value > spy_mom * 0.5:  # Looser filter
                sector_candidates[sector].append((symbol, mom_value))

        # Sort each sector by momentum
        for sector in sector_candidates:
            sector_candidates[sector].sort(key=lambda x: x[1], reverse=True)

        # Select top stocks from each qualifying sector
        selected = []
        sector_picks = {}

        # First pass: get best from each sector
        for sector, candidates in sector_candidates.items():
            if len(candidates) > 0:
                top_picks = candidates[:self.max_per_sector]
                sector_picks[sector] = top_picks
                selected.extend([s[0] for s in top_picks])

        # Ensure minimum sector diversification
        sectors_represented = len([s for s in sector_picks if len(sector_picks[s]) > 0])

        if sectors_represented < self.min_sectors:
            self.log(f"Only {sectors_represented} sectors qualify. Going to cash.")
            self.liquidate()
            return

        self.log(f"Selected from {sectors_represented} sectors: {selected}")

        # Equal weight
        if len(selected) == 0:
            self.liquidate()
            return

        weight = 1.0 / len(selected)

        # Liquidate non-selected
        for symbol in self.all_symbols:
            sym = self.equities[symbol]
            if symbol not in selected and self.portfolio[sym].invested:
                self.liquidate(sym)

        # Allocate
        for symbol in selected:
            sym = self.equities[symbol]
            self.set_holdings(sym, weight)

    def on_data(self, data):
        pass
