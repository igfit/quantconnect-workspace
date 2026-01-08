from AlgorithmImports import *

class BroadEqualWeightMomentum(QCAlgorithm):
    """
    Broad Equal Weight Momentum - 20 Positions for Diversification

    THESIS:
    Concentration creates single-stock risk. Holding 20 positions instead of 3
    diversifies away idiosyncratic risk while still capturing momentum alpha.

    WHY IT SHOULD WORK:
    1. Diversification: 20 positions means no single stock > 5% of portfolio
    2. Momentum persists: Academic research shows 6-12 month momentum works
    3. Regime filter: SPY > 200 SMA avoids bear market losses (2022)
    4. Quality universe: Only liquid, established companies

    WHY DD SHOULD BE LOW:
    - Individual stock crashes (like INTC -50%) only impact 5% of portfolio
    - Regime filter exits before major drawdowns
    - Broader diversification smooths returns

    TARGET: 20-25% CAGR, <25% DD, Sharpe > 0.8

    EXCLUSIONS: No NVDA (robustness test)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Broad universe - 50 quality stocks across sectors (NO NVDA)
        self.tickers = [
            # Tech (ex-NVDA)
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "CRM", "ADBE", "ORCL", "CSCO", "INTC",
            # Semiconductors (ex-NVDA)
            "AMD", "AVGO", "QCOM", "TXN", "AMAT", "LRCX", "MU",
            # Consumer/Internet
            "TSLA", "NFLX", "UBER", "SHOP", "ABNB", "BKNG",
            # Finance
            "JPM", "BAC", "GS", "MS", "V", "MA", "AXP",
            # Healthcare
            "UNH", "JNJ", "PFE", "ABBV", "MRK", "LLY",
            # Industrial/Energy
            "CAT", "DE", "HON", "UPS", "XOM", "CVX",
            # Consumer Staples/Other
            "PG", "KO", "PEP", "WMT", "COST", "HD", "LOW"
        ]

        self.symbols = {}
        for ticker in self.tickers:
            try:
                self.symbols[ticker] = self.add_equity(ticker, Resolution.DAILY).symbol
            except:
                pass

        # Market regime filter
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)

        # Momentum indicators (126 days = 6 months)
        self.momentum_ind = {}
        for ticker, symbol in self.symbols.items():
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)

        # 50-day SMA for trend filter
        self.sma50_ind = {}
        for ticker, symbol in self.symbols.items():
            self.sma50_ind[ticker] = self.sma(symbol, 50, Resolution.DAILY)

        # KEY PARAMETER: 20 positions for diversification
        self.top_n = 20

        self.set_benchmark("SPY")

        # Monthly rebalance
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

        # Regime filter: only invest in bull markets
        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            self.liquidate()
            self.debug(f"{self.time.date()}: BEAR MARKET - Going to cash")
            return

        # Select candidates: positive momentum + price > 50 SMA
        candidates = []
        for ticker, symbol in self.symbols.items():
            if ticker not in self.momentum_ind or ticker not in self.sma50_ind:
                continue
            if not self.momentum_ind[ticker].is_ready or not self.sma50_ind[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            sma50 = self.sma50_ind[ticker].current.value
            momentum = self.momentum_ind[ticker].current.value

            # Filter: positive momentum AND price above 50 SMA
            if momentum > 0 and price > sma50:
                candidates.append({
                    'ticker': ticker,
                    'symbol': symbol,
                    'momentum': momentum
                })

        if len(candidates) < 5:
            self.debug(f"{self.time.date()}: Only {len(candidates)} candidates, staying in cash")
            self.liquidate()
            return

        # Sort by momentum, take top N
        sorted_candidates = sorted(candidates, key=lambda x: x['momentum'], reverse=True)
        top_stocks = sorted_candidates[:min(self.top_n, len(sorted_candidates))]

        # Liquidate positions not in top stocks
        top_tickers = [s['ticker'] for s in top_stocks]
        for ticker, symbol in self.symbols.items():
            if ticker not in top_tickers and self.portfolio[symbol].invested:
                self.liquidate(symbol)

        # Equal weight positions (diversified)
        weight = 0.95 / len(top_stocks)
        for stock in top_stocks:
            self.set_holdings(stock['symbol'], weight)

        self.debug(f"{self.time.date()}: Holding {len(top_stocks)} positions at {weight:.1%} each")

    def on_data(self, data):
        pass
