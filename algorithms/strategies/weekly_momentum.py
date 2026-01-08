from AlgorithmImports import *

class WeeklyMomentum(QCAlgorithm):
    """
    Round 9 Strategy 2: Weekly Momentum Rebalance

    THESIS: Weekly rebalancing captures momentum faster than monthly,
    allowing quicker rotation into winners and out of losers.

    WHY IT MIGHT WORK:
    - Momentum is strongest over 3-12 month formation, but can shift within months
    - Weekly rebalance = 4x more opportunities to rotate
    - Catch breakouts earlier, exit reversals sooner
    - More responsive to regime changes

    RISK FACTORS:
    - Higher transaction costs (4x more trades)
    - More whipsaws in choppy markets
    - May over-trade during volatile periods

    Excludes: NVDA (robustness test)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Position sizing - 10 positions at 10% each
        self.num_positions = 10
        self.position_weight = 0.10

        # Quality mega-cap universe (no NVDA)
        self.universe_tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "TSLA", "AMD", "NFLX", "ADBE", "CRM",
            "ORCL", "SHOP", "NOW", "AVGO", "QCOM",
            "COST", "HD", "TXN", "LLY", "UNH",
            "JPM", "GS", "MA", "V", "CAT", "DE"
        ]

        self.symbols = {}
        self.momentum_ind = {}

        for ticker in self.universe_tickers:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)  # 6-month momentum

        # Market regime - SPY
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)

        # Weekly rebalance (every Monday)
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_warm_up(210, Resolution.DAILY)

    def rebalance(self):
        if self.is_warming_up:
            return

        # Check market regime
        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            # Bear market - go to cash
            self.liquidate()
            return

        # Calculate momentum scores
        momentum_scores = {}
        for ticker in self.universe_tickers:
            symbol = self.symbols[ticker]
            if not self.momentum_ind[ticker].is_ready:
                continue
            if not self.securities[symbol].price or self.securities[symbol].price <= 0:
                continue
            momentum_scores[ticker] = self.momentum_ind[ticker].current.value

        # Rank by momentum - top N
        ranked = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        top_tickers = [t[0] for t in ranked[:self.num_positions]]

        # Liquidate positions not in top
        for holding in self.portfolio.Values:
            if holding.invested and holding.symbol.value not in top_tickers:
                self.liquidate(holding.symbol)

        # Equal weight positions
        for ticker in top_tickers:
            symbol = self.symbols[ticker]
            self.set_holdings(symbol, self.position_weight)
