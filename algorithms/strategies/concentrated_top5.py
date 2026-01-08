from AlgorithmImports import *

class ConcentratedTop5(QCAlgorithm):
    """
    Round 10 Strategy 5: Concentrated Top 5

    THESIS: More concentration in fewer stocks. Top 5 at 18% each = 90% invested.
    This maximizes exposure to winners while still having some diversification.

    WHY IT MIGHT WORK:
    - Top 5 captures the major winners (TSLA, AMD, META, etc.)
    - 5 positions = enough diversification to avoid single-stock blow-ups
    - 18% position size = significant gains from winners

    RISK FACTORS:
    - Single stock crash = 18% portfolio hit
    - Less diversification than 10-position strategies
    - Higher volatility

    Excludes: NVDA (robustness test)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Concentrated: 5 positions at 18% each
        self.num_positions = 5
        self.position_weight = 0.18

        # Universe (no NVDA)
        self.universe_tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "TSLA", "AMD", "NFLX", "ADBE", "CRM",
            "ORCL", "SHOP", "NOW", "AVGO", "QCOM",
            "COST", "HD", "TXN", "LLY", "UNH",
            "JPM", "GS", "MA", "V", "CAT", "DE"
        ]

        self.symbols = {}
        self.momentum_ind = {}
        self.sma50_ind = {}

        for ticker in self.universe_tickers:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)
            self.sma50_ind[ticker] = self.sma(symbol, 50)

        # Market regime
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

    def rebalance(self):
        if self.is_warming_up:
            return

        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            self.liquidate()
            return

        # Get candidates
        candidates = []
        for ticker in self.universe_tickers:
            if not self.momentum_ind[ticker].is_ready or not self.sma50_ind[ticker].is_ready:
                continue
            symbol = self.symbols[ticker]
            price = self.securities[symbol].price
            if not price or price <= 0:
                continue

            momentum = self.momentum_ind[ticker].current.value
            sma50 = self.sma50_ind[ticker].current.value

            if momentum > 0 and price > sma50:
                candidates.append({'ticker': ticker, 'momentum': momentum})

        candidates.sort(key=lambda x: x['momentum'], reverse=True)

        # Top 5 only
        top_tickers = [c['ticker'] for c in candidates[:self.num_positions]]

        # Liquidate non-target
        for holding in self.portfolio.Values:
            if holding.invested and holding.symbol.value not in top_tickers:
                self.liquidate(holding.symbol)

        # Equal weight
        for ticker in top_tickers:
            symbol = self.symbols[ticker]
            self.set_holdings(symbol, self.position_weight)
