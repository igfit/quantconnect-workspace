from AlgorithmImports import *
from datetime import timedelta


class TopPicksBalanced(QCAlgorithm):
    """
    Top Picks Balanced - Optimized Risk/Return

    Combines best elements:
    - Strong composite momentum scoring (from Top Picks)
    - Moderate regime scaling (not too aggressive)
    - Trailing stops to lock in gains
    - 7 positions at ~12% each

    Target: 25-30% CAGR with ~20% drawdown
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(self._initialize_security)

        self.stock_list = [
            "NVDA", "AMD", "AVGO", "QCOM",
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "TSLA", "NFLX", "CRM", "ADBE", "NOW",
            "CRWD", "NET", "SNOW", "SHOP",
            "SQ", "COIN",
            "V", "MA", "PYPL",
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

        # SPY indicators
        self.spy_sma50 = self.sma(self.spy, 50, Resolution.DAILY)
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_roc_21 = self.roc(self.spy, 21, Resolution.DAILY)
        self.spy_roc_63 = self.roc(self.spy, 63, Resolution.DAILY)
        self.spy_roc_126 = self.roc(self.spy, 126, Resolution.DAILY)

        # BALANCED settings
        self.max_position_pct = 0.14
        self.target_positions = 7

        # Risk management
        self.stop_loss_pct = 0.12
        self.trailing_stop_pct = 0.15
        self.entry_prices = {}
        self.high_prices = {}

        self.set_warmup(timedelta(days=280))

        # Weekly rebalancing
        self.schedule.on(
            self.date_rules.every(DayOfWeek.FRIDAY),
            self.time_rules.before_market_close("SPY", 30),
            self.rebalance
        )

        # Daily stop checks
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open("SPY", 30),
            self.check_stops
        )

    def _initialize_security(self, security):
        security.set_slippage_model(ConstantSlippageModel(0.001))
        security.set_fee_model(InteractiveBrokersFeeModel())

    def get_regime_scale(self):
        """
        Moderate scaling based on market regime.
        Less aggressive than full adaptive - only scale down 20% in cautious.
        """
        if not (self.spy_sma50.is_ready and self.spy_sma200.is_ready):
            return 0.9

        spy_price = self.securities[self.spy].price
        sma50 = self.spy_sma50.current.value
        sma200 = self.spy_sma200.current.value

        spy_mom = self.calculate_spy_score()
        if spy_mom is None:
            return 0.9

        # Strong bull: full exposure
        if spy_price > sma50 > sma200 and spy_mom > 0:
            return 1.0
        # Moderate bull: slight reduction
        elif spy_price > sma200:
            return 0.9
        # Weak/bear: moderate reduction
        elif spy_price > sma200 * 0.95:
            return 0.7
        # Strong bear: significant reduction
        else:
            return 0.5

    def calculate_composite_score(self, symbol):
        """Weight recent momentum higher - same as Top Picks"""
        if symbol not in self.roc_21:
            return None

        roc21 = self.roc_21[symbol]
        roc63 = self.roc_63[symbol]
        roc126 = self.roc_126[symbol]

        if not (roc21.is_ready and roc63.is_ready and roc126.is_ready):
            return None

        return (roc21.current.value * 0.5 +
                roc63.current.value * 0.3 +
                roc126.current.value * 0.2)

    def calculate_spy_score(self):
        if not (self.spy_roc_21.is_ready and self.spy_roc_63.is_ready and self.spy_roc_126.is_ready):
            return None

        return (self.spy_roc_21.current.value * 0.5 +
                self.spy_roc_63.current.value * 0.3 +
                self.spy_roc_126.current.value * 0.2)

    def calculate_52wh_proximity(self, symbol):
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
        score = self.calculate_composite_score(symbol)
        if score is None or score <= 0:
            return False

        spy_score = self.calculate_spy_score()
        if spy_score is not None and score <= spy_score:
            return False

        sma = self.sma50.get(symbol)
        if sma is None or not sma.is_ready:
            return False
        if self.securities[symbol].price <= sma.current.value:
            return False

        # Within 30% of high
        proximity = self.calculate_52wh_proximity(symbol)
        if proximity is None or proximity < 0.70:
            return False

        return True

    def should_exit(self, symbol):
        score = self.calculate_composite_score(symbol)
        if score is None or score < 0:
            return True

        sma = self.sma50.get(symbol)
        if sma is not None and sma.is_ready:
            if self.securities[symbol].price < sma.current.value * 0.97:
                return True

        return False

    def check_stops(self):
        """Check both hard stop and trailing stop"""
        if self.is_warming_up:
            return

        for symbol in self.symbols.values():
            if not self.portfolio[symbol].invested:
                continue

            current_price = self.securities[symbol].price

            # Update high water mark
            if symbol in self.high_prices:
                if current_price > self.high_prices[symbol]:
                    self.high_prices[symbol] = current_price
            else:
                self.high_prices[symbol] = current_price

            # Hard stop from entry
            if symbol in self.entry_prices:
                entry_price = self.entry_prices[symbol]
                loss_pct = (entry_price - current_price) / entry_price

                if loss_pct >= self.stop_loss_pct:
                    self.liquidate(symbol, "Hard stop")
                    self.log(f"HARD STOP: {symbol} at {loss_pct*100:.1f}%")
                    self._clear_tracking(symbol)
                    continue

            # Trailing stop from high
            if symbol in self.high_prices:
                high_price = self.high_prices[symbol]
                drop_pct = (high_price - current_price) / high_price

                if drop_pct >= self.trailing_stop_pct:
                    self.liquidate(symbol, "Trailing stop")
                    self.log(f"TRAIL STOP: {symbol} at {drop_pct*100:.1f}% from high")
                    self._clear_tracking(symbol)

    def _clear_tracking(self, symbol):
        if symbol in self.entry_prices:
            del self.entry_prices[symbol]
        if symbol in self.high_prices:
            del self.high_prices[symbol]

    def rebalance(self):
        if self.is_warming_up:
            return

        regime_scale = self.get_regime_scale()
        self.log(f"Regime scale: {regime_scale}")

        candidates = []
        for ticker, symbol in self.symbols.items():
            if self.is_qualified(symbol):
                score = self.calculate_composite_score(symbol)
                if score is not None:
                    candidates.append((symbol, ticker, score))

        candidates.sort(key=lambda x: x[2], reverse=True)

        top_picks = candidates[:self.target_positions]
        target_symbols = set(s for s, _, _ in top_picks)

        # Exit positions not in top picks
        for symbol in self.symbols.values():
            if self.portfolio[symbol].invested:
                if symbol not in target_symbols or self.should_exit(symbol):
                    self.liquidate(symbol, "Exit")
                    self.log(f"EXIT: {symbol}")
                    self._clear_tracking(symbol)

        # Enter/adjust positions
        if len(top_picks) > 0:
            base_weight = min(1.0 / len(top_picks), self.max_position_pct)
            target_weight = base_weight * regime_scale

            for symbol, ticker, score in top_picks:
                if not self.portfolio[symbol].invested:
                    self.set_holdings(symbol, target_weight)
                    self.entry_prices[symbol] = self.securities[symbol].price
                    self.high_prices[symbol] = self.securities[symbol].price
                    self.log(f"ENTRY: {ticker} at {target_weight*100:.1f}% (score: {score:.1f}%)")
                else:
                    current_weight = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value
                    if abs(current_weight - target_weight) > 0.03:
                        self.set_holdings(symbol, target_weight)

    def on_data(self, data):
        pass
