from AlgorithmImports import *
from datetime import timedelta


class AcceleratingMomentumBalanced(QCAlgorithm):
    """
    Balanced Accelerating Momentum Strategy

    Hybrid approach:
    - Concentrated high-beta universe for returns
    - Strict 52WH filter for crash protection
    - Relative strength filter vs SPY
    - Position-level stop loss

    Target: 25-35% CAGR, <20% Max DD, Sharpe > 1.0
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(self._initialize_security)

        # Balanced universe: 20 stocks
        self.stock_list = [
            # High-Beta Tech (12)
            "NVDA", "AMD", "AVGO",
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            "TSLA", "NFLX", "CRM", "ADBE",
            # Fintech/Payments (4)
            "V", "MA", "SQ", "PYPL",
            # Stable Ballast (4)
            "JPM", "UNH", "LLY", "COST"
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
        self.spy_roc_21 = self.roc(self.spy, 21, Resolution.DAILY)
        self.spy_roc_63 = self.roc(self.spy, 63, Resolution.DAILY)
        self.spy_roc_126 = self.roc(self.spy, 126, Resolution.DAILY)

        # Position sizing - balanced
        self.max_position_pct = 0.07  # 7% max per position
        self.min_positions = 5
        self.max_positions = 15

        # Risk management
        self.stop_loss_pct = 0.12  # 12% stop loss per position
        self.entry_prices = {}

        self.set_warmup(timedelta(days=280))

        # Bi-weekly rebalancing (balance between responsive and stable)
        self.schedule.on(
            self.date_rules.every(DayOfWeek.WEDNESDAY),
            self.time_rules.before_market_close("SPY", 30),
            self.rebalance
        )

        # Daily stop loss check
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open("SPY", 30),
            self.check_stop_losses
        )

    def _initialize_security(self, security):
        security.set_slippage_model(ConstantSlippageModel(0.001))
        security.set_fee_model(InteractiveBrokersFeeModel())

    def calculate_accel_momentum(self, symbol):
        """Accelerating momentum"""
        if symbol not in self.roc_21:
            return None

        roc21 = self.roc_21[symbol]
        roc63 = self.roc_63[symbol]
        roc126 = self.roc_126[symbol]

        if not (roc21.is_ready and roc63.is_ready and roc126.is_ready):
            return None

        return (roc21.current.value + roc63.current.value + roc126.current.value) / 3

    def calculate_spy_accel_momentum(self):
        """SPY accelerating momentum"""
        if not (self.spy_roc_21.is_ready and self.spy_roc_63.is_ready and self.spy_roc_126.is_ready):
            return None

        return (self.spy_roc_21.current.value + self.spy_roc_63.current.value + self.spy_roc_126.current.value) / 3

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

    def check_entry_conditions(self, symbol):
        """
        Entry conditions (ALL must be true):
        1. Accelerating momentum > 0
        2. Relative strength: beat SPY
        3. Price > 50 SMA
        4. Within 30% of 52-week high
        """
        accel_mom = self.calculate_accel_momentum(symbol)
        if accel_mom is None or accel_mom <= 0:
            return False

        spy_accel = self.calculate_spy_accel_momentum()
        if spy_accel is not None and accel_mom <= spy_accel:
            return False

        sma = self.sma50.get(symbol)
        if sma is None or not sma.is_ready:
            return False
        if self.securities[symbol].price <= sma.current.value:
            return False

        # 52WH filter - within 30% of high
        proximity = self.calculate_52wh_proximity(symbol)
        if proximity is None or proximity < 0.70:
            return False

        return True

    def check_exit_conditions(self, symbol):
        """
        Exit if:
        1. Accelerating momentum < 0
        2. Underperforming SPY significantly
        3. Price < 50 SMA
        """
        accel_mom = self.calculate_accel_momentum(symbol)
        if accel_mom is None or accel_mom < 0:
            return True

        spy_accel = self.calculate_spy_accel_momentum()
        if spy_accel is not None and accel_mom < spy_accel * 0.8:  # Underperform by 20%+
            return True

        sma = self.sma50.get(symbol)
        if sma is not None and sma.is_ready:
            if self.securities[symbol].price < sma.current.value:
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
                    self.liquidate(symbol, "Stop loss triggered")
                    self.log(f"STOP LOSS: {symbol} at {loss_pct*100:.1f}% loss")
                    del self.entry_prices[symbol]

    def rebalance(self):
        """Bi-weekly rebalancing"""
        if self.is_warming_up:
            return

        current_holdings = set()
        for symbol in self.symbols.values():
            if self.portfolio[symbol].invested:
                current_holdings.add(symbol)

        exits = set()
        for symbol in current_holdings:
            if self.check_exit_conditions(symbol):
                exits.add(symbol)

        entry_candidates = []
        for ticker, symbol in self.symbols.items():
            if symbol not in current_holdings and self.check_entry_conditions(symbol):
                accel_mom = self.calculate_accel_momentum(symbol)
                if accel_mom is not None:
                    entry_candidates.append((symbol, accel_mom))

        entry_candidates.sort(key=lambda x: x[1], reverse=True)

        remaining_holdings = current_holdings - exits
        available_slots = self.max_positions - len(remaining_holdings)
        new_entries = [s for s, _ in entry_candidates[:available_slots]]

        for symbol in exits:
            self.liquidate(symbol, "Exit signal")
            self.log(f"EXIT: {symbol}")
            if symbol in self.entry_prices:
                del self.entry_prices[symbol]

        target_holdings = remaining_holdings.union(set(new_entries))
        num_positions = len(target_holdings)

        if num_positions >= self.min_positions:
            target_weight = min(1.0 / num_positions, self.max_position_pct)

            for symbol in target_holdings:
                current_weight = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value

                if abs(current_weight - target_weight) > 0.02 or symbol in new_entries:
                    self.set_holdings(symbol, target_weight)
                    if symbol in new_entries:
                        self.entry_prices[symbol] = self.securities[symbol].price
                        self.log(f"ENTRY: {symbol} at {target_weight*100:.1f}%")

    def on_data(self, data):
        pass
