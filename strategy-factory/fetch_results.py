#!/usr/bin/env python3
"""
Fetch Backtest Results - Reusable CLI Tool

Fetches orders and stats from QuantConnect API and saves structured results.

Usage:
    # Single strategy
    python fetch_results.py --name clenow_momentum --project 27337816 --backtest abc123 --universe large_cap_liquid

    # From JSON config file
    python fetch_results.py --config strategies.json

    # List recent backtests for a project
    python fetch_results.py --list-backtests --project 27337816

Config file format (strategies.json):
    [
        {"name": "strategy1", "project_id": 123, "backtest_id": "abc", "universe": "etf_core"},
        {"name": "strategy2", "project_id": 456, "backtest_id": "def", "universe": "large_cap"}
    ]
"""

import os
import sys
import json
import time
import argparse
import hashlib
import base64
from typing import Dict, List, Optional

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Run: pip install requests")
    sys.exit(1)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner.results_storage import save_backtest_results

# ============================================================================
# QC API Authentication
# ============================================================================

QC_USER_ID = os.environ.get('QC_USER_ID')
QC_API_TOKEN = os.environ.get('QC_API_TOKEN')


def get_auth_headers() -> Dict[str, str]:
    """Generate QC API authentication headers."""
    if not QC_USER_ID or not QC_API_TOKEN:
        raise ValueError("QC_USER_ID and QC_API_TOKEN environment variables required")

    timestamp = str(int(time.time()))
    to_hash = f"{QC_API_TOKEN}:{timestamp}"
    hashed = hashlib.sha256(to_hash.encode()).hexdigest()
    auth_str = f"{QC_USER_ID}:{hashed}"
    encoded = base64.b64encode(auth_str.encode()).decode()

    return {
        "Authorization": f"Basic {encoded}",
        "Timestamp": timestamp,
        "Content-Type": "application/json"
    }


# ============================================================================
# QC API Functions
# ============================================================================

def fetch_backtest_stats(project_id: int, backtest_id: str) -> Dict:
    """Fetch backtest statistics from QC API."""
    url = "https://www.quantconnect.com/api/v2/backtests/read"
    response = requests.post(url, headers=get_auth_headers(), json={
        "projectId": project_id,
        "backtestId": backtest_id
    })
    data = response.json()

    if not data.get('success', False):
        errors = data.get('errors', ['Unknown error'])
        raise ValueError(f"API error: {errors}")

    return data.get('backtest', {})


def fetch_orders(project_id: int, backtest_id: str, verbose: bool = True) -> List[Dict]:
    """
    Fetch all orders from QC API with correct pagination.

    QC API quirks:
    - Returns max 99 orders per request (not 100!)
    - Uses 0-based indexing for start/end params
    - Step by 99 to avoid gaps
    - Use dict to dedupe by order ID
    """
    url = "https://www.quantconnect.com/api/v2/backtests/orders/read"
    all_orders = {}  # Use dict to dedupe by ID
    start = 0
    batch_size = 99  # API returns max 99, not 100!

    while True:
        response = requests.post(url, headers=get_auth_headers(), json={
            "projectId": project_id,
            "backtestId": backtest_id,
            "start": start,
            "end": start + batch_size
        })
        orders = response.json().get('orders', [])

        if not orders:
            break

        for o in orders:
            all_orders[o.get('id')] = o

        if verbose:
            print(f"    Batch {start}: {len(orders)} orders (total: {len(all_orders)})")

        if len(orders) < batch_size:
            break

        start += batch_size
        time.sleep(0.3)

    # Return as list sorted by ID
    return [all_orders[k] for k in sorted(all_orders.keys())]


def list_backtests(project_id: int, limit: int = 10) -> List[Dict]:
    """List recent backtests for a project."""
    url = "https://www.quantconnect.com/api/v2/backtests/read"
    response = requests.post(url, headers=get_auth_headers(), json={
        "projectId": project_id
    })
    data = response.json()

    if not data.get('success', False):
        errors = data.get('errors', ['Unknown error'])
        raise ValueError(f"API error: {errors}")

    backtests = data.get('backtests', [])
    return backtests[:limit]


def run_backtest(project_id: int, backtest_name: str) -> Dict:
    """
    Compile and run a backtest for a project.

    Returns backtest info including backtestId.
    """
    # First compile
    compile_url = "https://www.quantconnect.com/api/v2/compile/create"
    compile_response = requests.post(compile_url, headers=get_auth_headers(), json={
        "projectId": project_id
    })
    compile_data = compile_response.json()

    if not compile_data.get('success', False):
        errors = compile_data.get('errors', ['Unknown error'])
        raise ValueError(f"Compile error: {errors}")

    compile_id = compile_data.get('compileId')
    print(f"  Compiled: {compile_id}")

    # Wait for compile
    time.sleep(2)

    # Run backtest
    backtest_url = "https://www.quantconnect.com/api/v2/backtests/create"
    backtest_response = requests.post(backtest_url, headers=get_auth_headers(), json={
        "projectId": project_id,
        "compileId": compile_id,
        "backtestName": backtest_name
    })
    backtest_data = backtest_response.json()

    if not backtest_data.get('success', False):
        errors = backtest_data.get('errors', ['Unknown error'])
        raise ValueError(f"Backtest error: {errors}")

    return backtest_data.get('backtest', {})


