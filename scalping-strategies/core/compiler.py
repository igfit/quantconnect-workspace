"""
Strategy Compiler

Compiles StrategySpec objects into QuantConnect Python code.
Supports multiple resolutions (minute, hour, daily) unlike the daily-only strategy-factory.
"""

import re
import os
from typing import Dict, Any, List, Tuple
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.strategy_spec import (
    StrategySpec, IndicatorSpec, Condition, ConditionGroup,
    Operator, Logic, StrategyType
)
from config import (
    Resolution, BACKTEST_PERIODS, ACTIVE_PERIOD,
    DEFAULT_INITIAL_CAPITAL, SLIPPAGE_BY_RESOLUTION,
    WARMUP_BUFFER_DAYS, COMPILED_DIR
)


class StrategyCompiler:
    """Compiles StrategySpec to QuantConnect Python code with resolution support"""

    def compile(
        self,
        spec: StrategySpec,
        period: str = None,
        initial_capital: float = None,
    ) -> str:
        """
        Compile a StrategySpec to QuantConnect Python code.

        Args:
            spec: The strategy specification
            period: Backtest period key (train/test/validate/full)
            initial_capital: Override initial capital

        Returns:
            Complete Python code string for QuantConnect
        """
        # Validate spec first
        errors = spec.validate()
        if errors:
            raise ValueError(f"Invalid strategy spec: {errors}")

        # Get dates from period
        if period is None:
            period = ACTIVE_PERIOD
        period_config = BACKTEST_PERIODS[period]
        start_date = period_config["start"]
        end_date = period_config["end"]

        start_year, start_month, start_day = self._parse_date(start_date)
        end_year, end_month, end_day = self._parse_date(end_date)

        # Initial capital
        if initial_capital is None:
            initial_capital = DEFAULT_INITIAL_CAPITAL

        # Get slippage for resolution
        slippage = SLIPPAGE_BY_RESOLUTION.get(spec.resolution, 0.001)

        # Generate class name
        class_name = self._generate_class_name(spec.name)

        # Calculate warmup period
        warmup_period = self._calculate_warmup(spec)

        # Generate the code
        code = self._generate_code(
            spec=spec,
            class_name=class_name,
            start_year=start_year,
            start_month=start_month,
            start_day=start_day,
            end_year=end_year,
            end_month=end_month,
            end_day=end_day,
            initial_capital=initial_capital,
            slippage=slippage,
            warmup_period=warmup_period,
        )

        return code

    def _parse_date(self, date_str: str) -> Tuple[int, int, int]:
        """Parse YYYY-MM-DD to (year, month, day)"""
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.year, dt.month, dt.day

    def _generate_class_name(self, name: str) -> str:
        """Generate a valid Python class name from strategy name"""
        words = re.sub(r'[^a-zA-Z0-9\s]', '', name).split()
        class_name = ''.join(word.capitalize() for word in words)
        if not class_name:
            class_name = "GeneratedStrategy"
        if class_name[0].isdigit():
            class_name = "Strategy" + class_name
        return class_name

    def _calculate_warmup(self, spec: StrategySpec) -> int:
        """Calculate warmup period based on indicators and resolution"""
        max_period = spec.get_max_indicator_period()

        # Adjust for resolution
        if spec.resolution == Resolution.MINUTE:
            # For minute data, need more bars for same time period
            return max_period + WARMUP_BUFFER_DAYS * 390
        elif spec.resolution == Resolution.HOUR:
            return max_period + WARMUP_BUFFER_DAYS * 7
        else:
            return max_period + WARMUP_BUFFER_DAYS

    def _generate_code(
        self,
        spec: StrategySpec,
        class_name: str,
        start_year: int,
        start_month: int,
        start_day: int,
        end_year: int,
        end_month: int,
        end_day: int,
        initial_capital: float,
        slippage: float,
        warmup_period: int,
    ) -> str:
        """Generate the complete algorithm code"""

        # Resolution string
        resolution_str = spec.resolution.value  # e.g., "Resolution.DAILY"

        # Generate sections
        universe_code = self._generate_universe_code(spec, resolution_str)
        indicator_code = self._generate_indicator_code(spec, resolution_str)
        entry_logic = self._generate_entry_logic(spec)
        exit_logic = self._generate_exit_logic(spec)
        custom_indicators = self._generate_custom_indicator_code(spec)

        # Risk management
        rm = spec.risk_management
        stop_loss_code = f"{rm.stop_loss_pct}" if rm.stop_loss_pct else "None"
        take_profit_code = f"{rm.take_profit_pct}" if rm.take_profit_pct else "None"
        max_holding_code = f"{rm.max_holding_days}" if rm.max_holding_days else "None"

        code = f'''"""
{spec.name}

{spec.description}

Rationale:
{spec.rationale}

Strategy Type: {spec.strategy_type.value}
Resolution: {resolution_str}
Generated: {datetime.now().isoformat()}
Strategy ID: {spec.id}
"""

from AlgorithmImports import *
import numpy as np
from collections import deque


class {class_name}(QCAlgorithm):
    """
    {spec.name}

    {spec.description}
    """

    def initialize(self):
        # Backtest period
        self.set_start_date({start_year}, {start_month}, {start_day})
        self.set_end_date({end_year}, {end_month}, {end_day})
        self.set_cash({int(initial_capital)})

        # Strategy parameters
        self.strategy_id = "{spec.id}"
        self.resolution = {resolution_str}

        # Risk management
        self.position_size_dollars = {rm.position_size_dollars}
        self.risk_per_trade = {rm.risk_per_trade_pct}
        self.stop_loss_pct = {stop_loss_code}
        self.take_profit_pct = {take_profit_code}
        self.max_holding_days = {max_holding_code}
        self.max_positions = {rm.max_positions}

        # Track positions
        self.entry_prices = {{}}
        self.entry_times = {{}}
        self.positions_count = 0

        # Universe and indicators
        self.symbols = []
        self.indicators = {{}}
        self.prev_values = {{}}

        # Setup universe
        {universe_code}

        # Setup indicators
        {indicator_code}

        # Slippage model (resolution-appropriate)
        for symbol in self.symbols:
            security = self.securities[symbol]
            security.set_slippage_model(ConstantSlippageModel({slippage}))
            security.set_fee_model(InteractiveBrokersFeeModel())

        # Warmup
        self.set_warm_up({warmup_period}, self.resolution)

        # Benchmark
        if "SPY" not in [str(s) for s in self.symbols]:
            self.add_equity("SPY", self.resolution)
        self.set_benchmark("SPY")

        # Schedule daily check for time-based exits
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.before_market_close("SPY", 5),
            self.check_time_exits
        )

{custom_indicators}

    def on_data(self, data):
        """Main trading logic"""
        if self.is_warming_up:
            return

        for symbol in self.symbols:
            if symbol not in data or data[symbol] is None:
                continue

            # Check if we should exit existing position
            if self.portfolio[symbol].invested:
                if self._should_exit(symbol, data):
                    self._exit_position(symbol, "Signal exit")

            # Check if we should enter new position
            elif self.positions_count < self.max_positions:
                if self._should_enter(symbol, data):
                    self._enter_position(symbol, data)

            # Update previous values for crossover detection
            self._update_prev_values(symbol)

    def _should_enter(self, symbol, data) -> bool:
        """Check entry conditions"""
        if not self._all_indicators_ready(symbol):
            return False

        try:
{entry_logic}
        except Exception as e:
            self.debug(f"Entry check error for {{symbol}}: {{e}}")
            return False

    def _should_exit(self, symbol, data) -> bool:
        """Check exit conditions"""
        if not self._all_indicators_ready(symbol):
            return False

        # Check stop loss
        if self.stop_loss_pct and symbol in self.entry_prices:
            entry = self.entry_prices[symbol]
            current = data[symbol].close
            if current < entry * (1 - self.stop_loss_pct):
                self.debug(f"{{symbol}}: Stop loss triggered")
                return True

        # Check take profit
        if self.take_profit_pct and symbol in self.entry_prices:
            entry = self.entry_prices[symbol]
            current = data[symbol].close
            if current > entry * (1 + self.take_profit_pct):
                self.debug(f"{{symbol}}: Take profit triggered")
                return True

        try:
{exit_logic}
        except Exception as e:
            self.debug(f"Exit check error for {{symbol}}: {{e}}")
            return False

    def _enter_position(self, symbol, data):
        """Enter a new position"""
        price = data[symbol].close
        shares = int(self.position_size_dollars / price)

        if shares > 0:
            self.market_order(symbol, shares)
            self.entry_prices[symbol] = price
            self.entry_times[symbol] = self.time
            self.positions_count += 1
            self.debug(f"ENTRY: {{symbol}} @ ${{price:.2f}}, {{shares}} shares")

    def _exit_position(self, symbol, reason: str):
        """Exit an existing position"""
        if self.portfolio[symbol].invested:
            self.liquidate(symbol)
            entry = self.entry_prices.get(symbol, 0)
            pnl = (self.portfolio[symbol].price - entry) / entry * 100 if entry > 0 else 0
            self.debug(f"EXIT: {{symbol}} ({{reason}}), P&L: {{pnl:.1f}}%")

            # Cleanup
            if symbol in self.entry_prices:
                del self.entry_prices[symbol]
            if symbol in self.entry_times:
                del self.entry_times[symbol]
            self.positions_count = max(0, self.positions_count - 1)

    def check_time_exits(self):
        """Check for time-based exits"""
        if self.max_holding_days is None:
            return

        for symbol in list(self.entry_times.keys()):
            if symbol in self.entry_times:
                days_held = (self.time - self.entry_times[symbol]).days
                if days_held >= self.max_holding_days:
                    self._exit_position(symbol, f"Time stop ({{days_held}} days)")

    def _all_indicators_ready(self, symbol) -> bool:
        """Check if all indicators are ready"""
        if symbol not in self.indicators:
            return False
        for name, ind in self.indicators[symbol].items():
            if hasattr(ind, 'is_ready') and not ind.is_ready:
                return False
        return True

    def _get_indicator_value(self, symbol, name: str):
        """Get current value of an indicator"""
        if symbol not in self.indicators:
            return None
        if name not in self.indicators[symbol]:
            # Check for special indicators
            if name == "price":
                return self.securities[symbol].price
            elif name == "bb_lower":
                bb = self.indicators[symbol].get("bb")
                return bb.lower_band.current.value if bb else None
            elif name == "bb_middle":
                bb = self.indicators[symbol].get("bb")
                return bb.middle_band.current.value if bb else None
            elif name == "bb_upper":
                bb = self.indicators[symbol].get("bb")
                return bb.upper_band.current.value if bb else None
            return None

        ind = self.indicators[symbol][name]
        if hasattr(ind, 'current'):
            return ind.current.value
        return ind

    def _get_prev_value(self, symbol, name: str):
        """Get previous value for crossover detection"""
        if symbol not in self.prev_values:
            return None
        return self.prev_values[symbol].get(name)

    def _update_prev_values(self, symbol):
        """Store current values for next bar's crossover detection"""
        if symbol not in self.prev_values:
            self.prev_values[symbol] = {{}}

        if symbol in self.indicators:
            for name, ind in self.indicators[symbol].items():
                if hasattr(ind, 'current'):
                    self.prev_values[symbol][name] = ind.current.value

    def _crosses_above(self, symbol, ind_name: str, threshold) -> bool:
        """Check if indicator crosses above threshold"""
        current = self._get_indicator_value(symbol, ind_name)
        prev = self._get_prev_value(symbol, ind_name)
        if current is None or prev is None:
            return False

        if isinstance(threshold, str):
            threshold = self._get_indicator_value(symbol, threshold)
            if threshold is None:
                return False

        return prev < threshold and current >= threshold

    def _crosses_below(self, symbol, ind_name: str, threshold) -> bool:
        """Check if indicator crosses below threshold"""
        current = self._get_indicator_value(symbol, ind_name)
        prev = self._get_prev_value(symbol, ind_name)
        if current is None or prev is None:
            return False

        if isinstance(threshold, str):
            threshold = self._get_indicator_value(symbol, threshold)
            if threshold is None:
                return False

        return prev >= threshold and current < threshold

    def on_end_of_algorithm(self):
        """Log final results"""
        self.log(f"Strategy: {{self.strategy_id}}")
        self.log(f"Final Portfolio Value: ${{self.portfolio.total_portfolio_value:,.2f}}")
'''

        return code

    def _generate_universe_code(self, spec: StrategySpec, resolution_str: str) -> str:
        """Generate universe setup code"""
        symbols_str = ", ".join(f'"{s}"' for s in spec.symbols)

        return f'''for ticker in [{symbols_str}]:
            equity = self.add_equity(ticker, {resolution_str})
            self.symbols.append(equity.symbol)'''

    def _generate_indicator_code(self, spec: StrategySpec, resolution_str: str) -> str:
        """Generate indicator initialization code"""
        lines = []

        for ind in spec.indicators:
            lines.append(f"# {ind.name}: {ind.type}")
            lines.append("for symbol in self.symbols:")
            lines.append("    if symbol not in self.indicators:")
            lines.append("        self.indicators[symbol] = {}")

            if ind.type == "SMA":
                period = ind.params.get("period", 20)
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.sma(symbol, {period}, {resolution_str})")

            elif ind.type == "EMA":
                period = ind.params.get("period", 20)
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.ema(symbol, {period}, {resolution_str})")

            elif ind.type == "RSI":
                period = ind.params.get("period", 14)
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.rsi(symbol, {period}, MovingAverageType.WILDERS, {resolution_str})")

            elif ind.type == "BB":
                period = ind.params.get("period", 20)
                k = ind.params.get("k", 2)
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.bb(symbol, {period}, {k}, {resolution_str})")

            elif ind.type == "ATR":
                period = ind.params.get("period", 14)
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.atr(symbol, {period}, MovingAverageType.SIMPLE, {resolution_str})")

            elif ind.type == "MACD":
                fast = ind.params.get("fast_period", 12)
                slow = ind.params.get("slow_period", 26)
                signal = ind.params.get("signal_period", 9)
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.macd(symbol, {fast}, {slow}, {signal}, {resolution_str})")

            elif ind.type == "VWAP":
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.vwap(symbol, {resolution_str})")

            elif ind.type == "CONNORS_RSI":
                # Custom indicator - will be calculated in on_data
                rsi_period = ind.params.get("rsi_period", 3)
                streak_period = ind.params.get("streak_period", 2)
                rank_period = ind.params.get("rank_period", 100)
                lines.append(f"    # Connors RSI - custom calculation")
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = ConnorsRSI({rsi_period}, {streak_period}, {rank_period})")
                lines.append(f"    self.indicators[symbol]['_rsi_for_connors'] = self.rsi(symbol, {rsi_period}, MovingAverageType.WILDERS, {resolution_str})")
                lines.append(f"    self.indicators[symbol]['_price_history'] = deque(maxlen={rank_period + 10})")

            elif ind.type in ["SPREAD_ZSCORE", "GAP", "VWAP_DEVIATION"]:
                # Custom indicators - handled separately
                lines.append(f"    # {ind.type} - custom calculation in on_data")
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = None")

            else:
                lines.append(f"    # Unknown indicator type: {ind.type}")

            lines.append("")

        return "\n        ".join(lines)

    def _generate_custom_indicator_code(self, spec: StrategySpec) -> str:
        """Generate custom indicator classes"""
        code = ""

        # Check if we need Connors RSI
        has_connors = any(ind.type == "CONNORS_RSI" for ind in spec.indicators)
        if has_connors:
            code += '''

class ConnorsRSI:
    """
    Connors RSI Composite Indicator

    Formula: (RSI(3) + StreakRSI(2) + PercentRank(100)) / 3
    """

    def __init__(self, rsi_period=3, streak_period=2, rank_period=100):
        self.rsi_period = rsi_period
        self.streak_period = streak_period
        self.rank_period = rank_period
        self.streak = 0
        self.prev_close = None
        self.closes = deque(maxlen=rank_period + 10)
        self.streak_history = deque(maxlen=streak_period + 10)
        self._current_value = 50  # Default neutral
        self.is_ready = False

    @property
    def current(self):
        class ValueHolder:
            def __init__(self, val):
                self.value = val
        return ValueHolder(self._current_value)

    def update(self, close: float, rsi_value: float):
        """Update with new close price and RSI value"""
        # Update streak
        if self.prev_close is not None:
            if close > self.prev_close:
                self.streak = max(1, self.streak + 1) if self.streak > 0 else 1
            elif close < self.prev_close:
                self.streak = min(-1, self.streak - 1) if self.streak < 0 else -1
            else:
                self.streak = 0

        self.prev_close = close
        self.closes.append(close)
        self.streak_history.append(self.streak)

        # Need enough data
        if len(self.closes) < self.rank_period:
            return

        self.is_ready = True

        # Calculate StreakRSI (RSI of streak values)
        streak_rsi = self._calculate_streak_rsi()

        # Calculate PercentRank
        percent_rank = self._calculate_percent_rank(close)

        # Connors RSI = average of three components
        self._current_value = (rsi_value + streak_rsi + percent_rank) / 3

    def _calculate_streak_rsi(self) -> float:
        """Calculate RSI of streak values"""
        if len(self.streak_history) < self.streak_period + 1:
            return 50

        streaks = list(self.streak_history)[-self.streak_period-1:]
        gains = []
        losses = []

        for i in range(1, len(streaks)):
            change = streaks[i] - streaks[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        avg_gain = sum(gains) / len(gains) if gains else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _calculate_percent_rank(self, close: float) -> float:
        """Calculate percent rank of current close"""
        closes = list(self.closes)
        if len(closes) < 2:
            return 50

        count_below = sum(1 for c in closes[:-1] if c < close)
        return (count_below / (len(closes) - 1)) * 100

'''

        return code

    def _generate_entry_logic(self, spec: StrategySpec) -> str:
        """Generate entry condition checking code"""
        if not spec.entry_conditions.conditions:
            return "            return False"

        condition_strs = []
        for cond in spec.entry_conditions.conditions:
            cond_str = self._condition_to_code(cond)
            condition_strs.append(f"({cond_str})")

        joiner = " and " if spec.entry_conditions.logic == Logic.AND else " or "
        combined = joiner.join(condition_strs)

        return f"            return {combined}"

    def _generate_exit_logic(self, spec: StrategySpec) -> str:
        """Generate exit condition checking code"""
        if not spec.exit_conditions.conditions:
            return "            return False"

        condition_strs = []
        for cond in spec.exit_conditions.conditions:
            cond_str = self._condition_to_code(cond)
            condition_strs.append(f"({cond_str})")

        joiner = " and " if spec.exit_conditions.logic == Logic.AND else " or "
        combined = joiner.join(condition_strs)

        return f"            return {combined}"

    def _condition_to_code(self, cond: Condition) -> str:
        """Convert a condition to Python code"""
        left = cond.left
        right = cond.right
        op = cond.operator

        if op == Operator.CROSSES_ABOVE:
            if isinstance(right, (int, float)):
                return f'self._crosses_above(symbol, "{left}", {right})'
            else:
                return f'self._crosses_above(symbol, "{left}", "{right}")'

        elif op == Operator.CROSSES_BELOW:
            if isinstance(right, (int, float)):
                return f'self._crosses_below(symbol, "{left}", {right})'
            else:
                return f'self._crosses_below(symbol, "{left}", "{right}")'

        else:
            # Standard comparison
            left_val = f'self._get_indicator_value(symbol, "{left}")'
            if isinstance(right, (int, float)):
                right_val = str(right)
            else:
                right_val = f'self._get_indicator_value(symbol, "{right}")'

            op_str = op.value
            return f'{left_val} {op_str} {right_val}'


