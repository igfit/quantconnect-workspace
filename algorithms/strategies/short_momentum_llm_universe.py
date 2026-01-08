from AlgorithmImports import *

class ShortMomentumLLMUniverse(QCAlgorithm):
    """
    Short Momentum + 1.15x Leverage with LLM-Generated Universe

    THESIS: Use systematically generated universe (Quant + Claude Opus 4.5 Qual)
    instead of hand-picked winners to reduce survivorship bias.

    Universe Selection (24 stocks):
    - Phase 1: Quant filters (market cap, margins, growth, ROE, debt)
    - Phase 2: LLM qualitative analysis (moat, tailwind, management, disruption risk)
    - Phase 3: Composite scoring (40% quant + 40% qual + 20% momentum)

    Strategy:
    - 3-month momentum ranking
    - Top 3 at 15%, next 7 at 7%
    - 1.15x leverage
    - SPY > 200 SMA regime filter
    - Monthly rebalance

    Key Changes vs Original:
    - Added: PANW, CRWD, AMAT, NOW, INTU, HON, GE, NVDA
    - Removed: TSLA, AMD, CRM, ORCL, SHOP, TXN, UNH, COST, HD
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        self.leverage = 1.15

        # Tiered weights
        self.top_tier_count = 3
        self.top_tier_weight = 0.15
        self.second_tier_count = 7
        self.second_tier_weight = 0.07

        # LLM-Generated Universe (ranked by composite score)
        # Generated 2025-01-08 using Claude Opus 4.5
        self.universe_tickers = [
            "NVDA",   # 0.834 - CUDA ecosystem, tailwind 10/10
            "PANW",   # 0.764 - Cybersecurity platform
            "MSFT",   # 0.760 - Azure + OpenAI
            "V",      # 0.754 - Payment network
            "AVGO",   # 0.752 - AI networking ASICs
            "LLY",    # 0.734 - GLP-1 obesity drugs
            "ADBE",   # 0.697 - Creative suite
            "AMAT",   # 0.690 - Semi equipment
            "META",   # 0.673 - 3B+ user network
            "CRWD",   # 0.668 - AI cybersecurity
            "NOW",    # 0.646 - Enterprise workflow
            "GOOGL",  # 0.634 - Search monopoly
            "QCOM",   # 0.617 - Wireless IP
            "CAT",    # 0.611 - Dealer network
            "INTU",   # 0.606 - TurboTax lock-in
            "DE",     # 0.602 - Precision ag
            "MA",     # 0.600 - Payment duopoly
            "AMZN",   # 0.591 - AWS + logistics
            "HON",    # 0.564 - Aerospace/building
            "GE",     # 0.529 - Jet engine duopoly
            "JPM",    # 0.522 - Banking scale
            "NFLX",   # 0.516 - Content library
            "AAPL",   # 0.507 - Ecosystem lock-in
            "GS",     # 0.394 - Investment bank
        ]

        self.symbols = {}
        self.momentum_ind = {}
        self.sma50_ind = {}

        for ticker in self.universe_tickers:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            # 3-month momentum
            self.momentum_ind[ticker] = self.momp(symbol, 63, Resolution.DAILY)
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

        # Build tiered portfolio with leverage
        target_weights = {}
        total_positions = self.top_tier_count + self.second_tier_count

        for i, c in enumerate(candidates[:total_positions]):
            ticker = c['ticker']
            if i < self.top_tier_count:
                weight = self.top_tier_weight * self.leverage
            else:
                weight = self.second_tier_weight * self.leverage
            target_weights[ticker] = weight

        # Liquidate non-target
        for holding in self.portfolio.Values:
            if holding.invested and holding.symbol.value not in target_weights:
                self.liquidate(holding.symbol)

        # Rebalance
        for ticker, weight in target_weights.items():
            symbol = self.symbols[ticker]
            self.set_holdings(symbol, weight)
