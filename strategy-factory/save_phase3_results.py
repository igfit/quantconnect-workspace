#!/usr/bin/env python3
"""
Save Phase 3 Backtest Results

Fetches orders and stats from QuantConnect API and saves using the results_storage module.
"""

import os
import sys
import time
import json
import hashlib
import base64
import requests

# Add runner module to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner.results_storage import save_backtest_results

# QC API credentials from environment
QC_USER_ID = os.environ.get('QC_USER_ID')
QC_API_TOKEN = os.environ.get('QC_API_TOKEN')

if not QC_USER_ID or not QC_API_TOKEN:
    print("ERROR: Set QC_USER_ID and QC_API_TOKEN environment variables")
    sys.exit(1)


def get_auth_headers():
    """Generate QC API authentication headers"""
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


def fetch_backtest_stats(project_id: int, backtest_id: str) -> dict:
    """Fetch backtest stats from QC API"""
    url = "https://www.quantconnect.com/api/v2/backtests/read"
    response = requests.post(url, headers=get_auth_headers(), json={
        "projectId": project_id,
        "backtestId": backtest_id
    })
    return response.json().get('backtest', {})


def fetch_orders(project_id: int, backtest_id: str) -> list:
    """Fetch all orders from QC API (with pagination)"""
    url = "https://www.quantconnect.com/api/v2/backtests/orders/read"
    all_orders = []
    start = 0
    batch_size = 100

    while True:
        response = requests.post(url, headers=get_auth_headers(), json={
            "projectId": project_id,
            "backtestId": backtest_id,
            "start": start,
            "end": start + batch_size - 1
        })
        data = response.json()
        orders = data.get('orders', [])

        if not orders:
            break

        all_orders.extend(orders)

        if len(orders) < batch_size:
            break

        start += batch_size
        time.sleep(0.5)  # Rate limiting

    return all_orders


def main():
    """Save all Phase 3 backtest results"""

    # Phase 3 strategies with their project IDs and final backtest IDs
    phase3_strategies = [
        {
            "name": "clenow_momentum",
            "project_id": 27337634,
            "backtest_id": "7de0da86d58665309e23a66d1b0130fc",
            "universe": "large_cap_liquid"
        },
        {
            "name": "donchian_breakout",
            "project_id": 27337636,
            "backtest_id": "eea5f5363fc2d775ca22790f4c2cd798",  # v3
            "universe": "large_cap_liquid"
        },
        {
            "name": "week52_high_breakout",
            "project_id": 27337637,
            "backtest_id": "f431e752813cf3195dcd2f1299ea42b5",  # v2
            "universe": "large_cap_liquid"
        },
        {
            "name": "elder_impulse",
            "project_id": 27337639,
            "backtest_id": "ce51ad167e7290c5c244c381d2662f65",  # v2
            "universe": "large_cap_liquid"
        },
        {
            "name": "nr7_breakout",
            "project_id": 27337640,
            "backtest_id": "9e28aaada1e1dc70a130c25ba5dffbe7",
            "universe": "large_cap_liquid"
        },
    ]

    print("=" * 60)
    print("PHASE 3 RESULTS STORAGE")
    print("=" * 60)

    for strategy in phase3_strategies:
        print(f"\n[{strategy['name']}]")
        print(f"  Project: {strategy['project_id']}")
        print(f"  Backtest: {strategy['backtest_id'][:12]}")

        try:
            # Fetch stats
            print("  Fetching stats...", end=" ")
            stats = fetch_backtest_stats(strategy['project_id'], strategy['backtest_id'])
            print(f"OK ({stats.get('status', 'unknown')})")

            if stats.get('status') != 'Completed.':
                print(f"  SKIPPED: Backtest not completed")
                continue

            # Fetch orders
            print("  Fetching orders...", end=" ")
            orders = fetch_orders(strategy['project_id'], strategy['backtest_id'])
            print(f"OK ({len(orders)} orders)")

            # Save results
            print("  Saving results...", end=" ")
            result_dir = save_backtest_results(
                strategy_name=strategy['name'],
                backtest_id=strategy['backtest_id'],
                orders=orders,
                stats=stats,
                universe=strategy['universe']
            )
            print(f"OK")
            print(f"  Saved to: {result_dir}")

            # Print key metrics
            statistics = stats.get('statistics', {})
            runtime = stats.get('runtimeStatistics', {})
            print(f"  CAGR: {statistics.get('Compounding Annual Return', 'N/A')}")
            print(f"  Sharpe: {statistics.get('Sharpe Ratio', 'N/A')}")
            print(f"  MaxDD: {statistics.get('Drawdown', 'N/A')}")

            time.sleep(1)  # Rate limiting between strategies

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("PHASE 3 COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
