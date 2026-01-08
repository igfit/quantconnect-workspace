#!/usr/bin/env python3
"""
Test script for runner and results storage modules.

Tests:
1. ResultsStorage class initialization and directory creation
2. Order fetching from QC API
3. Trade calculation from orders
4. P&L by ticker calculation
5. Metrics extraction and storage
6. Comparison table update
"""

import os
import sys
import json

# Add strategy-factory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runner.results_storage import (
    ResultsStorage,
    BacktestMetrics,
    Trade,
    calculate_trades_from_orders,
    calculate_pnl_by_ticker,
    save_backtest_results,
)

# Test configuration
PROJECT_ID = 27336494
BACKTEST_ID = "105cddffc795ad195857e6423d2fcf86"
STRATEGY_NAME = "sma_crossover_infra_test"


def test_results_storage_init():
    """Test ResultsStorage initialization"""
    print("\n" + "=" * 60)
    print("TEST 1: ResultsStorage Initialization")
    print("=" * 60)

    storage = ResultsStorage()

    print(f"✓ Base directory: {storage.base_dir}")
    print(f"✓ Comparison directory: {storage.comparison_dir}")

    # Test directory creation
    strategy_dir = storage.get_strategy_dir("test_strategy_xyz")
    print(f"✓ Strategy directory created: {strategy_dir}")

    bt_dir = storage.get_backtest_dir("test_strategy_xyz", "abc123def456789")
    print(f"✓ Backtest directory created: {bt_dir}")

    # Cleanup test directories
    os.rmdir(bt_dir)
    os.rmdir(strategy_dir)
    print("✓ Test directories cleaned up")

    return True


def test_fetch_orders():
    """Test fetching orders from QC API"""
    print("\n" + "=" * 60)
    print("TEST 2: Fetch Orders from QC API")
    print("=" * 60)

    import hashlib
    import base64
    import time
    import requests

    user_id = os.environ.get('QC_USER_ID')
    api_token = os.environ.get('QC_API_TOKEN')

    if not user_id or not api_token:
        print("⚠ Skipping: QC_USER_ID and QC_API_TOKEN not set")
        return None

    # Generate auth
    timestamp = str(int(time.time()))
    hash_input = f"{api_token}:{timestamp}"
    hash_digest = hashlib.sha256(hash_input.encode()).hexdigest()
    auth_string = base64.b64encode(f"{user_id}:{hash_digest}".encode()).decode()

    headers = {
        'Authorization': f'Basic {auth_string}',
        'Timestamp': timestamp,
        'Content-Type': 'application/json'
    }

    # Fetch orders
    payload = {
        'projectId': PROJECT_ID,
        'backtestId': BACKTEST_ID,
        'start': 0,
        'end': 100
    }

    response = requests.post(
        'https://www.quantconnect.com/api/v2/backtests/orders/read',
        headers=headers,
        json=payload
    )

    data = response.json()

    if not data.get('success'):
        print(f"✗ API Error: {data.get('errors')}")
        return None

    orders = data.get('orders', [])
    print(f"✓ Fetched {len(orders)} orders from QC API")

    # Show sample order
    if orders:
        sample = orders[0]
        print(f"  Sample order: {sample.get('symbol', {}).get('value')} "
              f"qty={sample.get('quantity')} @ ${sample.get('price', 0):.2f}")

    return orders


def test_fetch_backtest_stats():
    """Test fetching backtest statistics"""
    print("\n" + "=" * 60)
    print("TEST 3: Fetch Backtest Statistics")
    print("=" * 60)

    import hashlib
    import base64
    import time
    import requests

    user_id = os.environ.get('QC_USER_ID')
    api_token = os.environ.get('QC_API_TOKEN')

    if not user_id or not api_token:
        print("⚠ Skipping: QC credentials not set")
        return None

    timestamp = str(int(time.time()))
    hash_input = f"{api_token}:{timestamp}"
    hash_digest = hashlib.sha256(hash_input.encode()).hexdigest()
    auth_string = base64.b64encode(f"{user_id}:{hash_digest}".encode()).decode()

    headers = {
        'Authorization': f'Basic {auth_string}',
        'Timestamp': timestamp,
        'Content-Type': 'application/json'
    }

    payload = {
        'projectId': PROJECT_ID,
        'backtestId': BACKTEST_ID
    }

    response = requests.post(
        'https://www.quantconnect.com/api/v2/backtests/read',
        headers=headers,
        json=payload
    )

    data = response.json()

    if not data.get('success'):
        print(f"✗ API Error: {data.get('errors')}")
        return None

    stats = data.get('backtest', {})
    runtime = stats.get('runtimeStatistics', {})

    print(f"✓ Strategy: {stats.get('name')}")
    print(f"✓ Period: {stats.get('backtestStart')} to {stats.get('backtestEnd')}")
    print(f"✓ Equity: {runtime.get('Equity')}")
    print(f"✓ Net Profit: {runtime.get('Net Profit')}")

    return stats


