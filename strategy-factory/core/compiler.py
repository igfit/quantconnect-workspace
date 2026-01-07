"""
Strategy Compiler

Converts StrategySpec objects into QuantConnect Python code.
Injects all safety guards from the base algorithm template.
"""

import re
from typing import Dict, Any, List, Tuple
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.strategy_spec import (
    StrategySpec, IndicatorSpec, Condition, ConditionGroup,
    Operator, Logic, Timeframe, UniverseType
)
from templates.base_algorithm import get_template
import config


class StrategyCompiler:
    """Compiles StrategySpec to QuantConnect Python code"""

    def __init__(self):
        self.template = get_template()

    def compile(
        self,
        spec: StrategySpec,
        start_date: str = None,
        end_date: str = None,
        initial_capital: float = None,
    ) -> str:
        """
        Compile a StrategySpec to QuantConnect Python code.

        Args:
            spec: The strategy specification
            start_date: Override start date (YYYY-MM-DD)
            end_date: Override end date (YYYY-MM-DD)
            initial_capital: Override initial capital

        Returns:
            Complete Python code string for QuantConnect
        """
        # Validate spec first
        errors = spec.validate()
        if errors:
            raise ValueError(f"Invalid strategy spec: {errors}")

        # Parse dates
        if start_date is None:
            start_date = config.DATE_RANGES[config.ACTIVE_DATE_RANGE]["full"][0]
        if end_date is None:
            end_date = config.DATE_RANGES[config.ACTIVE_DATE_RANGE]["full"][1]

        start_year, start_month, start_day = self._parse_date(start_date)
        end_year, end_month, end_day = self._parse_date(end_date)

        # Initial capital
        if initial_capital is None:
            initial_capital = config.DEFAULT_INITIAL_CAPITAL

        # Generate class name
        class_name = self._generate_class_name(spec.name)

        # Generate code sections
        universe_code = self._generate_universe_code(spec)
        indicator_code = self._generate_indicator_code(spec)
        entry_conditions_code = self._generate_conditions_code(spec.entry_conditions, spec)
        exit_conditions_code = self._generate_conditions_code(spec.exit_conditions, spec)

        # Calculate warmup period
        warmup_period = spec.get_max_indicator_period() + config.WARMUP_BUFFER_DAYS

        # Risk management values
        stop_loss = spec.risk_management.stop_loss_pct
        take_profit = spec.risk_management.take_profit_pct
        max_holding = spec.risk_management.max_holding_days

        # Format the template
        code = self.template.format(
            class_name=class_name,
            strategy_name=spec.name,
            description=spec.description,
            rationale=spec.rationale,
            strategy_id=spec.id,
            start_year=start_year,
            start_month=start_month,
            start_day=start_day,
            end_year=end_year,
            end_month=end_month,
            end_day=end_day,
            initial_capital=int(initial_capital),
            slippage_percent=config.SLIPPAGE_PERCENT,
            universe_code=universe_code,
            indicator_code=indicator_code,
            position_size_dollars=spec.risk_management.position_size_dollars,
            stop_loss_pct=f"{stop_loss}" if stop_loss else "None",
            take_profit_pct=f"{take_profit}" if take_profit else "None",
            max_holding_days=f"{max_holding}" if max_holding else "None",
            warmup_period=warmup_period,
            min_price=config.MIN_PRICE,
            min_dollar_volume=config.MIN_DOLLAR_VOLUME,
            entry_conditions_code=entry_conditions_code,
            exit_conditions_code=exit_conditions_code,
        )

        return code

    def _parse_date(self, date_str: str) -> Tuple[int, int, int]:
        """Parse YYYY-MM-DD to (year, month, day)"""
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.year, dt.month, dt.day

    def _generate_class_name(self, name: str) -> str:
        """Generate a valid Python class name from strategy name"""
        # Remove non-alphanumeric characters and convert to CamelCase
        words = re.sub(r'[^a-zA-Z0-9\s]', '', name).split()
        class_name = ''.join(word.capitalize() for word in words)
        if not class_name:
            class_name = "GeneratedStrategy"
        # Ensure it starts with a letter
        if class_name[0].isdigit():
            class_name = "Strategy" + class_name
        return class_name

    def _generate_universe_code(self, spec: StrategySpec) -> str:
        """Generate universe setup code"""
        lines = []

        if spec.universe.type == UniverseType.STATIC:
            # Static universe - add specific symbols
            symbols_str = ", ".join(f'"{s}"' for s in spec.universe.symbols)
            lines.append(f"# Static universe")
            lines.append(f"for ticker in [{symbols_str}]:")
            lines.append(f"    equity = self.add_equity(ticker, Resolution.DAILY)")
            lines.append(f"    self.symbols.append(equity.symbol)")
        else:
            # Dynamic universe - use coarse selection
            # For now, fall back to a default set if dynamic
            # Full dynamic universe would require more complex implementation
            lines.append(f"# Dynamic universe (simplified to liquid stocks)")
            lines.append(f"# TODO: Implement full coarse/fine universe selection")
            default_symbols = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META"]
            symbols_str = ", ".join(f'"{s}"' for s in default_symbols)
            lines.append(f"for ticker in [{symbols_str}]:")
            lines.append(f"    equity = self.add_equity(ticker, Resolution.DAILY)")
            lines.append(f"    self.symbols.append(equity.symbol)")

        return "\n        ".join(lines)

    def _generate_indicator_code(self, spec: StrategySpec) -> str:
        """Generate indicator initialization code"""
        lines = []

        for ind in spec.indicators:
            lines.append(f"# Indicator: {ind.name} ({ind.type})")
            lines.append(f"for symbol in self.symbols:")
            lines.append(f"    if symbol not in self.indicators:")
            lines.append(f"        self.indicators[symbol] = {{}}")

            qc_class = config.INDICATOR_MAPPING.get(ind.type, ind.type)

            # Build parameters
            if ind.type == "SMA":
                period = ind.params.get("period", 20)
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.sma(symbol, {period}, Resolution.DAILY)")

            elif ind.type == "EMA":
                period = ind.params.get("period", 20)
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.ema(symbol, {period}, Resolution.DAILY)")

            elif ind.type == "RSI":
                period = ind.params.get("period", 14)
                # RSI requires: symbol, period, MovingAverageType, resolution
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.rsi(symbol, {period}, MovingAverageType.WILDERS, Resolution.DAILY)")

            elif ind.type == "MACD":
                fast = ind.params.get("fast_period", 12)
                slow = ind.params.get("slow_period", 26)
                signal = ind.params.get("signal_period", 9)
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.macd(symbol, {fast}, {slow}, {signal}, Resolution.DAILY)")

            elif ind.type == "ADX":
                period = ind.params.get("period", 14)
                # ADX shortcut: symbol, period, resolution
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.adx(symbol, {period})")

            elif ind.type == "ATR":
                period = ind.params.get("period", 14)
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.atr(symbol, {period}, Resolution.DAILY)")

            elif ind.type == "BB":
                period = ind.params.get("period", 20)
                k = ind.params.get("k", 2)
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.bb(symbol, {period}, {k}, Resolution.DAILY)")

            elif ind.type == "ROC":
                period = ind.params.get("period", 14)
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.roc(symbol, {period}, Resolution.DAILY)")

            elif ind.type == "MOM":
                period = ind.params.get("period", 14)
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.mom(symbol, {period}, Resolution.DAILY)")

            elif ind.type == "STOCH":
                period = ind.params.get("period", 14)
                k_period = ind.params.get("k_period", 3)
                d_period = ind.params.get("d_period", 3)
                lines.append(f"    self.indicators[symbol]['{ind.name}'] = self.sto(symbol, {period}, {k_period}, {d_period}, Resolution.DAILY)")

            else:
                # Generic fallback
                period = ind.params.get("period", 14)
                lines.append(f"    # Unknown indicator type: {ind.type}")
                lines.append(f"    # self.indicators[symbol]['{ind.name}'] = ...")

            lines.append("")

        return "\n        ".join(lines)

    def _generate_conditions_code(self, cond_group: ConditionGroup, spec: StrategySpec) -> str:
        """Generate condition checking code"""
        if not cond_group.conditions:
            return "return False"

        condition_strs = []
        for cond in cond_group.conditions:
            cond_str = self._generate_single_condition(cond)
            condition_strs.append(cond_str)

        # Join with AND or OR
        joiner = " and " if cond_group.logic == Logic.AND else " or "
        combined = joiner.join(f"({c})" for c in condition_strs)

        return f"return {combined}"

    def _generate_single_condition(self, cond: Condition) -> str:
        """Generate code for a single condition"""
        left = cond.left
        right = cond.right
        op = cond.operator

        # Format right side
        if isinstance(right, (int, float)):
            right_str = str(right)
        else:
            right_str = f'"{right}"'

        if op == Operator.CROSSES_ABOVE:
            return f'self._crosses_above(symbol, "{left}", {right_str})'
        elif op == Operator.CROSSES_BELOW:
            return f'self._crosses_below(symbol, "{left}", {right_str})'
        else:
            # Standard comparison
            left_val = f'self._get_indicator_value(symbol, "{left}")'
            if isinstance(right, (int, float)):
                right_val = str(right)
            else:
                right_val = f'self._get_indicator_value(symbol, "{right}")'

            op_str = op.value if isinstance(op, Operator) else op
            return f'{left_val} {op_str} {right_val}'


