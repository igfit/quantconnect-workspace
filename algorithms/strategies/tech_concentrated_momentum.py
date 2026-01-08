from AlgorithmImports import *

class TechConcentratedMomentum(QCAlgorithm):
    """
    Round 9 Strategy 3: Tech Concentrated Momentum

    THESIS: Tech sector dramatically outperformed 2020-2024. Concentrate
    60% in tech stocks, 40% in other sectors for higher returns.

    WHY IT MIGHT WORK:
    - Tech had 5 of top 10 performers (TSLA, AMD, META, NFLX, SHOP)
    - Without NVDA, tech still dominates returns
    - 60/40 split gives concentration while some diversification
    - Still use momentum within each group

    RISK FACTORS:
    - Tech sector rotation risk (2022 was brutal)
    - Correlation within tech is high
    - If tech underperforms, whole strategy suffers

    Excludes: NVDA (robustness test)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Allocation split
        self.tech_weight = 0.60  # 60% to tech
        self.other_weight = 0.40  # 40% to other sectors

        # Number of positions in each group
        self.tech_positions = 6    # 10% each
        self.other_positions = 4   # 10% each

        # Tech universe (no NVDA)
        self.tech_tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "AMD", "NFLX", "ADBE", "CRM", "ORCL",
            "SHOP", "NOW", "AVGO", "QCOM", "TXN"
        ]

        # Non-tech universe
        self.other_tickers = [
            "TSLA",  # Consumer discretionary (auto)
            "COST", "HD",  # Consumer staples/discretionary
            "LLY", "UNH", "ABBV",  # Healthcare
            "JPM", "GS", "MA", "V",  # Financials
            "CAT", "DE", "HON"  # Industrials
        ]

        self.symbols = {}
        self.momentum_ind = {}

        all_tickers = self.tech_tickers + self.other_tickers
        for ticker in all_tickers:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)

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

    def get_top_momentum(self, tickers, n):
        """Get top N tickers by momentum from a list"""
        scores = {}
        for ticker in tickers:
            if not self.momentum_ind[ticker].is_ready:
                continue
            symbol = self.symbols[ticker]
            if not self.securities[symbol].price or self.securities[symbol].price <= 0:
                continue
            scores[ticker] = self.momentum_ind[ticker].current.value

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [t[0] for t in ranked[:n]]

    def rebalance(self):
        if self.is_warming_up:
            return

        # Check market regime
        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            self.liquidate()
            return

        # Get top momentum in each group
        top_tech = self.get_top_momentum(self.tech_tickers, self.tech_positions)
        top_other = self.get_top_momentum(self.other_tickers, self.other_positions)

        # Calculate weights
        target_weights = {}
        tech_per_position = self.tech_weight / len(top_tech) if top_tech else 0
        other_per_position = self.other_weight / len(top_other) if top_other else 0

        for ticker in top_tech:
            target_weights[ticker] = tech_per_position
        for ticker in top_other:
            target_weights[ticker] = other_per_position

        # Liquidate positions not in target
        for holding in self.portfolio.Values:
            if holding.invested and holding.symbol.value not in target_weights:
                self.liquidate(holding.symbol)

        # Rebalance
        for ticker, weight in target_weights.items():
            symbol = self.symbols[ticker]
            self.set_holdings(symbol, weight)

        self.debug(f"{self.time.date()}: Tech={len(top_tech)} at {tech_per_position:.1%}, Other={len(top_other)} at {other_per_position:.1%}")