def test_trade_calculation(orders):
    """Test round-trip trade calculation"""
    print("\n" + "=" * 60)
    print("TEST 4: Trade Calculation from Orders")
    print("=" * 60)

    if not orders:
        print("⚠ Skipping: No orders provided")
        return None

    trades = calculate_trades_from_orders(orders)

    print(f"✓ Calculated {len(trades)} round-trip trades")

    for i, trade in enumerate(trades[:5]):  # Show first 5
        print(f"  Trade {i+1}: {trade.symbol} | "
              f"{trade.entry_date} → {trade.exit_date} | "
              f"${trade.pnl_dollars:,.0f} ({trade.pnl_pct*100:.1f}%) | "
              f"{trade.bars_held} days")

    # Validate trade structure
    if trades:
        t = trades[0]
        assert hasattr(t, 'symbol'), "Trade missing symbol"
        assert hasattr(t, 'entry_date'), "Trade missing entry_date"
        assert hasattr(t, 'exit_date'), "Trade missing exit_date"
        assert hasattr(t, 'pnl_dollars'), "Trade missing pnl_dollars"
        assert hasattr(t, 'pnl_pct'), "Trade missing pnl_pct"
        assert hasattr(t, 'bars_held'), "Trade missing bars_held"
        print("✓ Trade structure validated")

    return trades


def test_pnl_by_ticker(trades):
    """Test P&L by ticker calculation"""
    print("\n" + "=" * 60)
    print("TEST 5: P&L by Ticker Calculation")
    print("=" * 60)

    if not trades:
        print("⚠ Skipping: No trades provided")
        return None

    pnl_data = calculate_pnl_by_ticker(trades)

    print(f"✓ Calculated P&L for {len(pnl_data)} tickers")

    for symbol, data in pnl_data.items():
        print(f"  {symbol}: {data['total_trades']} trades | "
              f"Win rate: {data['wins']}/{data['total_trades']} | "
              f"P&L: ${data['total_pnl']:,.0f} | "
              f"R:R: {data['rr_ratio']:.2f}")

    return pnl_data


def test_save_backtest_results(orders, stats):
    """Test full results storage pipeline"""
    print("\n" + "=" * 60)
    print("TEST 6: Full Results Storage Pipeline")
    print("=" * 60)

    if not orders or not stats:
        print("⚠ Skipping: Missing orders or stats")
        return False

    result_dir = save_backtest_results(
        strategy_name=STRATEGY_NAME,
        backtest_id=BACKTEST_ID,
        orders=orders,
        stats=stats,
        universe="single_instrument",
        config={
            "symbols": ["SPY"],
            "sma_fast": 50,
            "sma_slow": 200,
        }
    )

    print(f"✓ Results saved to: {result_dir}")

    # Verify files exist
    expected_files = ['orders.csv', 'trades.csv', 'pnl_by_ticker.csv', 'metrics.json', 'config.json']
    for filename in expected_files:
        filepath = os.path.join(result_dir, filename)
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            print(f"  ✓ {filename} ({size} bytes)")
        else:
            print(f"  ✗ {filename} NOT FOUND")

    # Load and display metrics
    metrics_file = os.path.join(result_dir, 'metrics.json')
    if os.path.exists(metrics_file):
        with open(metrics_file, 'r') as f:
            metrics = json.load(f)
        print(f"\n  Metrics Summary:")
        print(f"    CAGR: {metrics.get('cagr')}%")
        print(f"    Sharpe: {metrics.get('sharpe')}")
        print(f"    Max DD: {metrics.get('max_drawdown')}%")
        print(f"    Win Rate: {metrics.get('win_rate'):.1f}%")
        print(f"    Avg Win: {metrics.get('avg_win_pct'):.1f}%")
        print(f"    Avg Loss: {metrics.get('avg_loss_pct'):.1f}%")
        print(f"    R:R: {metrics.get('risk_reward'):.2f}")

    return True


def test_comparison_table():
    """Test comparison table exists and is updated"""
    print("\n" + "=" * 60)
    print("TEST 7: Comparison Table")
    print("=" * 60)

    storage = ResultsStorage()
    comparison_file = os.path.join(storage.comparison_dir, 'all_strategies.csv')

    if os.path.exists(comparison_file):
        with open(comparison_file, 'r') as f:
            lines = f.readlines()
        print(f"✓ Comparison table exists: {comparison_file}")
        print(f"✓ Contains {len(lines)} rows (including header)")

        # Show last entry
        if len(lines) > 1:
            print(f"\n  Latest entry:")
            header = lines[0].strip().split(',')
            values = lines[-1].strip().split(',')
            for h, v in zip(header[:8], values[:8]):
                print(f"    {h}: {v}")
    else:
        print(f"✗ Comparison table not found: {comparison_file}")

    return True


def main():
    """Run all tests"""
    print("=" * 60)
    print("RUNNER AND RESULTS STORAGE TEST SUITE")
    print("=" * 60)

    # Test 1: Storage initialization
    test_results_storage_init()

    # Test 2: Fetch orders
    orders = test_fetch_orders()

    # Test 3: Fetch stats
    stats = test_fetch_backtest_stats()

    # Test 4: Trade calculation
    trades = test_trade_calculation(orders)

    # Test 5: P&L by ticker
    test_pnl_by_ticker(trades)

    # Test 6: Full save pipeline
    test_save_backtest_results(orders, stats)

    # Test 7: Comparison table
    test_comparison_table()

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