def compile_strategy(
    spec: StrategySpec,
    start_date: str = None,
    end_date: str = None,
    initial_capital: float = None,
) -> str:
    """
    Convenience function to compile a strategy spec.

    Args:
        spec: The strategy specification
        start_date: Override start date (YYYY-MM-DD)
        end_date: Override end date (YYYY-MM-DD)
        initial_capital: Override initial capital

    Returns:
        Complete Python code string for QuantConnect
    """
    compiler = StrategyCompiler()
    return compiler.compile(spec, start_date, end_date, initial_capital)


def save_compiled_strategy(spec: StrategySpec, code: str) -> str:
    """
    Save compiled strategy code to file.

    Returns the filepath.
    """
    filepath = os.path.join(config.COMPILED_DIR, f"{spec.id}.py")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f:
        f.write(code)
    return filepath


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test compilation with example strategy
    from models.strategy_spec import create_example_momentum_strategy

    spec = create_example_momentum_strategy()
    print(f"Compiling strategy: {spec.name}")
    print(f"Validation errors: {spec.validate()}")

    compiler = StrategyCompiler()
    code = compiler.compile(spec)

    print("\n" + "="*60)
    print("GENERATED CODE:")
    print("="*60)
    print(code)

    # Save to file
    filepath = save_compiled_strategy(spec, code)
    print(f"\nSaved to: {filepath}")
