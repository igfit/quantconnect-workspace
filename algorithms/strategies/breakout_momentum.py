from AlgorithmImports import *

class BreakoutMomentum(QCAlgorithm):
    """
    Round 9 Strategy 4: Breakout Momentum

    THESIS: Only buy stocks making new 52-week highs. Breakouts to new highs
    indicate strong institutional buying and momentum continuation.

    WHY IT MIGHT WORK:
    - New highs = no overhead supply (no trapped longs waiting to sell)
    - Institutional algorithms trigger on breakouts
    - Momentum is strongest at new highs
    - Filters out mean-reverting stocks

    RISK FACTORS:
    - Fewer buying opportunities (may miss early moves)
    - Buying at highs feels uncomfortable
    - Breakouts can fail (false breakouts)

    Excludes: NVDA (robustness test)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Position sizing
        self.max_positions = 8
        self.position_weight = 0.12  # ~96% invested

        # Universe (no NVDA)
        self.universe_tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "TSLA", "AMD", "NFLX", "ADBE", "CRM",
            "ORCL", "SHOP", "NOW", "AVGO", "QCOM",
            "COST", "HD", "TXN", "LLY", "UNH",
            "JPM", "GS", "MA", "V", "CAT", "DE"
        ]

        self.symbols = {}
        self.max_52w = {}  # Track 52-week highs
        self.momentum_ind = {}

        for ticker in self.universe_tickers:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.max_52w[ticker] = self.MAX(symbol, 252)  # 252 trading days
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)

        # Market regime
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)

        # Weekly check for breakouts
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_warm_up(260, Resolution.DAILY)

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

        # Find stocks at or near 52-week highs
        breakout_candidates = []

        for ticker in self.universe_tickers:
            symbol = self.symbols[ticker]
            if not self.max_52w[ticker].is_ready or not self.momentum_ind[ticker].is_ready:
                continue

            price = self.securities[symbol].price
            if not price or price <= 0:
                continue

            high_52w = self.max_52w[ticker].current.value

            # Within 3% of 52-week high = breakout candidate
            if price >= high_52w * 0.97:
                momentum = self.momentum_ind[ticker].current.value
                breakout_candidates.append((ticker, momentum))

        # Sort by momentum, take top positions
        breakout_candidates.sort(key=lambda x: x[1], reverse=True)
        top_tickers = [t[0] for t in breakout_candidates[:self.max_positions]]

        # Liquidate positions not in breakout list
        for holding in self.portfolio.Values:
            if holding.invested and holding.symbol.value not in top_tickers:
                self.liquidate(holding.symbol)

        # Size positions
        if top_tickers:
            weight = min(self.position_weight, 1.0 / len(top_tickers))
            for ticker in top_tickers:
                symbol = self.symbols[ticker]
                self.set_holdings(symbol, weight)

        self.debug(f"{self.time.date()}: {len(top_tickers)} breakout positions")
