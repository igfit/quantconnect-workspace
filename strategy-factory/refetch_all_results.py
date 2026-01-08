#!/usr/bin/env python3
"""
Re-fetch all backtest results with fixed pagination.

Bug fix: QC API returns max 99 orders per request, not 100.
"""

import os
import sys
import time
import hashlib
import base64
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner.results_storage import save_backtest_results

QC_USER_ID = os.environ.get('QC_USER_ID')
QC_API_TOKEN = os.environ.get('QC_API_TOKEN')


def get_auth_headers():
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
    url = "https://www.quantconnect.com/api/v2/backtests/read"
    response = requests.post(url, headers=get_auth_headers(), json={
        "projectId": project_id,
        "backtestId": backtest_id
    })
    return response.json().get('backtest', {})


def fetch_orders(project_id: int, backtest_id: str) -> list:
    """Fetch orders with FIXED pagination.

    QC API quirks:
    - Returns max 99 orders per request
    - Uses 0-based indexing for start/end params
    - Step by 99 (not 100) to avoid gaps
    - Use dict to dedupe by order ID
    """
    url = "https://www.quantconnect.com/api/v2/backtests/orders/read"
    all_orders = {}  # Use dict to dedupe by ID
    start = 0
    batch_size = 99

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

        print(f"    Batch {start}: {len(orders)} orders (unique total: {len(all_orders)})")

        if len(orders) < batch_size:
            break

        start += batch_size  # Step by 99 to avoid gaps
        time.sleep(0.3)

    # Return as list sorted by ID
    return [all_orders[k] for k in sorted(all_orders.keys())]


def main():
    # All strategies to refetch
    strategies = [
        # Phase 3 - Large Cap
        {
            "name": "clenow_momentum",
            "project_id": 27337816,
            "backtest_id": "7de0da86d586febe3cb5d64f5f60b5f7",
            "universe": "large_cap_liquid"
        },
        {
            "name": "donchian_breakout",
            "project_id": 27337815,
            "backtest_id": "eea5f5363fc26d77ad9fab91ed36daf6",
            "universe": "large_cap_liquid"
        },
        {
            "name": "week52_high_breakout",
            "project_id": 27337820,
            "backtest_id": "f431e752813c4eaa15fc2bcb8b8e6fa3",
            "universe": "large_cap_liquid"
        },
        {
            "name": "elder_impulse",
            "project_id": 27337817,
            "backtest_id": "ce51ad167e72ac75dcf80b1a2d24b5a1",
            "universe": "large_cap_liquid"
        },
        {
            "name": "nr7_breakout",
            "project_id": 27337818,
            "backtest_id": "9e28aaada1e16f1c34df86cc3bd8bc4b",
            "universe": "large_cap_liquid"
        },
        # Phase 4 - High Beta
        {
            "name": "clenow_controlled",
            "project_id": 27338318,
            "backtest_id": "bd25a8faeb776cc883a4750b1aa2ee58",
            "universe": "high_beta_growth"
        },
        {
            "name": "clenow_aggressive",
            "project_id": 27338134,
            "backtest_id": "db4879fd5c0c56fdd87e7b02873fd47e",
            "universe": "high_beta_growth"
        },
        {
            "name": "momentum_burst",
            "project_id": 27338138,
            "backtest_id": "1bc494ad1db2145eefea10a4b64dc624",
            "universe": "high_beta_growth"
        },
        {
            "name": "clenow_with_stops",
            "project_id": 27338324,
            "backtest_id": "4226027bd28958b521fabf32ae43e05c",
            "universe": "high_beta_growth"
        },
        {
            "name": "chandelier_trend",
            "project_id": 27338141,
            "backtest_id": "2628c9d9778b7bc14151fd85d4bfec09",
            "universe": "high_beta_growth"
        },
    ]

    print("=" * 60)
    print("RE-FETCHING ALL RESULTS (FIXED PAGINATION)")
    print("=" * 60)

    for strategy in strategies:
        print(f"\n[{strategy['name']}]")

        try:
            print("  Fetching stats...", end=" ")
            stats = fetch_backtest_stats(strategy['project_id'], strategy['backtest_id'])
            total_orders = stats.get('statistics', {}).get('Total Orders', 'N/A')
            print(f"OK (Total Orders: {total_orders})")

            if stats.get('status') != 'Completed.':
                print(f"  SKIPPED: Not completed")
                continue

            print("  Fetching orders...")
            orders = fetch_orders(strategy['project_id'], strategy['backtest_id'])
            print(f"  Total orders fetched: {len(orders)}")

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

            statistics = stats.get('statistics', {})
            print(f"  CAGR: {statistics.get('Compounding Annual Return', 'N/A')}")
            print(f"  Sharpe: {statistics.get('Sharpe Ratio', 'N/A')}")
            print(f"  MaxDD: {statistics.get('Drawdown', 'N/A')}")

            time.sleep(1)

        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("REFETCH COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
