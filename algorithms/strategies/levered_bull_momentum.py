from AlgorithmImports import *

class LeveredBullMomentum(QCAlgorithm):
    """
    Round 9 Strategy 1: Levered Bull Momentum

    THESIS: Use 1.25x leverage in confirmed bull markets to boost returns
    without excessive drawdown.

    WHY IT MIGHT WORK:
    - Tiered Momentum hit 26.24% CAGR at 1.0x
    - 1.25x leverage could push to 32.8% CAGR
    - Leverage only in bull markets (SPY > 200 SMA) limits downside
    - Max DD should be ~1.25 * 19.6% = 24.5% (still under 30%)

    RISK FACTORS:
    - Leverage amplifies losses in whipsaws around 200 SMA
    - Margin costs eat into returns
    - 2022 bear market could have larger DD

    Excludes: NVDA (robustness test)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Leverage settings
        self.bull_leverage = 1.25  # 125% exposure in bull market
        self.bear_leverage = 0.0   # Cash in bear market

        # Tiered position sizing (same as R8 Tiered Momentum)
        self.top_tier_count = 3
        self.top_tier_weight = 0.15
        self.second_tier_count = 7
        self.second_tier_weight = 0.07

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

        # Check market regime
        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            # Bear market - go to cash
            self.liquidate()
            self.debug(f"{self.time.date()}: Bear market - all cash")
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

        # Rank by momentum
        ranked = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)

        # Build target portfolio with tiered weights
        target_weights = {}
        total_positions = self.top_tier_count + self.second_tier_count

        for i, (ticker, score) in enumerate(ranked[:total_positions]):
            if i < self.top_tier_count:
                weight = self.top_tier_weight
            else:
                weight = self.second_tier_weight
            # Apply leverage
            target_weights[ticker] = weight * self.bull_leverage

        # Liquidate positions not in target
        for holding in self.portfolio.Values:
            if holding.invested and holding.symbol.value not in target_weights:
                self.liquidate(holding.symbol)

        # Rebalance to targets
        for ticker, weight in target_weights.items():
            symbol = self.symbols[ticker]
            self.set_holdings(symbol, weight)

        self.debug(f"{self.time.date()}: Bull market - {len(target_weights)} positions at {self.bull_leverage}x")