def wait_for_backtest(project_id: int, backtest_id: str, timeout: int = 300) -> Dict:
    """Wait for a backtest to complete."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        stats = fetch_backtest_stats(project_id, backtest_id)
        status = stats.get('status', '')

        if status == 'Completed.':
            return stats
        elif 'Error' in status or 'Failed' in status:
            raise ValueError(f"Backtest failed: {status}")

        print(f"  Status: {status} (waiting...)")
        time.sleep(5)

    raise TimeoutError(f"Backtest did not complete within {timeout}s")


# ============================================================================
# Main Functions
# ============================================================================

def fetch_and_save(
    name: str,
    project_id: int,
    backtest_id: str,
    universe: str,
    verbose: bool = True
) -> str:
    """
    Fetch results for a single strategy and save to disk.

    Returns path to saved results directory.
    """
    if verbose:
        print(f"\n[{name}]")

    # Fetch stats
    if verbose:
        print("  Fetching stats...", end=" ")
    stats = fetch_backtest_stats(project_id, backtest_id)
    total_orders = stats.get('statistics', {}).get('Total Orders', 'N/A')
    if verbose:
        print(f"OK (Total Orders: {total_orders})")

    if stats.get('status') != 'Completed.':
        raise ValueError(f"Backtest not completed: {stats.get('status')}")

    # Fetch orders
    if verbose:
        print("  Fetching orders...")
    orders = fetch_orders(project_id, backtest_id, verbose)
    if verbose:
        print(f"  Total orders: {len(orders)}")

    # Save results
    if verbose:
        print("  Saving results...", end=" ")
    result_dir = save_backtest_results(
        strategy_name=name,
        backtest_id=backtest_id,
        orders=orders,
        stats=stats,
        universe=universe
    )
    if verbose:
        print("OK")
        print(f"  Saved to: {result_dir}")

        # Print key metrics
        statistics = stats.get('statistics', {})
        print(f"  CAGR: {statistics.get('Compounding Annual Return', 'N/A')}")
        print(f"  Sharpe: {statistics.get('Sharpe Ratio', 'N/A')}")
        print(f"  MaxDD: {statistics.get('Drawdown', 'N/A')}")

    return result_dir


def run_and_fetch(
    name: str,
    project_id: int,
    universe: str,
    verbose: bool = True
) -> str:
    """
    Run a backtest and fetch results.

    Returns path to saved results directory.
    """
    if verbose:
        print(f"\n[{name}]")
        print("  Running backtest...")

    # Run backtest
    backtest_info = run_backtest(project_id, f"{name}_{int(time.time())}")
    backtest_id = backtest_info.get('backtestId')
    if verbose:
        print(f"  Backtest ID: {backtest_id}")

    # Wait for completion
    if verbose:
        print("  Waiting for completion...")
    stats = wait_for_backtest(project_id, backtest_id)

    # Fetch and save
    return fetch_and_save(name, project_id, backtest_id, universe, verbose)


def process_config(config_path: str, verbose: bool = True):
    """Process strategies from a JSON config file."""
    with open(config_path, 'r') as f:
        strategies = json.load(f)

    print("=" * 60)
    print(f"Processing {len(strategies)} strategies from {config_path}")
    print("=" * 60)

    results = []
    for strategy in strategies:
        try:
            result_dir = fetch_and_save(
                name=strategy['name'],
                project_id=strategy['project_id'],
                backtest_id=strategy['backtest_id'],
                universe=strategy.get('universe', 'unknown'),
                verbose=verbose
            )
            results.append({'name': strategy['name'], 'status': 'success', 'dir': result_dir})
            time.sleep(1)
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({'name': strategy['name'], 'status': 'error', 'error': str(e)})

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for r in results:
        status = "OK" if r['status'] == 'success' else f"FAILED: {r.get('error', 'Unknown')}"
        print(f"  {r['name']}: {status}")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch backtest results from QuantConnect API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Single strategy arguments
    parser.add_argument('--name', '-n', help='Strategy name')
    parser.add_argument('--project', '-p', type=int, help='QC Project ID')
    parser.add_argument('--backtest', '-b', help='Backtest ID')
    parser.add_argument('--universe', '-u', default='unknown', help='Universe name')

    # Config file
    parser.add_argument('--config', '-c', help='JSON config file with strategy list')

    # Run backtest
    parser.add_argument('--run', action='store_true', help='Run backtest before fetching')

    # List backtests
    parser.add_argument('--list-backtests', action='store_true', help='List recent backtests')
    parser.add_argument('--limit', type=int, default=10, help='Limit for list operations')

    # Options
    parser.add_argument('--quiet', '-q', action='store_true', help='Minimal output')

    args = parser.parse_args()
    verbose = not args.quiet

    try:
        if args.list_backtests:
            if not args.project:
                parser.error("--project required for --list-backtests")
            backtests = list_backtests(args.project, args.limit)
            print(f"\nRecent backtests for project {args.project}:")
            for bt in backtests:
                print(f"  {bt.get('backtestId', 'N/A')[:12]} | {bt.get('name', 'Unnamed')} | {bt.get('status', 'Unknown')}")

        elif args.config:
            process_config(args.config, verbose)

        elif args.run:
            if not args.name or not args.project:
                parser.error("--name and --project required for --run")
            run_and_fetch(args.name, args.project, args.universe, verbose)

        elif args.name and args.project and args.backtest:
            fetch_and_save(args.name, args.project, args.backtest, args.universe, verbose)

        else:
            parser.print_help()

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
