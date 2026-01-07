from AlgorithmImports import *
from datetime import timedelta


class AcceleratingMomentumAggressive(QCAlgorithm):
    """
    Aggressive Accelerating Momentum Strategy

    More concentrated, higher-beta universe
    Looser filters for more signals
    Faster rebalancing

    Target: 30%+ CAGR with acceptable drawdown
    """

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        self.set_security_initializer(self._initialize_security)

        # Concentrated high-beta universe (15 stocks)
        self.stock_list = [
            # AI/Semiconductors (highest momentum)
            "NVDA", "AMD", "AVGO",
            # Tech Giants
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            # High-Growth
            "TSLA", "NFLX", "CRM",
            # Cloud/Cyber
            "CRWD", "NET",
            # E-commerce/Fintech
            "SHOP", "SQ"
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

        # Position sizing - more concentrated
        self.max_position_pct = 0.10  # 10% max per position (more concentrated)
        self.min_positions = 3
        self.max_positions = 12

        self.set_warmup(timedelta(days=280))

        # Daily rebalancing for faster response
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close("SPY", 30),
            self.rebalance
        )

    def _initialize_security(self, security):
        security.set_slippage_model(ConstantSlippageModel(0.001))
        security.set_fee_model(InteractiveBrokersFeeModel())

    def calculate_accel_momentum(self, symbol):
        """Accelerating momentum: avg of 1m, 3m, 6m returns"""
        if symbol not in self.roc_21:
            return None

        roc21 = self.roc_21[symbol]
        roc63 = self.roc_63[symbol]
        roc126 = self.roc_126[symbol]

        if not (roc21.is_ready and roc63.is_ready and roc126.is_ready):
            return None

        return (roc21.current.value + roc63.current.value + roc126.current.value) / 3

    def calculate_52wh_proximity(self, symbol):
        """How close to 52-week high (0-1)"""
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
        AGGRESSIVE entry conditions:
        1. Accelerating momentum > 0
        2. Price above 50 SMA
        3. Within 40% of 52-week high (looser than base strategy)
        """
        accel_mom = self.calculate_accel_momentum(symbol)
        if accel_mom is None or accel_mom <= 0:
            return False

        sma = self.sma50.get(symbol)
        if sma is None or not sma.is_ready:
            return False
        if self.securities[symbol].price <= sma.current.value:
            return False

        # Looser 52WH filter - within 40% of high
        proximity = self.calculate_52wh_proximity(symbol)
        if proximity is None or proximity < 0.60:
            return False

        return True

    def check_exit_conditions(self, symbol):
        """
        Exit if:
        1. Accelerating momentum goes negative
        2. Price drops below 50 SMA
        """
        accel_mom = self.calculate_accel_momentum(symbol)
        if accel_mom is None or accel_mom < 0:
            return True

        sma = self.sma50.get(symbol)
        if sma is not None and sma.is_ready:
            if self.securities[symbol].price < sma.current.value:
                return True

        return False

    def rebalance(self):
        """Daily rebalancing"""
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

        target_holdings = remaining_holdings.union(set(new_entries))
        num_positions = len(target_holdings)

        if num_positions > 0:
            target_weight = min(1.0 / num_positions, self.max_position_pct)

            for symbol in target_holdings:
                current_weight = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value

                if abs(current_weight - target_weight) > 0.02 or symbol in new_entries:
                    self.set_holdings(symbol, target_weight)
                    if symbol in new_entries:
                        self.log(f"ENTRY: {symbol} at {target_weight*100:.1f}%")

    def on_data(self, data):
        pass