def compile_strategy(
    spec: StrategySpec,
    period: str = None,
    initial_capital: float = None,
) -> str:
    """Convenience function to compile a strategy spec"""
    compiler = StrategyCompiler()
    return compiler.compile(spec, period, initial_capital)


def save_compiled_strategy(spec: StrategySpec, code: str) -> str:
    """Save compiled strategy code to file"""
    os.makedirs(COMPILED_DIR, exist_ok=True)
    filepath = os.path.join(COMPILED_DIR, f"{spec.id}.py")
    with open(filepath, 'w') as f:
        f.write(code)
    return filepath


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    from models.strategy_spec import create_rsi2_pullback_spec, create_connors_rsi_spec

    # Test RSI(2) Pullback
    spec = create_rsi2_pullback_spec()
    print(f"Compiling: {spec.name}")
    print(f"Resolution: {spec.resolution.value}")

    compiler = StrategyCompiler()
    code = compiler.compile(spec, period="train")

    print("\n" + "="*60)
    print("GENERATED CODE (first 100 lines):")
    print("="*60)
    for i, line in enumerate(code.split("\n")[:100]):
        print(line)

    # Save
    filepath = save_compiled_strategy(spec, code)
    print(f"\nSaved to: {filepath}")

    # Test Connors RSI
    spec2 = create_connors_rsi_spec()
    code2 = compiler.compile(spec2, period="train")
    filepath2 = save_compiled_strategy(spec2, code2)
    print(f"Saved Connors RSI to: {filepath2}")
