from AlgorithmImports import *

class ConservativeLeverage(QCAlgorithm):
    """
    Round 10 Strategy 1: Conservative Leverage (1.15x)

    THESIS: R9 showed 1.25x leverage gave 27% CAGR but 40% DD.
    1.15x leverage should give ~30% CAGR with ~23% DD.

    WHY IT MIGHT WORK:
    - Tiered Momentum at 26.24% * 1.15 = ~30.2% CAGR
    - 19.6% DD * 1.15 = ~22.5% DD (well under 30%)
    - Small leverage, big impact on compounding

    RISK FACTORS:
    - Leverage still amplifies losses
    - Margin costs
    - May still breach 30% DD in extreme scenarios

    Excludes: NVDA (robustness test)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Conservative leverage
        self.leverage = 1.15

        # Tiered position sizing (same as successful R8 strategy)
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

        # Get candidates with positive momentum above 50 SMA
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

        # Sort by momentum
        candidates.sort(key=lambda x: x['momentum'], reverse=True)

        # Build tiered portfolio
        target_weights = {}
        total_positions = self.top_tier_count + self.second_tier_count

        for i, c in enumerate(candidates[:total_positions]):
            ticker = c['ticker']
            if i < self.top_tier_count:
                weight = self.top_tier_weight
            else:
                weight = self.second_tier_weight
            # Apply leverage
            target_weights[ticker] = weight * self.leverage

        # Liquidate positions not in target
        for holding in self.portfolio.Values:
            if holding.invested and holding.symbol.value not in target_weights:
                self.liquidate(holding.symbol)

        # Rebalance
        for ticker, weight in target_weights.items():
            symbol = self.symbols[ticker]
            self.set_holdings(symbol, weight)
