from AlgorithmImports import *

class StopLossLeverage(QCAlgorithm):
    """
    Round 10 Strategy 2: Stop-Loss Protected Leverage

    THESIS: Use 1.25x leverage but with portfolio-level stop-loss at -20%.
    This caps maximum DD while allowing higher returns in bull markets.

    WHY IT MIGHT WORK:
    - Leverage boosts returns to 30%+ in good times
    - Stop-loss prevents catastrophic drawdowns
    - Re-entry after SPY recovers above 200 SMA

    RISK FACTORS:
    - Stop-loss may trigger at bottom (selling low)
    - Re-entry timing crucial
    - Whipsaws can erode capital

    Excludes: NVDA (robustness test)
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2025, 1, 1)
        self.set_cash(100000)

        self.leverage = 1.25
        self.stop_loss_threshold = -0.20  # -20% from peak
        self.recovery_required = 0.10  # 10% recovery before re-entry

        self.num_positions = 10
        self.position_weight = 0.10

        self.peak_portfolio_value = 100000
        self.stopped_out = False
        self.stopped_out_value = 0

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

        # Market regime
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.spy_sma200 = self.sma(self.spy, 200)

        self.set_benchmark("SPY")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)

        # Daily check for stop-loss
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 30),
            self.daily_check
        )

        # Monthly rebalance
        self.schedule.on(
            self.date_rules.month_start("SPY"),
            self.time_rules.after_market_open("SPY", 31),
            self.rebalance
        )

        self.set_warm_up(210, Resolution.DAILY)

    def daily_check(self):
        if self.is_warming_up:
            return

        current_value = self.portfolio.total_portfolio_value

        # Update peak
        if current_value > self.peak_portfolio_value:
            self.peak_portfolio_value = current_value

        # Check stop-loss
        if not self.stopped_out:
            drawdown = (current_value - self.peak_portfolio_value) / self.peak_portfolio_value
            if drawdown <= self.stop_loss_threshold:
                self.liquidate()
                self.stopped_out = True
                self.stopped_out_value = current_value
                self.debug(f"{self.time.date()}: STOP-LOSS triggered at {drawdown:.1%} DD")

        # Check recovery for re-entry
        if self.stopped_out:
            recovery = (current_value - self.stopped_out_value) / self.stopped_out_value
            spy_price = self.securities[self.spy].price
            spy_above_sma = spy_price > self.spy_sma200.current.value

            if recovery >= self.recovery_required and spy_above_sma:
                self.stopped_out = False
                self.peak_portfolio_value = current_value
                self.debug(f"{self.time.date()}: Recovery - re-entering market")

    def rebalance(self):
        if self.is_warming_up:
            return

        if self.stopped_out:
            return

        if not self.spy_sma200.is_ready:
            return

        spy_price = self.securities[self.spy].price
        bull_market = spy_price > self.spy_sma200.current.value

        if not bull_market:
            self.liquidate()
            return

        # Get momentum scores
        momentum_scores = {}
        for ticker in self.universe_tickers:
            if not self.momentum_ind[ticker].is_ready:
                continue
            symbol = self.symbols[ticker]
            if not self.securities[symbol].price or self.securities[symbol].price <= 0:
                continue
            momentum_scores[ticker] = self.momentum_ind[ticker].current.value

        # Top N by momentum
        ranked = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        top_tickers = [t[0] for t in ranked[:self.num_positions]]

        # Liquidate non-target positions
        for holding in self.portfolio.Values:
            if holding.invested and holding.symbol.value not in top_tickers:
                self.liquidate(holding.symbol)

        # Apply leveraged weights
        for ticker in top_tickers:
            symbol = self.symbols[ticker]
            self.set_holdings(symbol, self.position_weight * self.leverage)
