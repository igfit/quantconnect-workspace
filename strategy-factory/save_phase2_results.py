#!/usr/bin/env python3
"""
Save Phase 2 Backtest Results

Uses the runner infrastructure to save all Phase 2 backtest results:
- Orders CSV
- Trades CSV
- P&L by ticker
- Metrics JSON
- Update comparison table
"""

import os
import sys
import time
import hashlib
import base64
import json

# Add strategy-factory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runner.results_storage import save_backtest_results

try:
    import requests
except ImportError:
    print("Error: requests library required")
    sys.exit(1)


def get_qc_auth():
    """Generate QuantConnect API authentication headers."""
    user_id = os.environ.get('QC_USER_ID')
    api_token = os.environ.get('QC_API_TOKEN')

    if not user_id or not api_token:
        print("Error: QC_USER_ID and QC_API_TOKEN required")
        sys.exit(1)

    timestamp = str(int(time.time()))
    hash_input = f"{api_token}:{timestamp}"
    hash_digest = hashlib.sha256(hash_input.encode()).hexdigest()
    auth_string = base64.b64encode(f"{user_id}:{hash_digest}".encode()).decode()

    return {
        'Authorization': f'Basic {auth_string}',
        'Timestamp': timestamp,
        'Content-Type': 'application/json'
    }


def fetch_orders(project_id: int, backtest_id: str) -> list:
    """Fetch all orders from a backtest."""
    orders = []
    start = 0
    batch_size = 100

    while True:
        headers = get_qc_auth()
        payload = {
            'projectId': project_id,
            'backtestId': backtest_id,
            'start': start,
            'end': start + batch_size
        }

        response = requests.post(
            'https://www.quantconnect.com/api/v2/backtests/orders/read',
            headers=headers,
            json=payload
        )

        data = response.json()
        if not data.get('success'):
            print(f"  API Error: {data.get('errors')}")
            break

        batch = data.get('orders', [])
        if not batch:
            break

        orders.extend(batch)
        start += batch_size

        if len(batch) < batch_size:
            break

    return orders


def fetch_backtest_stats(project_id: int, backtest_id: str) -> dict:
    """Fetch backtest statistics."""
    headers = get_qc_auth()
    payload = {
        'projectId': project_id,
        'backtestId': backtest_id
    }

    response = requests.post(
        'https://www.quantconnect.com/api/v2/backtests/read',
        headers=headers,
        json=payload
    )

    data = response.json()
    if data.get('success'):
        return data.get('backtest', {})
    return {}


def save_strategy_results(strategy_name: str, universe: str, project_id: int, backtest_id: str, config: dict = None):
    """Save results for a single strategy."""
    print(f"\n{'='*60}")
    print(f"Saving: {strategy_name}")
    print(f"{'='*60}")

    # Fetch orders
    print(f"  Fetching orders...")
    orders = fetch_orders(project_id, backtest_id)
    print(f"  Found {len(orders)} orders")

    if not orders:
        print(f"  WARNING: No orders found for {strategy_name}")

    # Fetch stats
    print(f"  Fetching backtest stats...")
    stats = fetch_backtest_stats(project_id, backtest_id)

    if not stats:
        print(f"  ERROR: Could not fetch stats for {strategy_name}")
        return None

    # Save using runner infrastructure
    print(f"  Saving results...")
    result_dir = save_backtest_results(
        strategy_name=strategy_name,
        backtest_id=backtest_id,
        orders=orders,
        stats=stats,
        universe=universe,
        config=config or {}
    )

    print(f"  ✓ Results saved to: {result_dir}")

    # Show key metrics
    runtime = stats.get('runtimeStatistics', {})
    statistics = stats.get('statistics', {})
    print(f"\n  Key Metrics:")
    print(f"    CAGR: {statistics.get('Compounding Annual Return', 'N/A')}")
    print(f"    Sharpe: {statistics.get('Sharpe Ratio', 'N/A')}")
    print(f"    Max DD: {statistics.get('Drawdown', 'N/A')}")
    print(f"    Win Rate: {statistics.get('Win Rate', 'N/A')}")
    print(f"    Net Profit: {runtime.get('Net Profit', 'N/A')}")

    return result_dir


def main():
    """Save all Phase 2 backtest results."""
    print("=" * 60)
    print("PHASE 2 RESULTS STORAGE")
    print("=" * 60)

    # Phase 2 strategies with their project/backtest IDs
    strategies = [
        {
            "name": "dual_momentum_gem",
            "universe": "etf_core",
            "project_id": 27336895,
            "backtest_id": "0651f9ce20f6514197b8075672c07a29",
            "config": {
                "symbols": ["SPY", "EFA", "BND"],
                "lookback_days": 252,
                "rebalance": "monthly"
            }
        },
        {
            "name": "sector_rotation",
            "universe": "sector_spdrs",
            "project_id": 27336896,
            "backtest_id": "f199199252f7a84316a6a2cf33a8b8ef",
            "config": {
                "symbols": ["XLK", "XLF", "XLV", "XLE", "XLI", "XLP", "XLY", "XLB", "XLU"],
                "top_n": 3,
                "lookback_days": 63,
                "rebalance": "monthly"
            }
        },
        {
            "name": "rsi2_mean_reversion",
            "universe": "single_instrument",
            "project_id": 27336898,
            "backtest_id": "55190f00547b008db39434c587dd83ff",
            "config": {
                "symbol": "SPY",
                "rsi_period": 2,
                "oversold": 10,
                "overbought": 90,
                "regime_filter": True
            }
        },
        {
            "name": "williams_r_reversion",
            "universe": "single_instrument",
            "project_id": 27336903,
            "backtest_id": "96560ea63033b1bef5d399e106747fd0",
            "config": {
                "symbol": "SPY",
                "williams_period": 10,
                "oversold": -90,
                "overbought": -10,
                "regime_filter": True
            }
        },
    ]

    saved_count = 0
    for strategy in strategies:
        try:
            result = save_strategy_results(
                strategy_name=strategy["name"],
                universe=strategy["universe"],
                project_id=strategy["project_id"],
                backtest_id=strategy["backtest_id"],
                config=strategy["config"]
            )
            if result:
                saved_count += 1
        except Exception as e:
            print(f"  ERROR saving {strategy['name']}: {e}")

        # Rate limiting
        time.sleep(2)

    print(f"\n{'='*60}")
    print(f"COMPLETE: Saved {saved_count}/{len(strategies)} strategies")
    print(f"{'='*60}")

    # Show comparison table location
    print(f"\nComparison table: backtests/comparison/all_strategies.csv")


if __name__ == "__main__":
    main()
