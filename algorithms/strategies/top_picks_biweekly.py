from AlgorithmImports import *
from datetime import timedelta


class TopPicksBiweekly(QCAlgorithm):
    """
    Top Picks with Bi-Weekly Rebalancing

    More responsive to momentum changes:
    - Bi-weekly rebalancing (vs weekly)
    - Composite score weighted more to recent momentum
    - Regime detection for risk management

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
        self.roc_10 = {}   # Shorter period for faster response
        self.roc_21 = {}
        self.roc_63 = {}
        self.max_252 = {}

        for ticker, symbol in self.symbols.items():
            self.sma50[symbol] = self.sma(symbol, 50, Resolution.DAILY)
            self.roc_10[symbol] = self.roc(symbol, 10, Resolution.DAILY)
            self.roc_21[symbol] = self.roc(symbol, 21, Resolution.DAILY)
            self.roc_63[symbol] = self.roc(symbol, 63, Resolution.DAILY)
            self.max_252[symbol] = self.max(symbol, 252, Resolution.DAILY)

        # SPY indicators
        self.spy_sma50 = self.sma(self.spy, 50, Resolution.DAILY)
        self.spy_sma200 = self.sma(self.spy, 200, Resolution.DAILY)
        self.spy_roc_21 = self.roc(self.spy, 21, Resolution.DAILY)

        # Position management
        self.max_position_pct = 0.12
        self.target_positions = 7

        self.stop_loss_pct = 0.10
        self.entry_prices = {}

        self.set_warmup(timedelta(days=280))

        # BI-WEEKLY rebalancing (Wed and Fri)
        self.schedule.on(
            self.date_rules.every(DayOfWeek.WEDNESDAY),
            self.time_rules.before_market_close("SPY", 30),
            self.rebalance
        )
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

    def is_bullish_regime(self):
        """Simple bull/bear check"""
        if not (self.spy_sma50.is_ready and self.spy_sma200.is_ready):
            return True

        spy_price = self.securities[self.spy].price
        sma50 = self.spy_sma50.current.value
        sma200 = self.spy_sma200.current.value

        # Bull: SPY > SMA50 or SPY > SMA200
        return spy_price > sma50 or spy_price > sma200

    def get_position_scale(self):
        """Scale positions based on market regime"""
        if not (self.spy_sma50.is_ready and self.spy_sma200.is_ready):
            return 0.8

        spy_price = self.securities[self.spy].price
        sma50 = self.spy_sma50.current.value
        sma200 = self.spy_sma200.current.value

        if spy_price > sma50 > sma200:
            return 1.0  # Full exposure
        elif spy_price > sma200:
            return 0.8  # Cautious
        else:
            return 0.5  # Risk-off

    def calculate_composite_score(self, symbol):
        """Weight very recent momentum more heavily"""
        if symbol not in self.roc_10:
            return None

        roc10 = self.roc_10[symbol]
        roc21 = self.roc_21[symbol]
        roc63 = self.roc_63[symbol]

        if not (roc10.is_ready and roc21.is_ready and roc63.is_ready):
            return None

        # Heavy weight on recent momentum
        return (roc10.current.value * 0.4 +
                roc21.current.value * 0.4 +
                roc63.current.value * 0.2)

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
        if score is None or score < -5:  # Allow slight negative
            return True

        sma = self.sma50.get(symbol)
        if sma is not None and sma.is_ready:
            if self.securities[symbol].price < sma.current.value * 0.95:
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

        # Exit all if bearish
        if not self.is_bullish_regime():
            for symbol in self.symbols.values():
                if self.portfolio[symbol].invested:
                    self.liquidate(symbol, "Bear regime")
                    if symbol in self.entry_prices:
                        del self.entry_prices[symbol]
            return

        position_scale = self.get_position_scale()

        candidates = []
        for ticker, symbol in self.symbols.items():
            if self.is_qualified(symbol):
                score = self.calculate_composite_score(symbol)
                if score is not None:
                    candidates.append((symbol, ticker, score))

        candidates.sort(key=lambda x: x[2], reverse=True)

        top_picks = candidates[:self.target_positions]
        target_symbols = set(s for s, _, _ in top_picks)

        for symbol in self.symbols.values():
            if self.portfolio[symbol].invested:
                if symbol not in target_symbols or self.should_exit(symbol):
                    self.liquidate(symbol, "Exit")
                    self.log(f"EXIT: {symbol}")
                    if symbol in self.entry_prices:
                        del self.entry_prices[symbol]

        if len(top_picks) > 0:
            base_weight = min(1.0 / len(top_picks), self.max_position_pct)
            target_weight = base_weight * position_scale

            for symbol, ticker, score in top_picks:
                if not self.portfolio[symbol].invested:
                    self.set_holdings(symbol, target_weight)
                    self.entry_prices[symbol] = self.securities[symbol].price
                    self.log(f"ENTRY: {ticker} at {target_weight*100:.1f}%")
                else:
                    current_weight = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value
                    if abs(current_weight - target_weight) > 0.025:
                        self.set_holdings(symbol, target_weight)

    def on_data(self, data):
        pass
