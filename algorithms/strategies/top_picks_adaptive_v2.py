from AlgorithmImports import *
from datetime import timedelta


class TopPicksAdaptiveV2(QCAlgorithm):
    """
    Top Picks Adaptive V2 - Less Conservative

    Same regime detection but:
    - Higher base position sizes (15% vs 12%)
    - Less aggressive regime scaling
    - More positions (8 vs 6)

    Target: 30%+ CAGR with <20% drawdown
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
        self.atr_14 = {}

        for ticker, symbol in self.symbols.items():
            self.sma50[symbol] = self.sma(symbol, 50, Resolution.DAILY)
            self.roc_21[symbol] = self.roc(symbol, 21, Resolution.DAILY)
            self.roc_63[symbol] = self.roc(symbol, 63, Resolution.DAILY)
            self.roc_126[symbol] = self.roc(symbol, 126, Resolution.DAILY)
            self.max_252[symbol] = self.max(symbol, 252, Resolution.DAILY)
            self.atr_14[symbol] = self.atr(symbol, 14, MovingAverageType.SIMPLE, Resolution.DAILY)

        # SPY indicators for regime detection
        self.spy_sma50 = self.sma(self.spy, 50, Resolution.DAILY)
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_roc_21 = self.roc(self.spy, 21, Resolution.DAILY)
        self.spy_roc_63 = self.roc(self.spy, 63, Resolution.DAILY)
        self.spy_roc_126 = self.roc(self.spy, 126, Resolution.DAILY)

        # LESS CONSERVATIVE position management
        self.base_position_pct = 0.15  # Higher base (was 0.12)
        self.target_positions = 8      # More positions (was 6)
        self.max_positions = 10

        self.stop_loss_pct = 0.12
        self.entry_prices = {}

        self.set_warmup(timedelta(days=280))

        self.schedule.on(
            self.date_rules.every(DayOfWeek.FRIDAY),
            self.time_rules.before_market_close("SPY", 30),
            self.rebalance
        )

        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open("SPY", 30),
            self.check_stops
        )

    def _initialize_security(self, security):
        security.set_slippage_model(ConstantSlippageModel(0.001))
        security.set_fee_model(InteractiveBrokersFeeModel())

    def get_market_regime(self):
        """
        Determine market regime:
        - BULLISH: SPY > SMA50 > SMA200, positive momentum
        - CAUTIOUS: Mixed signals
        - BEARISH: SPY < SMA200 or strong negative momentum
        """
        if not (self.spy_sma50.is_ready and self.spy_sma200.is_ready):
            return "CAUTIOUS"

        spy_price = self.securities[self.spy].price
        sma50 = self.spy_sma50.current.value
        sma200 = self.spy_sma200.current.value

        spy_momentum = self.calculate_spy_score()
        if spy_momentum is None:
            return "CAUTIOUS"

        # Strong bull: Price > SMA50 > SMA200 and positive momentum
        if spy_price > sma50 > sma200 and spy_momentum > 5:
            return "BULLISH"
        # Bear: Below SMA200 or very negative momentum
        elif spy_price < sma200 * 0.98 or spy_momentum < -15:
            return "BEARISH"
        else:
            return "CAUTIOUS"

    def get_regime_multiplier(self):
        """Position size multiplier based on regime - LESS CONSERVATIVE"""
        regime = self.get_market_regime()
        if regime == "BULLISH":
            return 1.0
        elif regime == "CAUTIOUS":
            return 0.85  # Was 0.7
        else:  # BEARISH
            return 0.5   # Was 0.4

    def calculate_composite_score(self, symbol):
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

    def calculate_volatility_factor(self, symbol):
        """Inverse volatility factor for position sizing."""
        if symbol not in self.atr_14:
            return 1.0

        atr = self.atr_14[symbol]
        if not atr.is_ready:
            return 1.0

        price = self.securities[symbol].price
        if price <= 0:
            return 1.0

        atr_pct = atr.current.value / price

        if atr_pct < 0.01:
            return 1.2
        elif atr_pct < 0.02:
            return 1.0
        elif atr_pct < 0.03:
            return 0.85
        else:
            return 0.65

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
        if self.is_warming_up:
            return

        for symbol in self.symbols.values():
            if not self.portfolio[symbol].invested:
                continue

            if symbol in self.entry_prices:
                entry_price = self.entry_prices[symbol]
                current_price = self.securities[symbol].price
                loss_pct = (entry_price - current_price) / entry_price

                if loss_pct >= self.stop_loss_pct:
                    self.liquidate(symbol, "Stop loss")
                    self.log(f"STOP: {symbol} at {loss_pct*100:.1f}%")
                    del self.entry_prices[symbol]

    def rebalance(self):
        if self.is_warming_up:
            return

        regime = self.get_market_regime()
        regime_mult = self.get_regime_multiplier()
        self.log(f"Market Regime: {regime} (mult: {regime_mult})")

        # In bearish regime, reduce but don't fully exit
        if regime == "BEARISH":
            for symbol in self.symbols.values():
                if self.portfolio[symbol].invested:
                    current_weight = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value
                    target_weight = current_weight * 0.5  # Cut positions in half
                    if target_weight < 0.02:
                        self.liquidate(symbol, "Bear regime exit")
                        if symbol in self.entry_prices:
                            del self.entry_prices[symbol]
                    else:
                        self.set_holdings(symbol, target_weight)
            return

        candidates = []
        for ticker, symbol in self.symbols.items():
            if self.is_qualified(symbol):
                score = self.calculate_composite_score(symbol)
                if score is not None:
                    vol_factor = self.calculate_volatility_factor(symbol)
                    candidates.append((symbol, ticker, score, vol_factor))

        candidates.sort(key=lambda x: x[2], reverse=True)

        top_picks = candidates[:self.target_positions]
        target_symbols = set(s for s, _, _, _ in top_picks)

        for symbol in self.symbols.values():
            if self.portfolio[symbol].invested:
                if symbol not in target_symbols or self.should_exit(symbol):
                    self.liquidate(symbol, "Exit")
                    self.log(f"EXIT: {symbol}")
                    if symbol in self.entry_prices:
                        del self.entry_prices[symbol]

        if len(top_picks) > 0:
            total_vol_factor = sum(vf for _, _, _, vf in top_picks)

            for symbol, ticker, score, vol_factor in top_picks:
                base_weight = self.base_position_pct * (vol_factor / (total_vol_factor / len(top_picks)))
                target_weight = min(base_weight * regime_mult, 0.15)

                if not self.portfolio[symbol].invested:
                    self.set_holdings(symbol, target_weight)
                    self.entry_prices[symbol] = self.securities[symbol].price
                    self.log(f"ENTRY: {ticker} at {target_weight*100:.1f}%")
                else:
                    current_weight = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value
                    if abs(current_weight - target_weight) > 0.03:
                        self.set_holdings(symbol, target_weight)

    def on_data(self, data):
        pass
