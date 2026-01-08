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
import csv
from typing import Dict, List, Optional

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Run: pip install requests")
    sys.exit(1)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner.results_storage import (
    save_backtest_results,
    calculate_trades_from_orders,
    calculate_pnl_by_ticker
)

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

def format_currency(value: float) -> str:
    """Format currency value with sign."""
    if value >= 0:
        return f"${value:,.0f}"
    else:
        return f"-${abs(value):,.0f}"


def print_pnl_table(pnl_data: Dict[str, Dict], top_n: int = 15):
    """Print P&L by ticker table."""
    if not pnl_data:
        print("  No P&L data available")
        return

    # Sort by total P&L descending
    sorted_tickers = sorted(
        pnl_data.items(),
        key=lambda x: x[1].get('total_pnl', 0),
        reverse=True
    )

    # Header
    print()
    print(f"  {'Ticker':<8} {'Trades':>7} {'Win%':>7} {'Realized':>12} {'Unreal':>10} {'Total':>12}")
    print(f"  {'-'*8} {'-'*7} {'-'*7} {'-'*12} {'-'*10} {'-'*12}")

    # Top performers
    for ticker, data in sorted_tickers[:top_n]:
        trades = data.get('total_trades', 0)
        win_rate = data.get('wins', 0) / trades * 100 if trades > 0 else 0
        realized = data.get('realized_pnl', 0)
        unrealized = data.get('unrealized_pnl', 0)
        total = data.get('total_pnl', 0)

        print(f"  {ticker:<8} {trades:>7} {win_rate:>6.1f}% {format_currency(realized):>12} {format_currency(unrealized):>10} {format_currency(total):>12}")

    # If there are more tickers, show count
    if len(sorted_tickers) > top_n:
        remaining = len(sorted_tickers) - top_n
        print(f"  ... and {remaining} more tickers")

    # Summary totals
    total_realized = sum(d.get('realized_pnl', 0) for d in pnl_data.values())
    total_unrealized = sum(d.get('unrealized_pnl', 0) for d in pnl_data.values())
    total_pnl = sum(d.get('total_pnl', 0) for d in pnl_data.values())
    total_trades = sum(d.get('total_trades', 0) for d in pnl_data.values())
    total_wins = sum(d.get('wins', 0) for d in pnl_data.values())

    print(f"  {'-'*8} {'-'*7} {'-'*7} {'-'*12} {'-'*10} {'-'*12}")
    overall_win_rate = total_wins / total_trades * 100 if total_trades > 0 else 0
    print(f"  {'TOTAL':<8} {total_trades:>7} {overall_win_rate:>6.1f}% {format_currency(total_realized):>12} {format_currency(total_unrealized):>10} {format_currency(total_pnl):>12}")


def fetch_and_save(
    name: str,
    project_id: int,
    backtest_id: str,
    universe: str,
    verbose: bool = True,
    show_pnl_table: bool = True
) -> str:
    """
    Fetch results for a single strategy and save to disk.

    Returns path to saved results directory.
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"[{name}]")
        print(f"{'='*60}")

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

    # Calculate trades and P&L
    trades = calculate_trades_from_orders(orders)
    pnl_data = calculate_pnl_by_ticker(trades)

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

    if verbose:
        # Print comprehensive metrics
        statistics = stats.get('statistics', {})
        runtime = stats.get('runtimeStatistics', {})

        print()
        print("  PERFORMANCE METRICS")
        print("  " + "-" * 40)
        print(f"  CAGR:           {statistics.get('Compounding Annual Return', 'N/A')}")
        print(f"  Sharpe Ratio:   {statistics.get('Sharpe Ratio', 'N/A')}")
        print(f"  Max Drawdown:   {statistics.get('Drawdown', 'N/A')}")
        print(f"  Net Profit:     {runtime.get('Net Profit', 'N/A')}")

        # Calculate trade statistics
        total_trades_count = len(trades)
        winners = [t for t in trades if t.pnl_dollars > 0]
        losers = [t for t in trades if t.pnl_dollars <= 0]

        win_rate = len(winners) / total_trades_count * 100 if total_trades_count > 0 else 0
        avg_win = sum(t.pnl_pct for t in winners) / len(winners) * 100 if winners else 0
        avg_loss = sum(t.pnl_pct for t in losers) / len(losers) * 100 if losers else 0
        risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        avg_hold = sum(t.bars_held for t in trades) / total_trades_count if total_trades_count > 0 else 0

        print()
        print("  TRADE STATISTICS")
        print("  " + "-" * 40)
        print(f"  Total Trades:   {total_trades_count}")
        print(f"  Win Rate:       {win_rate:.1f}%")
        print(f"  Avg Win:        {avg_win:.1f}%")
        print(f"  Avg Loss:       {avg_loss:.1f}%")
        print(f"  Risk/Reward:    {risk_reward:.2f}")
        print(f"  Profit Factor:  {statistics.get('Profit-Loss Ratio', 'N/A')}")
        print(f"  Avg Hold (days):{avg_hold:.0f}")

        # P&L by ticker table
        if show_pnl_table and pnl_data:
            print()
            print("  P&L BY TICKER (Top 15)")
            print("  " + "-" * 40)
            print_pnl_table(pnl_data, top_n=15)

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


def process_config(config_path: str, verbose: bool = True, show_pnl_table: bool = True):
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
                verbose=verbose,
                show_pnl_table=show_pnl_table
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
    parser.add_argument('--no-pnl-table', action='store_true', help='Skip P&L by ticker table')
    parser.add_argument('--top-tickers', type=int, default=15, help='Number of top tickers to show (default: 15)')

    args = parser.parse_args()
    verbose = not args.quiet
    show_pnl_table = not args.no_pnl_table

    try:
        if args.list_backtests:
            if not args.project:
                parser.error("--project required for --list-backtests")
            backtests = list_backtests(args.project, args.limit)
            print(f"\nRecent backtests for project {args.project}:")
            for bt in backtests:
                print(f"  {bt.get('backtestId', 'N/A')[:12]} | {bt.get('name', 'Unnamed')} | {bt.get('status', 'Unknown')}")

        elif args.config:
            process_config(args.config, verbose, show_pnl_table)

        elif args.run:
            if not args.name or not args.project:
                parser.error("--name and --project required for --run")
            run_and_fetch(args.name, args.project, args.universe, verbose)

        elif args.name and args.project and args.backtest:
            fetch_and_save(args.name, args.project, args.backtest, args.universe, verbose, show_pnl_table)

        else:
            parser.print_help()

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
