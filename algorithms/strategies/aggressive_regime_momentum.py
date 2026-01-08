from AlgorithmImports import *

class AggressiveRegimeMomentum(QCAlgorithm):
    """
    Round 9 Strategy 5: Aggressive Regime-Based Sizing

    THESIS: Vary leverage based on market conditions. Use 125% exposure
    in calm bull markets (low VIX), 100% in normal, 0% in bear/high VIX.

    WHY IT MIGHT WORK:
    - Low VIX + bull = ideal conditions for momentum
    - Extra leverage when risk is lowest maximizes returns
    - Quick de-risk when conditions deteriorate
    - VIX < 18 historically = strong equity returns

    RISK FACTORS:
    - VIX can spike suddenly (overnight gaps)
    - Leverage rebalancing costs
    - May miss recoveries (too conservative exit)

    Excludes: NVDA (robustness test)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        # Regime-based leverage
        self.strong_bull_leverage = 1.25  # VIX < 18 and SPY > 200 SMA
        self.normal_bull_leverage = 1.00  # VIX 18-25 and SPY > 200 SMA
        self.weak_bull_leverage = 0.50    # VIX > 25 and SPY > 200 SMA
        self.bear_leverage = 0.00         # SPY < 200 SMA

        # Position sizing (10 positions)
        self.num_positions = 10
        self.base_weight = 0.10

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

        for ticker in self.universe_tickers:
            symbol = self.add_equity(ticker, Resolution.DAILY).symbol
            self.symbols[ticker] = symbol
            self.momentum_ind[ticker] = self.momp(symbol, 126, Resolution.DAILY)

        # Market regime indicators
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200)

        # VIX for volatility regime
        self.vix = self.add_data(CBOE, "VIX", Resolution.DAILY).symbol

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)

        # Weekly rebalance
        self.schedule.on(
            self.date_rules.every(DayOfWeek.MONDAY),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )

        self.set_warm_up(210, Resolution.DAILY)

    def get_regime_leverage(self):
        """Determine leverage based on market regime"""
        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            return self.bear_leverage, "Bear"

        # Check VIX level
        vix_price = self.securities[self.vix].price

        if vix_price < 18:
            return self.strong_bull_leverage, f"Strong Bull (VIX={vix_price:.1f})"
        elif vix_price < 25:
            return self.normal_bull_leverage, f"Normal Bull (VIX={vix_price:.1f})"
        else:
            return self.weak_bull_leverage, f"Weak Bull (VIX={vix_price:.1f})"

    def rebalance(self):
        if self.is_warming_up:
            return

        if not self.spy_sma200.is_ready:
            return

        leverage, regime = self.get_regime_leverage()

        if leverage == 0:
            self.liquidate()
            self.debug(f"{self.time.date()}: {regime} - all cash")
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
        top_tickers = [t[0] for t in ranked[:self.num_positions]]

        # Liquidate positions not in top
        for holding in self.portfolio.Values:
            if holding.invested and holding.symbol.value not in top_tickers:
                self.liquidate(holding.symbol)

        # Apply leveraged weights
        for ticker in top_tickers:
            symbol = self.symbols[ticker]
            weight = self.base_weight * leverage
            self.set_holdings(symbol, weight)

        self.debug(f"{self.time.date()}: {regime} - {len(top_tickers)} positions at {leverage}x")
