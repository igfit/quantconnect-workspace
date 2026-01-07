#!/usr/bin/env python3
"""
Strategy Validation Script

Runs each strategy and validates it executes correctly with trades.
Uses the improved verbose output and rate limiting.
"""

import os
import sys
import json
import time

# Add paths
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

from core.runner import QCRunner

# Strategy specs to validate
STRATEGIES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategies")
SPECS_DIR = os.path.join(STRATEGIES_DIR, "specs")
COMPILED_DIR = os.path.join(STRATEGIES_DIR, "compiled")


def load_spec(spec_id: str) -> dict:
    """Load a strategy spec by ID"""
    spec_file = os.path.join(SPECS_DIR, f"{spec_id}.json")
    if os.path.exists(spec_file):
        with open(spec_file) as f:
            return json.load(f)
    return None


def load_compiled_code(spec_id: str) -> str:
    """Load compiled code by spec ID"""
    code_file = os.path.join(COMPILED_DIR, f"{spec_id}.py")
    if os.path.exists(code_file):
        with open(code_file) as f:
            return f.read()
    return None


def validate_strategy(runner: QCRunner, spec_id: str, spec: dict, code: str) -> dict:
    """
    Run and validate a single strategy.

    Returns:
        Dict with validation results
    """
    print(f"\n{'='*60}")
    print(f"VALIDATING: {spec.get('name', spec_id)}")
    print(f"ID: {spec_id}")
    print(f"{'='*60}")

    # Show strategy config
    print(f"\nUniverse: {spec.get('universe', {}).get('symbols', [])}")
    print(f"Timeframe: {spec.get('timeframe', 'daily')}")
    print(f"Indicators: {[i['name'] for i in spec.get('indicators', [])]}")

    # Show entry conditions
    entry = spec.get('entry_conditions', {})
    print(f"Entry ({entry.get('logic', 'AND')}):")
    for cond in entry.get('conditions', []):
        print(f"  - {cond.get('left')} {cond.get('operator')} {cond.get('right')}")

    # Show exit conditions
    exit_conds = spec.get('exit_conditions', {})
    print(f"Exit ({exit_conds.get('logic', 'OR')}):")
    for cond in exit_conds.get('conditions', []):
        print(f"  - {cond.get('left')} {cond.get('operator')} {cond.get('right')}")

    print()

    # Run backtest
    try:
        result = runner.run_full_backtest(
            code=code,
            strategy_id=spec_id,
            backtest_name=f"validate_{spec_id}"
        )

        # Validate
        validation = runner.validate_strategy_execution(result)

        # Summary
        print(f"\n--- Results for {spec_id} ---")
        print(f"Status: {result.status}")
        print(f"Success: {result.success}")

        if result.success:
            stats = result.statistics
            print(f"Total Orders: {stats.get('Total Orders', 0)}")
            print(f"Sharpe Ratio: {stats.get('Sharpe Ratio', 'N/A')}")
            print(f"CAGR: {stats.get('Compounding Annual Return', 'N/A')}")
            print(f"Max Drawdown: {stats.get('Drawdown', 'N/A')}")
            print(f"Win Rate: {stats.get('Win Rate', 'N/A')}")

        if result.error:
            print(f"Error: {result.error}")

        if result.runtime_errors:
            print(f"Runtime Errors: {result.runtime_errors[:3]}")

        # Validation result
        print(f"\nValidation: {'PASS' if validation['valid'] else 'FAIL'}")
        if validation['issues']:
            print(f"Issues: {validation['issues']}")
        if validation.get('diagnostics', {}).get('possible_causes'):
            print(f"Possible causes: {validation['diagnostics']['possible_causes'][:3]}")

        return {
            'spec_id': spec_id,
            'name': spec.get('name'),
            'success': result.success,
            'valid': validation['valid'],
            'trades': int(str(result.statistics.get('Total Orders', 0)).replace(',', '') or 0) if result.success else 0,
            'sharpe': result.statistics.get('Sharpe Ratio') if result.success else None,
            'cagr': result.statistics.get('Compounding Annual Return') if result.success else None,
            'issues': validation['issues'],
            'error': result.error
        }

    except Exception as e:
        print(f"ERROR running strategy: {e}")
        import traceback
        traceback.print_exc()
        return {
            'spec_id': spec_id,
            'name': spec.get('name'),
            'success': False,
            'valid': False,
            'trades': 0,
            'error': str(e)
        }


def main():
    """Main validation routine"""
    print("="*60)
    print("STRATEGY VALIDATION SUITE")
    print("="*60)

    # Initialize runner with verbose output
    runner = QCRunner(verbose=True)

    # Test auth first
    print("\nTesting API authentication...")
    if not runner.test_auth():
        print("ERROR: Authentication failed!")
        return 1
    print("Authentication OK\n")

    # Get or create sandbox project
    print("Setting up sandbox project...")
    runner.get_or_create_sandbox_project("Strategy Validator")
    print(f"Using project ID: {runner.project_id}\n")

    # Find all specs
    spec_files = [f for f in os.listdir(SPECS_DIR) if f.endswith('.json')]
    print(f"Found {len(spec_files)} strategy specs")

    # Run validation for each
    results = []

    for spec_file in sorted(spec_files):
        spec_id = spec_file.replace('.json', '')

        # Load spec and code
        spec = load_spec(spec_id)
        code = load_compiled_code(spec_id)

        if not spec:
            print(f"\nSkipping {spec_id}: spec not found")
            continue

        if not code:
            print(f"\nSkipping {spec_id}: compiled code not found")
            continue

        # Run validation
        result = validate_strategy(runner, spec_id, spec, code)
        results.append(result)

        # Brief pause between strategies
        print("\nWaiting 5s before next strategy...")
        time.sleep(5)

    # Summary table
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    print(f"{'Strategy':<25} {'Valid':<8} {'Trades':<10} {'Sharpe':<10} {'CAGR':<15}")
    print("-"*80)

    passed = 0
    failed = 0

    for r in results:
        valid_str = "PASS" if r.get('valid') else "FAIL"
        trades = r.get('trades', 0)
        sharpe = r.get('sharpe', 'N/A')
        cagr = r.get('cagr', 'N/A')

        print(f"{r.get('spec_id', 'unknown'):<25} {valid_str:<8} {trades:<10} {sharpe!s:<10} {cagr!s:<15}")

        if r.get('valid'):
            passed += 1
        else:
            failed += 1

    print("-"*80)
    print(f"PASSED: {passed}/{len(results)}, FAILED: {failed}/{len(results)}")

    # List failing strategies with issues
    if failed > 0:
        print("\n--- Failed Strategies ---")
        for r in results:
            if not r.get('valid'):
                print(f"\n{r.get('spec_id')}:")
                if r.get('issues'):
                    for issue in r.get('issues', []):
                        print(f"  - {issue}")
                if r.get('error'):
                    print(f"  Error: {r.get('error')}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
