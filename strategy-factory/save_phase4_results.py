#!/usr/bin/env python3
"""Save Phase 4 Backtest Results"""

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
        orders = response.json().get('orders', [])
        if not orders:
            break
        all_orders.extend(orders)
        if len(orders) < batch_size:
            break
        start += batch_size
        time.sleep(0.5)

    return all_orders


def main():
    phase4_strategies = [
        # Best performers
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
    print("PHASE 4 RESULTS STORAGE")
    print("=" * 60)

    for strategy in phase4_strategies:
        print(f"\n[{strategy['name']}]")

        try:
            print("  Fetching stats...", end=" ")
            stats = fetch_backtest_stats(strategy['project_id'], strategy['backtest_id'])
            print(f"OK ({stats.get('status', 'unknown')})")

            if stats.get('status') != 'Completed.':
                print(f"  SKIPPED: Not completed")
                continue

            print("  Fetching orders...", end=" ")
            orders = fetch_orders(strategy['project_id'], strategy['backtest_id'])
            print(f"OK ({len(orders)} orders)")

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

    print("\n" + "=" * 60)
    print("PHASE 4 COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
