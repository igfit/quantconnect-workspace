"""
Parameter Sweeper

Generates parameter variations of strategies for grid search optimization.
"""

import os
import copy
from typing import List, Dict, Any, Iterator
from itertools import product

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.strategy_spec import StrategySpec, ParameterRange
import config


class ParameterSweeper:
    """
    Generate parameter variations of a strategy.

    Takes a StrategySpec with ParameterRange definitions and generates
    all combinations for grid search.
    """

    def __init__(self, max_combinations: int = None):
        """
        Args:
            max_combinations: Maximum number of combinations to generate.
                             If exceeded, samples uniformly.
        """
        self.max_combinations = max_combinations or config.MAX_PARAMETER_COMBINATIONS

    def sweep(self, spec: StrategySpec) -> List[StrategySpec]:
        """
        Generate all parameter combinations for a strategy.

        Args:
            spec: Base strategy with parameter ranges defined

        Returns:
            List of StrategySpec variations
        """
        if not spec.parameters:
            return [spec]

        # Get all parameter paths and their values
        param_paths = [p.path for p in spec.parameters]
        param_values = [p.values for p in spec.parameters]

        # Calculate total combinations
        total_combinations = 1
        for values in param_values:
            total_combinations *= len(values)

        print(f"  Total possible combinations: {total_combinations}")

        # Generate combinations
        variations = []
        for combo in product(*param_values):
            # Create a copy of the spec
            new_spec = self._copy_spec(spec)
            new_spec.parent_id = spec.id

            # Apply parameter values
            for path, value in zip(param_paths, combo):
                self._set_nested_value(new_spec, path, value)

            # Update name to reflect parameters
            param_str = "_".join(f"{p.split('.')[-1]}={v}" for p, v in zip(param_paths, combo))
            new_spec.name = f"{spec.name} ({param_str})"

            variations.append(new_spec)

            # Check max combinations
            if len(variations) >= self.max_combinations:
                print(f"  Limiting to {self.max_combinations} combinations")
                break

        return variations

    def _copy_spec(self, spec: StrategySpec) -> StrategySpec:
        """Create a deep copy of a strategy spec"""
        return StrategySpec.from_dict(spec.to_dict())

    def _set_nested_value(self, spec: StrategySpec, path: str, value: Any):
        """
        Set a nested value in the spec using dot notation.

        Example paths:
            - "indicators.0.params.period"
            - "entry_conditions.conditions.0.right"
            - "risk_management.stop_loss_pct"
        """
        parts = path.split(".")
        obj = spec

        # Navigate to parent object
        for i, part in enumerate(parts[:-1]):
            if part.isdigit():
                idx = int(part)
                obj = obj[idx] if isinstance(obj, list) else getattr(obj, list(obj.__dict__.keys())[idx])
            elif isinstance(obj, dict):
                obj = obj[part]
            elif isinstance(obj, list):
                obj = obj[int(part)]
            elif hasattr(obj, part):
                attr = getattr(obj, part)
                if isinstance(attr, list) and i + 1 < len(parts) - 1 and parts[i + 1].isdigit():
                    obj = attr
                else:
                    obj = attr
            else:
                raise ValueError(f"Cannot navigate path: {path} at {part}")

        # Set the final value
        final_key = parts[-1]
        if isinstance(obj, dict):
            obj[final_key] = value
        elif isinstance(obj, list):
            obj[int(final_key)] = value
        elif hasattr(obj, final_key):
            setattr(obj, final_key, value)
        else:
            # Handle special cases
            if hasattr(obj, 'params') and isinstance(obj.params, dict):
                obj.params[final_key] = value
            else:
                raise ValueError(f"Cannot set value at path: {path}")


def sweep_parameters(spec: StrategySpec, max_combinations: int = None) -> List[StrategySpec]:
    """
    Convenience function to sweep parameters.

    Args:
        spec: Strategy spec with parameter ranges
        max_combinations: Max variations to generate

    Returns:
        List of strategy variations
    """
    sweeper = ParameterSweeper(max_combinations)
    return sweeper.sweep(spec)


def sweep_multiple(
    specs: List[StrategySpec],
    max_per_strategy: int = None
) -> List[StrategySpec]:
    """
    Sweep parameters for multiple strategies.

    Args:
        specs: List of base strategies
        max_per_strategy: Max variations per strategy

    Returns:
        List of all variations
    """
    all_variations = []
    sweeper = ParameterSweeper(max_per_strategy)

    for spec in specs:
        print(f"\nSweeping: {spec.name}")
        variations = sweeper.sweep(spec)
        print(f"  Generated {len(variations)} variations")
        all_variations.extend(variations)

    return all_variations


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    from models.strategy_spec import create_example_momentum_strategy

    print("="*60)
    print("Parameter Sweeper Test")
    print("="*60)

    # Create example strategy
    spec = create_example_momentum_strategy()
    print(f"\nBase strategy: {spec.name}")
    print(f"Parameters: {[(p.path, p.values) for p in spec.parameters]}")

    # Sweep
    sweeper = ParameterSweeper(max_combinations=20)
    variations = sweeper.sweep(spec)

    print(f"\nGenerated {len(variations)} variations:")
    for v in variations[:10]:
        print(f"  - {v.name}")
        # Show indicator params
        for ind in v.indicators:
            print(f"      {ind.name}: {ind.params}")

    if len(variations) > 10:
        print(f"  ... and {len(variations) - 10} more")
