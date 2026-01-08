from AlgorithmImports import *
from datetime import timedelta


class TopPicksMomentum(QCAlgorithm):
    """
    Top Picks Momentum Strategy

    High conviction: Only hold the top 5-8 stocks with strongest momentum.
    More concentrated positions for higher returns.

    Target: 30%+ CAGR
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(self._initialize_security)

        # Wide universe to pick from (25 high-momentum candidates)
        self.stock_list = [
            # Tech/AI Leaders
            "NVDA", "AMD", "AVGO", "QCOM",
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "TSLA", "NFLX", "CRM", "ADBE", "NOW",
            # Growth/Momentum
            "CRWD", "NET", "SNOW", "SHOP",
            "SQ", "COIN",
            # Fintech
            "V", "MA", "PYPL",
            # Stable
            "LLY", "UNH"
        ]

        self.symbols = {}
        for ticker in self.stock_list:
            equity = self.add_equity(ticker, Resolution.DAILY)
            self.symbols[ticker] = equity.symbol

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # Indicators
        self.sma50 = {}
        self.roc_21 = {}
        self.roc_63 = {}
        self.roc_126 = {}
        self.max_252 = {}

        for ticker, symbol in self.symbols.items():
            self.sma50[symbol] = self.sma(symbol, 50, Resolution.DAILY)
            self.roc_21[symbol] = self.roc(symbol, 21, Resolution.DAILY)
            self.roc_63[symbol] = self.roc(symbol, 63, Resolution.DAILY)
            self.roc_126[symbol] = self.roc(symbol, 126, Resolution.DAILY)
            self.max_252[symbol] = self.max(symbol, 252, Resolution.DAILY)

        # SPY for relative strength
        self.spy_roc_21 = self.roc(self.spy, 21, Resolution.DAILY)
        self.spy_roc_63 = self.roc(self.spy, 63, Resolution.DAILY)
        self.spy_roc_126 = self.roc(self.spy, 126, Resolution.DAILY)

        # HIGH CONVICTION: Fewer positions, larger sizes
        self.max_position_pct = 0.15  # 15% max per position
        self.target_positions = 6     # Target 6 positions
        self.max_positions = 8

        # Risk management
        self.stop_loss_pct = 0.15
        self.entry_prices = {}

        self.set_warmup(timedelta(days=280))

        # Weekly rebalancing
        self.schedule.on(
            self.date_rules.every(DayOfWeek.FRIDAY),
            self.time_rules.before_market_close("SPY", 30),
            self.rebalance
        )

        # Daily stop loss
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open("SPY", 30),
            self.check_stop_losses
        )

    def _initialize_security(self, security):
        security.set_slippage_model(ConstantSlippageModel(0.001))
        security.set_fee_model(InteractiveBrokersFeeModel())

    def calculate_composite_score(self, symbol):
        """
        Calculate composite momentum score.
        Weights recent momentum higher.
        """
        if symbol not in self.roc_21:
            return None

        roc21 = self.roc_21[symbol]
        roc63 = self.roc_63[symbol]
        roc126 = self.roc_126[symbol]

        if not (roc21.is_ready and roc63.is_ready and roc126.is_ready):
            return None

        # Weight recent momentum higher
        return (roc21.current.value * 0.5 +
                roc63.current.value * 0.3 +
                roc126.current.value * 0.2)

    def calculate_spy_score(self):
        """SPY composite score"""
        if not (self.spy_roc_21.is_ready and self.spy_roc_63.is_ready and self.spy_roc_126.is_ready):
            return None

        return (self.spy_roc_21.current.value * 0.5 +
                self.spy_roc_63.current.value * 0.3 +
                self.spy_roc_126.current.value * 0.2)

    def calculate_52wh_proximity(self, symbol):
        """Proximity to 52-week high"""
        if symbol not in self.max_252:
            return None

        max_ind = self.max_252[symbol]
        if not max_ind.is_ready:
            return None

        current_price = self.securities[symbol].price
        high_252 = max_ind.current.value

        if high_252 <= 0:
            return None

        return current_price / high_252

    def is_qualified(self, symbol):
        """Check if stock qualifies for consideration"""
        # Must have positive momentum
        score = self.calculate_composite_score(symbol)
        if score is None or score <= 0:
            return False

        # Must beat SPY
        spy_score = self.calculate_spy_score()
        if spy_score is not None and score <= spy_score:
            return False

        # Must be in uptrend
        sma = self.sma50.get(symbol)
        if sma is None or not sma.is_ready:
            return False
        if self.securities[symbol].price <= sma.current.value:
            return False

        # Within 35% of high (looser filter for more candidates)
        proximity = self.calculate_52wh_proximity(symbol)
        if proximity is None or proximity < 0.65:
            return False

        return True

    def should_exit(self, symbol):
        """Check exit conditions"""
        score = self.calculate_composite_score(symbol)
        if score is None or score < 0:
            return True

        sma = self.sma50.get(symbol)
        if sma is not None and sma.is_ready:
            if self.securities[symbol].price < sma.current.value * 0.98:  # 2% buffer
                return True

        return False

    def check_stop_losses(self):
        """Daily stop loss check"""
        if self.is_warming_up:
            return

        for symbol in self.symbols.values():
            if self.portfolio[symbol].invested and symbol in self.entry_prices:
                entry_price = self.entry_prices[symbol]
                current_price = self.securities[symbol].price
                loss_pct = (entry_price - current_price) / entry_price

                if loss_pct >= self.stop_loss_pct:
                    self.liquidate(symbol, "Stop loss")
                    self.log(f"STOP LOSS: {symbol} at {loss_pct*100:.1f}%")
                    del self.entry_prices[symbol]

    def rebalance(self):
        """Weekly rotation into top picks"""
        if self.is_warming_up:
            return

        # Score all qualified stocks
        candidates = []
        for ticker, symbol in self.symbols.items():
            if self.is_qualified(symbol):
                score = self.calculate_composite_score(symbol)
                if score is not None:
                    candidates.append((symbol, ticker, score))

        # Sort by score (highest first)
        candidates.sort(key=lambda x: x[2], reverse=True)

        # Select top N
        top_picks = candidates[:self.target_positions]
        target_symbols = set(s for s, _, _ in top_picks)

        # Check current holdings for exits
        for symbol in self.symbols.values():
            if self.portfolio[symbol].invested:
                if symbol not in target_symbols or self.should_exit(symbol):
                    self.liquidate(symbol, "Exit")
                    self.log(f"EXIT: {symbol}")
                    if symbol in self.entry_prices:
                        del self.entry_prices[symbol]

        # Equal weight the top picks
        if len(top_picks) > 0:
            weight = min(1.0 / len(top_picks), self.max_position_pct)

            for symbol, ticker, score in top_picks:
                if not self.portfolio[symbol].invested:
                    self.set_holdings(symbol, weight)
                    self.entry_prices[symbol] = self.securities[symbol].price
                    self.log(f"ENTRY: {ticker} (score: {score:.1f}%) at {weight*100:.1f}%")
                else:
                    # Rebalance existing position
                    current_weight = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value
                    if abs(current_weight - weight) > 0.03:
                        self.set_holdings(symbol, weight)

    def on_data(self, data):
        pass
