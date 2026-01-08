from AlgorithmImports import *
from datetime import timedelta
import numpy as np


class AcceleratingDualMomentum(QCAlgorithm):
    """
    Accelerating Dual Momentum Strategy

    Based on academic research:
    - Jegadeesh & Titman (1993): Momentum
    - George & Hwang (2004): 52-week high momentum
    - Grinblatt & Moskowitz (2004): Accelerating momentum

    ENTRY (ALL must be true):
    1. Accelerating Momentum > 0 (avg of 1m, 3m, 6m returns)
    2. Stock AccelMom > SPY AccelMom (relative strength)
    3. Price > 50-day SMA (trend confirmation)
    4. Price within 25% of 52-week high (crash protection)

    EXIT (ANY triggers):
    1. Accelerating Momentum < 0
    2. Stock AccelMom < SPY AccelMom
    3. Price < 50-day SMA

    Position Sizing: Equal weight, max 5% per position
    Rebalance: Weekly
    """

    def initialize(self):
        # Backtest period
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100000)

        # Execution settings
        self.set_security_initializer(self._initialize_security)

        # Universe - 28 diversified stocks
        self.stock_list = [
            # Tech Giants
            "AAPL", "MSFT", "GOOGL", "AMZN", "META",
            # AI/Semiconductors
            "NVDA", "AMD", "AVGO", "QCOM",
            # High-Growth Tech
            "TSLA", "NFLX", "CRM", "ADBE",
            # Fintech/Payments
            "SQ", "PYPL", "V", "MA",
            # Cloud/Cyber
            "SNOW", "CRWD", "NET",
            # E-commerce
            "SHOP",
            # Stable Large-Caps (ballast)
            "JPM", "GS", "UNH", "LLY", "COST", "HD"
        ]

        # Add securities
        self.symbols = {}
        for ticker in self.stock_list:
            equity = self.add_equity(ticker, Resolution.DAILY)
            self.symbols[ticker] = equity.symbol

        # Add SPY as benchmark
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.set_benchmark("SPY")

        # Indicators storage
        self.sma50 = {}
        self.roc_21 = {}
        self.roc_63 = {}
        self.roc_126 = {}
        self.max_252 = {}  # Rolling 52-week high

        # Initialize indicators for each symbol
        for ticker, symbol in self.symbols.items():
            self.sma50[symbol] = self.sma(symbol, 50, Resolution.DAILY)
            self.roc_21[symbol] = self.roc(symbol, 21, Resolution.DAILY)
            self.roc_63[symbol] = self.roc(symbol, 63, Resolution.DAILY)
            self.roc_126[symbol] = self.roc(symbol, 126, Resolution.DAILY)
            self.max_252[symbol] = self.max(symbol, 252, Resolution.DAILY)

        # SPY indicators for relative strength
        self.spy_roc_21 = self.roc(self.spy, 21, Resolution.DAILY)
        self.spy_roc_63 = self.roc(self.spy, 63, Resolution.DAILY)
        self.spy_roc_126 = self.roc(self.spy, 126, Resolution.DAILY)

        # Position sizing
        self.max_position_pct = 0.05  # 5% max per position
        self.min_positions = 5
        self.max_positions = 20

        # Warmup period (252 days for 52-week high)
        self.set_warmup(timedelta(days=280))

        # Schedule weekly rebalance (Friday before close)
        self.schedule.on(
            self.date_rules.every(DayOfWeek.FRIDAY),
            self.time_rules.before_market_close("SPY", 30),
            self.rebalance
        )

        # Tracking
        self.last_rebalance = None

    def _initialize_security(self, security):
        """Set slippage and commission models"""
        security.set_slippage_model(ConstantSlippageModel(0.001))  # 0.1% slippage
        security.set_fee_model(InteractiveBrokersFeeModel())

    def calculate_accel_momentum(self, symbol):
        """
        Calculate accelerating momentum as average of 1m, 3m, 6m ROC.
        Returns None if indicators not ready.
        """
        if symbol not in self.roc_21:
            return None

        roc21 = self.roc_21[symbol]
        roc63 = self.roc_63[symbol]
        roc126 = self.roc_126[symbol]

        if not (roc21.is_ready and roc63.is_ready and roc126.is_ready):
            return None

        # Average the three ROC values
        return (roc21.current.value + roc63.current.value + roc126.current.value) / 3

    def calculate_spy_accel_momentum(self):
        """Calculate SPY's accelerating momentum for relative strength comparison"""
        if not (self.spy_roc_21.is_ready and self.spy_roc_63.is_ready and self.spy_roc_126.is_ready):
            return None

        return (self.spy_roc_21.current.value + self.spy_roc_63.current.value + self.spy_roc_126.current.value) / 3

    def calculate_52wh_proximity(self, symbol):
        """
        Calculate how close price is to 52-week high.
        Returns ratio (0 to 1), where 1 = at high, 0.75 = within 25% of high.
        """
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
        Check all entry conditions for a symbol.
        Returns True if all conditions met.
        """
        # Get accelerating momentum
        accel_mom = self.calculate_accel_momentum(symbol)
        if accel_mom is None:
            return False

        # Condition 1: Accelerating momentum > 0
        if accel_mom <= 0:
            return False

        # Condition 2: Relative strength - beat SPY
        spy_accel_mom = self.calculate_spy_accel_momentum()
        if spy_accel_mom is None:
            return False
        if accel_mom <= spy_accel_mom:
            return False

        # Condition 3: Price above 50 SMA
        sma = self.sma50.get(symbol)
        if sma is None or not sma.is_ready:
            return False
        if self.securities[symbol].price <= sma.current.value:
            return False

        # Condition 4: Within 25% of 52-week high
        proximity = self.calculate_52wh_proximity(symbol)
        if proximity is None:
            return False
        if proximity < 0.75:  # More than 25% below high
            return False

        return True

    def check_exit_conditions(self, symbol):
        """
        Check exit conditions for a symbol.
        Returns True if ANY exit condition is met.
        """
        # Get accelerating momentum
        accel_mom = self.calculate_accel_momentum(symbol)
        if accel_mom is None:
            return True  # Exit if can't calculate

        # Exit 1: Accelerating momentum < 0
        if accel_mom < 0:
            return True

        # Exit 2: Relative strength - underperforming SPY
        spy_accel_mom = self.calculate_spy_accel_momentum()
        if spy_accel_mom is not None and accel_mom < spy_accel_mom:
            return True

        # Exit 3: Price below 50 SMA
        sma = self.sma50.get(symbol)
        if sma is not None and sma.is_ready:
            if self.securities[symbol].price < sma.current.value:
                return True

        return False

    def rebalance(self):
        """Weekly rebalancing logic"""
        if self.is_warming_up:
            return

        # Get current holdings
        current_holdings = set()
        for symbol in self.symbols.values():
            if self.portfolio[symbol].invested:
                current_holdings.add(symbol)

        # Check for exits
        exits = set()
        for symbol in current_holdings:
            if self.check_exit_conditions(symbol):
                exits.add(symbol)

        # Check for entries
        entry_candidates = []
        for ticker, symbol in self.symbols.items():
            if symbol not in current_holdings and self.check_entry_conditions(symbol):
                # Score by accelerating momentum for ranking
                accel_mom = self.calculate_accel_momentum(symbol)
                if accel_mom is not None:
                    entry_candidates.append((symbol, accel_mom))

        # Sort by momentum (highest first)
        entry_candidates.sort(key=lambda x: x[1], reverse=True)

        # Calculate target positions
        remaining_holdings = current_holdings - exits
        available_slots = self.max_positions - len(remaining_holdings)

        # Select top candidates up to available slots
        new_entries = [s for s, _ in entry_candidates[:available_slots]]

        # Execute exits
        for symbol in exits:
            self.liquidate(symbol, "Exit signal")
            self.log(f"EXIT: {symbol}")

        # Calculate position size
        target_holdings = remaining_holdings.union(set(new_entries))
        num_positions = len(target_holdings)

        if num_positions < self.min_positions:
            # Not enough signals - hold cash
            self.log(f"Only {num_positions} signals - holding cash for remaining")

        if num_positions > 0:
            # Equal weight with max cap
            target_weight = min(1.0 / num_positions, self.max_position_pct)

            # Rebalance existing positions
            for symbol in target_holdings:
                current_weight = self.portfolio[symbol].holdings_value / self.portfolio.total_portfolio_value

                # Only rebalance if significantly off target (>2% difference)
                if abs(current_weight - target_weight) > 0.02 or symbol in new_entries:
                    self.set_holdings(symbol, target_weight)
                    if symbol in new_entries:
                        self.log(f"ENTRY: {symbol} at {target_weight*100:.1f}%")

        self.last_rebalance = self.time

    def on_data(self, data):
        """Required method - rebalancing happens on schedule"""
        pass
