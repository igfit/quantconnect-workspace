from AlgorithmImports import *

class SectorBalancedMomentum(QCAlgorithm):
    """
    Sector-Balanced Momentum - Force Diversification Across Sectors

    THESIS:
    2020-2024 was dominated by tech. Pure momentum concentrates in one sector,
    creating hidden risk. By forcing 2 stocks per sector, we ensure true
    diversification that protects in sector rotations.

    WHY IT SHOULD WORK:
    1. Sector rotation: Different sectors lead at different times
    2. Hidden correlation: Tech stocks move together (AAPL, MSFT, GOOGL all fell in 2022)
    3. Momentum within sectors: Each sector has winners
    4. Forced balance: Can't over-concentrate in one sector

    WHY DD SHOULD BE LOW:
    - 2022: Tech fell 30%+, but Energy rose 50%+ → sector balance helped
    - Healthcare/Staples are defensive → provide ballast
    - No single sector > 20% of portfolio

    SECTORS (8 sectors × 2 stocks = 16 positions):
    - Technology, Semiconductors, Consumer Internet
    - Finance, Healthcare, Industrial
    - Energy, Consumer

    TARGET: 18-22% CAGR, <25% DD, Sharpe > 0.8

    EXCLUSIONS: No NVDA (robustness test)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Define sectors with stock lists (NO NVDA)
        self.sectors = {
            'Tech': ["AAPL", "MSFT", "GOOGL", "ORCL", "CRM", "ADBE"],
            'Semis': ["AMD", "AVGO", "QCOM", "TXN", "AMAT", "MU", "INTC"],
            'Internet': ["AMZN", "META", "NFLX", "UBER", "SHOP", "ABNB"],
            'Finance': ["JPM", "GS", "V", "MA", "BAC", "AXP"],
            'Healthcare': ["UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK"],
            'Industrial': ["CAT", "DE", "HON", "UPS", "GE", "RTX"],
            'Energy': ["XOM", "CVX", "COP", "SLB", "EOG"],
            'Consumer': ["TSLA", "HD", "COST", "WMT", "NKE", "SBUX"]
        }

        # Flatten and add all stocks
        self.all_tickers = []
        self.ticker_to_sector = {}
        for sector, tickers in self.sectors.items():
            for ticker in tickers:
                self.all_tickers.append(ticker)
                self.ticker_to_sector[ticker] = sector

        self.symbols = {}
        for ticker in self.all_tickers:
            try:
                self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol
            except:
                pass

        # Market regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Momentum indicators
        self.momentum_ind = {}
        for ticker, symbol in self.symbols.items():
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)

        # Trend filter
        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        # 2 stocks per sector
        self.stocks_per_sector = 2

        self.set_benchmark("SPY")

        self.schedule.on(
            self.date_rules.month_start(1),
            self.time_rules.after_market_open(self.spy, 30),
            self.rebalance
        )

        self.set_warm_up(210, Resolution.DAILY)

    def rebalance(self):
        if self.is_warming_up:
            return

        if not self.spy_sma200.is_ready:
            return

        # Regime filter
        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            self.liquidate()
            self.debug(f"{self.time.date()}: BEAR MARKET - Going to cash")
            return

        # Group candidates by sector
        sector_candidates = {sector: [] for sector in self.sectors.keys()}

        for ticker, symbol in self.symbols.items():
            if ticker not in self.momentum_ind or ticker not in self.sma50_ind:
                continue
            if not self.momentum_ind[ticker].is_ready or not self.sma50_ind[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma50 = self.sma50_ind[ticker].current.value
            momentum = self.momentum_ind[ticker].current.value

            # Only consider stocks in uptrend
            if momentum > 0 and price > sma50:
                sector = self.ticker_to_sector.get(ticker)
                if sector:
                    sector_candidates[sector].append({
                        'ticker': ticker,
                        'symbol': symbol,
                        'momentum': momentum
                    })

        # Select top N from each sector
        selected_stocks = []
        for sector, candidates in sector_candidates.items():
            if len(candidates) > 0:
                sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
                selected_stocks.extend(sorted_candidates[:self.stocks_per_sector])

        if len(selected_stocks) < 4:
            self.liquidate()
            return

        # Liquidate positions not selected
        selected_tickers = [s['ticker'] for s in selected_stocks]
        for ticker, symbol in self.symbols.items():
            if ticker not in selected_tickers and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Equal weight all selected stocks
        weight = 0.95 / len(selected_stocks)
        for stock in selected_stocks:
            self.set_holdings(stock['symbol'], weight)

        # Log sector breakdown
        sector_count = {}
        for stock in selected_stocks:
            sector = self.ticker_to_sector[stock['ticker']]
            sector_count[sector] = sector_count.get(sector, 0) + 1
        self.debug(f"{self.time.date()}: {len(selected_stocks)} positions, Sectors: {sector_count}")

    def on_data(self, data):
        pass
