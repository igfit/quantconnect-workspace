from AlgorithmImports import *

class WeeklyTieredMomentum(QCAlgorithm):
    """
    Round 10 Strategy 3: Weekly Tiered Momentum

    THESIS: Combine the best elements:
    - Weekly rebalance (from R9 - faster rotation)
    - Tiered weighting (from R8 - concentrate on winners)

    WHY IT MIGHT WORK:
    - Weekly catches momentum shifts faster
    - Tiered puts more capital in top performers
    - Best of both worlds

    RISK FACTORS:
    - Higher transaction costs from weekly rebalance
    - May over-trade in choppy markets

    Excludes: NVDA (robustness test)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Tiered weights
        self.top_tier_count = 3
        self.top_tier_weight = 0.15
        self.second_tier_count = 7
        self.second_tier_weight = 0.07

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

        # Weekly rebalance
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
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

        # Build tiered portfolio
        target_weights = {}
        total_positions = self.top_tier_count + self.second_tier_count

        for i, c in enumerate(candidates[:total_positions]):
            ticker = c['ticker']
            if i < self.top_tier_count:
                target_weights[ticker] = self.top_tier_weight
            else:
                target_weights[ticker] = self.second_tier_weight

        # Liquidate non-target
        for holding in self.portfolio.Values:
            if holding.invested and holding.symbol.value not in target_weights:
                self.liquidate(holding.symbol)

        # Rebalance
        for ticker, weight in target_weights.items():
            symbol = self.symbols[ticker]
            self.set_holdings(symbol, weight)
