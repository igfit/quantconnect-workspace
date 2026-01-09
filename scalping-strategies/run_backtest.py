#!/usr/bin/env python3
"""
Backtest Runner for Scalping Strategies

Compiles strategy specs and runs backtests via QuantConnect API.
Supports walk-forward analysis for hindsight bias prevention.

Usage:
    # Single strategy, training period
    python run_backtest.py --strategy rsi2_pullback --period train

    # Walk-forward analysis (all periods)
    python run_backtest.py --strategy rsi2_pullback --walk-forward

    # Compare all strategies
    python run_backtest.py --compare-all --period train

    # Just compile (no backtest)
    python run_backtest.py --strategy rsi2_pullback --compile-only
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.strategy_spec import (
    StrategySpec,
    create_rsi2_pullback_spec,
    create_connors_rsi_spec,
    create_bollinger_mean_reversion_spec,
    create_pairs_trading_spec,
    create_gap_fade_spec,
    create_vwap_reversion_spec,
)
from core.compiler import compile_strategy, save_compiled_strategy
from config import BACKTEST_PERIODS, COMPILED_DIR, SPECS_DIR, BACKTESTS_DIR


# =============================================================================
# STRATEGY REGISTRY
# =============================================================================

STRATEGY_REGISTRY: Dict[str, callable] = {
    "rsi2_pullback": create_rsi2_pullback_spec,
    "connors_rsi": create_connors_rsi_spec,
    "bollinger_mr": create_bollinger_mean_reversion_spec,
    "pairs_nvda_amd": lambda: create_pairs_trading_spec("AMD", "NVDA"),
    "gap_fade": create_gap_fade_spec,
    "vwap_reversion": create_vwap_reversion_spec,
}


def list_strategies() -> List[str]:
    """List all available strategies"""
    return list(STRATEGY_REGISTRY.keys())


def get_strategy_spec(name: str) -> StrategySpec:
    """Get strategy spec by name"""
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy: {name}. Available: {list_strategies()}")
    return STRATEGY_REGISTRY[name]()


# =============================================================================
# COMPILATION
# =============================================================================

def compile_and_save(
    strategy_name: str,
    period: str = "train",
    save: bool = True
) -> tuple:
    """
    Compile a strategy and optionally save to disk.

    Returns:
        Tuple of (spec, code, filepath)
    """
    spec = get_strategy_spec(strategy_name)

    print(f"\nCompiling: {spec.name}")
    print(f"  Type: {spec.strategy_type.value}")
    print(f"  Resolution: {spec.resolution.value}")
    print(f"  Universe: {spec.symbols}")
    print(f"  Period: {period} ({BACKTEST_PERIODS[period]['start']} to {BACKTEST_PERIODS[period]['end']})")

    # Validate
    errors = spec.validate()
    if errors:
        print(f"  Validation FAILED: {errors}")
        return None, None, None

    # Compile
    code = compile_strategy(spec, period=period)

    filepath = None
    if save:
        filepath = save_compiled_strategy(spec, code)
        print(f"  Saved to: {filepath}")

        # Also save spec
        os.makedirs(SPECS_DIR, exist_ok=True)
        spec_path = os.path.join(SPECS_DIR, f"{spec.id}.json")
        with open(spec_path, 'w') as f:
            f.write(spec.to_json())
        print(f"  Spec saved to: {spec_path}")

    return spec, code, filepath


# =============================================================================
# WALK-FORWARD ANALYSIS
# =============================================================================

def walk_forward_compile(strategy_name: str) -> Dict[str, str]:
    """
    Compile strategy for all walk-forward periods.

    Returns dict of period -> filepath
    """
    results = {}

    for period in ["train", "test", "validate"]:
        spec, code, filepath = compile_and_save(strategy_name, period=period, save=True)
        if filepath:
            # Rename with period suffix
            new_path = filepath.replace(".py", f"_{period}.py")
            os.rename(filepath, new_path)
            results[period] = new_path

    return results


# =============================================================================
# BACKTEST EXECUTION (via QC API)
# =============================================================================

def run_backtest_qc(
    filepath: str,
    project_name: str = None
) -> Optional[Dict]:
    """
    Run backtest via QuantConnect API.

    This is a placeholder - actual implementation would:
    1. Create/get QC project
    2. Push compiled code
    3. Compile on QC
    4. Run backtest
    5. Fetch and return results

    For now, prints instructions.
    """
    print(f"\n{'='*60}")
    print("BACKTEST EXECUTION")
    print("="*60)
    print(f"\nCompiled strategy: {filepath}")
    print("\nTo run on QuantConnect:")
    print(f"  1. Create project: ./scripts/qc-api.sh project-create \"{project_name or 'Scalping Strategy'}\" Py")
    print(f"  2. Push code: ./scripts/qc-api.sh push <projectId> {filepath} main.py")
    print(f"  3. Compile: ./scripts/qc-api.sh compile <projectId>")
    print(f"  4. Backtest: ./scripts/qc-api.sh backtest <projectId> \"Test Run\" <compileId>")
    print(f"  5. Results: ./scripts/qc-api.sh results <projectId> <backtestId>")
    print(f"\nOr copy the code to QuantConnect web IDE for interactive testing.")

    return None


# =============================================================================
# RESULTS ANALYSIS
# =============================================================================

def analyze_results(results: Dict) -> Dict:
    """
    Analyze backtest results and check against success criteria.

    Returns analysis dict with pass/fail for each metric.
    """
    from config import (
        TARGET_SHARPE, TARGET_CAGR, TARGET_MAX_DRAWDOWN,
        TARGET_WIN_RATE, TARGET_PROFIT_FACTOR,
        MIN_TRADES_FOR_SIGNIFICANCE
    )

    analysis = {
        "passed": True,
        "metrics": {},
        "warnings": [],
    }

    # Check each metric
    if "sharpe" in results:
        passed = results["sharpe"] >= TARGET_SHARPE
        analysis["metrics"]["sharpe"] = {
            "value": results["sharpe"],
            "target": TARGET_SHARPE,
            "passed": passed,
        }
        if not passed:
            analysis["passed"] = False

    if "cagr" in results:
        passed = results["cagr"] >= TARGET_CAGR
        analysis["metrics"]["cagr"] = {
            "value": results["cagr"],
            "target": TARGET_CAGR,
            "passed": passed,
        }
        if not passed:
            analysis["passed"] = False

    if "max_drawdown" in results:
        passed = results["max_drawdown"] <= TARGET_MAX_DRAWDOWN
        analysis["metrics"]["max_drawdown"] = {
            "value": results["max_drawdown"],
            "target": TARGET_MAX_DRAWDOWN,
            "passed": passed,
        }
        if not passed:
            analysis["passed"] = False

    if "trades" in results:
        if results["trades"] < MIN_TRADES_FOR_SIGNIFICANCE:
            analysis["warnings"].append(
                f"Only {results['trades']} trades - below {MIN_TRADES_FOR_SIGNIFICANCE} for statistical significance"
            )

    return analysis


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Scalping Strategy Backtest Runner")

    parser.add_argument(
        "--strategy", "-s",
        type=str,
        help="Strategy name to run"
    )
    parser.add_argument(
        "--period", "-p",
        type=str,
        default="train",
        choices=["train", "test", "validate", "full"],
        help="Backtest period (default: train)"
    )
    parser.add_argument(
        "--walk-forward", "-w",
        action="store_true",
        help="Run walk-forward analysis (all periods)"
    )
    parser.add_argument(
        "--compare-all",
        action="store_true",
        help="Compare all strategies"
    )
    parser.add_argument(
        "--compile-only", "-c",
        action="store_true",
        help="Only compile, don't run backtest"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available strategies"
    )

    args = parser.parse_args()

    # List strategies
    if args.list:
        print("\nAvailable Strategies:")
        print("-" * 40)
        for name in list_strategies():
            spec = get_strategy_spec(name)
            print(f"  {name:20} - {spec.strategy_type.value}")
        return

    # Compare all
    if args.compare_all:
        print("\nCompiling all strategies for comparison...")
        for name in list_strategies():
            compile_and_save(name, period=args.period)
        return

    # Single strategy
    if not args.strategy:
        parser.print_help()
        print("\n\nError: --strategy is required (or use --list to see options)")
        return

    # Walk-forward analysis
    if args.walk_forward:
        print(f"\n{'='*60}")
        print(f"WALK-FORWARD ANALYSIS: {args.strategy}")
        print("="*60)
        results = walk_forward_compile(args.strategy)
        print("\nCompiled files:")
        for period, path in results.items():
            print(f"  {period}: {path}")
        return

    # Standard compile
    spec, code, filepath = compile_and_save(args.strategy, period=args.period)

    if not args.compile_only and filepath:
        run_backtest_qc(filepath, project_name=spec.name if spec else None)


if __name__ == "__main__":
    main()
