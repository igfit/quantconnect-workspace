#!/usr/bin/env python3
"""
Backtest P&L Calculator

Fetches orders from a QuantConnect backtest and calculates P&L per ticker.
Saves orders to CSV and displays realized/unrealized P&L breakdown.

Usage:
    python scripts/backtest_pnl.py <project_id> <backtest_id> [--save-dir <dir>]

Example:
    python scripts/backtest_pnl.py 27320717 1621985cb8a866271907cb33d8d675f2
"""

import argparse
import csv
import hashlib
import base64
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

try:
    import requests
except ImportError:
    print("Error: requests library required. Install with: pip install requests")
    sys.exit(1)


def get_qc_auth():
    """Generate QuantConnect API authentication headers."""
    user_id = os.environ.get('QC_USER_ID')
    api_token = os.environ.get('QC_API_TOKEN')

    if not user_id or not api_token:
        print("Error: QC_USER_ID and QC_API_TOKEN environment variables required")
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
            error = data.get('errors', ['Unknown error'])
            print(f"API Error: {error}")
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


def save_orders_csv(orders: list, filepath: str):
    """Save orders to CSV file."""
    if not orders:
        print("No orders to save")
        return

    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Date', 'Ticker', 'Direction', 'Quantity', 'Price', 'Value', 'Status'])

        for order in orders:
            ticker = order.get('symbol', {}).get('value', 'UNKNOWN')
            qty = order.get('quantity', 0)
            price = order.get('price', 0)
            value = order.get('value', qty * price)
            status = order.get('status', 0)
            created = order.get('createdTime', '')
            direction = 'BUY' if qty > 0 else 'SELL'

            writer.writerow([created, ticker, direction, abs(qty), price, abs(value), status])

    print(f"Saved {len(orders)} orders to {filepath}")


def calculate_pnl(orders: list, holdings_value: float = None) -> dict:
    """
    Calculate P&L per ticker using position-based accounting.

    Position-based means:
    - Realized P&L: Only from fully closed positions (no shares remaining)
    - Unrealized P&L: All gains on positions still held
    """
    positions = defaultdict(lambda: {
        'net_shares': 0,
        'total_bought': 0,
        'total_sold': 0,
        'last_price': 0,
        'trades': []
    })

    for order in orders:
        ticker = order.get('symbol', {}).get('value', 'UNKNOWN')
        qty = order.get('quantity', 0)
        price = order.get('price', 0)

        positions[ticker]['net_shares'] += qty
        positions[ticker]['last_price'] = price
        positions[ticker]['trades'].append({'qty': qty, 'price': price})

        if qty > 0:
            positions[ticker]['total_bought'] += qty * price
        else:
            positions[ticker]['total_sold'] += abs(qty) * price

    # Separate closed and open positions
    closed = []
    open_pos = []

    for ticker, pos in positions.items():
        net_cost = pos['total_bought'] - pos['total_sold']

        if abs(pos['net_shares']) < 0.5:  # Closed position
            pnl = pos['total_sold'] - pos['total_bought']
            closed.append({
                'ticker': ticker,
                'realized_pnl': pnl,
                'unrealized_pnl': 0,
                'total_pnl': pnl,
                'shares': 0,
                'net_cost': 0,
                'status': 'Closed'
            })
        else:
            open_pos.append({
                'ticker': ticker,
                'shares': pos['net_shares'],
                'net_cost': net_cost,
                'last_price': pos['last_price'],
                'total_bought': pos['total_bought'],
                'total_sold': pos['total_sold']
            })

    # Calculate unrealized P&L for open positions
    if holdings_value and open_pos:
        # Use actual holdings value from backtest
        last_price_value = sum(p['shares'] * p['last_price'] for p in open_pos)
        scale_factor = holdings_value / last_price_value if last_price_value > 0 else 1

        for p in open_pos:
            current_val = p['shares'] * p['last_price'] * scale_factor
            unrealized = current_val - p['net_cost']
            p['current_value'] = current_val
            p['unrealized_pnl'] = unrealized
            p['realized_pnl'] = 0
            p['total_pnl'] = unrealized
            p['status'] = f"Open ({int(p['shares'])} sh)"
    else:
        # Estimate using last trade price
        for p in open_pos:
            current_val = p['shares'] * p['last_price']
            unrealized = current_val - p['net_cost']
            p['current_value'] = current_val
            p['unrealized_pnl'] = unrealized
            p['realized_pnl'] = 0
            p['total_pnl'] = unrealized
            p['status'] = f"Open ({int(p['shares'])} sh)"

    return {
        'closed': closed,
        'open': open_pos,
        'total_realized': sum(p['realized_pnl'] for p in closed),
        'total_unrealized': sum(p.get('unrealized_pnl', 0) for p in open_pos),
    }


def print_pnl_report(pnl: dict, stats: dict = None):
    """Print formatted P&L report."""
    print()
    print("=" * 90)
    print("P&L PER TICKER REPORT")
    print("=" * 90)

    if stats:
        print(f"Strategy: {stats.get('name', 'Unknown')}")
        print(f"Period: {stats.get('backtestStart', '')} to {stats.get('backtestEnd', '')}")
        runtime = stats.get('runtimeStatistics', {})
        print(f"Final Equity: {runtime.get('Equity', 'N/A')}")
        print(f"Net Profit: {runtime.get('Net Profit', 'N/A')}")
    print()

    # Closed positions
    print("CLOSED POSITIONS (Realized P&L)")
    print("-" * 60)
    print(f"{'Ticker':<10} {'Realized':>18} {'Unrealized':>18} {'Total':>18}")
    print("-" * 60)

    closed = sorted(pnl['closed'], key=lambda x: x['total_pnl'], reverse=True)
    for p in closed:
        r = f"+${p['realized_pnl']:,.0f}" if p['realized_pnl'] >= 0 else f"-${abs(p['realized_pnl']):,.0f}"
        print(f"{p['ticker']:<10} {r:>18} {'$0':>18} {r:>18}")

    print("-" * 60)
    subtotal = pnl['total_realized']
    s = f"+${subtotal:,.0f}" if subtotal >= 0 else f"-${abs(subtotal):,.0f}"
    print(f"{'SUBTOTAL':<10} {s:>18} {'$0':>18} {s:>18}")
    print()

    # Open positions
    if pnl['open']:
        print("OPEN POSITIONS (Unrealized P&L)")
        print("-" * 90)
        print(f"{'Ticker':<10} {'Shares':>8} {'Net Cost':>14} {'Curr Value':>14} {'Realized':>14} {'Unrealized':>14}")
        print("-" * 90)

        for p in pnl['open']:
            curr_val = p.get('current_value', 0)
            print(f"{p['ticker']:<10} {p['shares']:>8.0f} ${p['net_cost']:>13,.0f} ${curr_val:>13,.0f} {'$0':>14} +${p['unrealized_pnl']:>13,.0f}")

        print("-" * 90)
        total_cost = sum(p['net_cost'] for p in pnl['open'])
        total_val = sum(p.get('current_value', 0) for p in pnl['open'])
        print(f"{'SUBTOTAL':<10} {'':>8} ${total_cost:>13,.0f} ${total_val:>13,.0f} {'$0':>14} +${pnl['total_unrealized']:>13,.0f}")
        print()

    # Combined summary
    print("=" * 90)
    print("COMBINED SUMMARY (Sorted by Total P&L)")
    print("=" * 90)
    print(f"{'Ticker':<10} {'Realized':>16} {'Unrealized':>16} {'Total P&L':>16} {'Status':<18}")
    print("-" * 80)

    all_positions = pnl['closed'] + pnl['open']
    all_positions.sort(key=lambda x: x['total_pnl'], reverse=True)

    for p in all_positions:
        r = f"+${p['realized_pnl']:,.0f}" if p['realized_pnl'] >= 0 else f"-${abs(p['realized_pnl']):,.0f}"
        u = f"+${p['unrealized_pnl']:,.0f}" if p['unrealized_pnl'] >= 0 else f"-${abs(p['unrealized_pnl']):,.0f}"
        t = f"+${p['total_pnl']:,.0f}" if p['total_pnl'] >= 0 else f"-${abs(p['total_pnl']):,.0f}"
        print(f"{p['ticker']:<10} {r:>16} {u:>16} {t:>16} {p['status']:<18}")

    print("-" * 80)
    grand_total = pnl['total_realized'] + pnl['total_unrealized']
    print(f"{'TOTAL':<10} +${pnl['total_realized']:>15,.0f} +${pnl['total_unrealized']:>15,.0f} +${grand_total:>15,.0f}")
    print()

    # Reconciliation
    print("=" * 90)
    print("RECONCILIATION")
    print("=" * 90)

    if stats:
        runtime = stats.get('runtimeStatistics', {})
        equity_str = runtime.get('Equity', '$0').replace('$', '').replace(',', '')
        try:
            equity = float(equity_str)
        except:
            equity = 0

        fees_str = runtime.get('Fees', '$0').replace('$', '').replace(',', '').replace('-', '')
        try:
            fees = float(fees_str)
        except:
            fees = 0

        print(f"Starting Capital:              $     100,000")
        print(f"Realized P&L:                  +${pnl['total_realized']:>12,.0f}")
        print(f"Unrealized P&L:                +${pnl['total_unrealized']:>12,.0f}")
        print(f"Fees:                          -${fees:>12,.0f}")
        print("-" * 45)
        calculated = 100000 + pnl['total_realized'] + pnl['total_unrealized'] - fees
        print(f"Calculated Equity:             ${calculated:>13,.0f}")
        print(f"Backtest Equity:               ${equity:>13,.0f}")

        diff = abs(calculated - equity)
        if diff < 100:
            print(f"Difference:                    ${diff:>13,.0f}  ✓ (rounding)")
        else:
            print(f"Difference:                    ${diff:>13,.0f}  ⚠ CHECK")

    print()


def save_pnl_csv(pnl: dict, filepath: str):
    """Save P&L summary to CSV."""
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Ticker', 'Shares', 'Net_Cost', 'Current_Value', 'Realized_PnL', 'Unrealized_PnL', 'Total_PnL', 'Status'])

        all_positions = pnl['closed'] + pnl['open']
        all_positions.sort(key=lambda x: x['total_pnl'], reverse=True)

        for p in all_positions:
            writer.writerow([
                p['ticker'],
                p.get('shares', 0),
                p.get('net_cost', 0),
                p.get('current_value', 0),
                p['realized_pnl'],
                p['unrealized_pnl'],
                p['total_pnl'],
                p['status']
            ])

        # Totals row
        writer.writerow([
            'TOTAL', '', '', '',
            pnl['total_realized'],
            pnl['total_unrealized'],
            pnl['total_realized'] + pnl['total_unrealized'],
            ''
        ])

    print(f"Saved P&L summary to {filepath}")


def main():
    parser = argparse.ArgumentParser(description='Calculate P&L from QuantConnect backtest')
    parser.add_argument('project_id', type=int, help='QuantConnect project ID')
    parser.add_argument('backtest_id', type=str, help='Backtest ID')
    parser.add_argument('--save-dir', type=str, default='backtests', help='Directory to save results')
    parser.add_argument('--name', type=str, help='Strategy name for filenames')

    args = parser.parse_args()

    # Create save directory
    os.makedirs(args.save_dir, exist_ok=True)

    # Fetch backtest stats
    print(f"Fetching backtest stats for project {args.project_id}...")
    stats = fetch_backtest_stats(args.project_id, args.backtest_id)

    if not stats:
        print("Warning: Could not fetch backtest stats")

    # Get holdings value for accurate unrealized P&L
    holdings_value = None
    if stats:
        runtime = stats.get('runtimeStatistics', {})
        holdings_str = runtime.get('Holdings', '0').replace('$', '').replace(',', '')
        try:
            holdings_value = float(holdings_str)
        except:
            pass

    # Fetch orders
    print(f"Fetching orders for backtest {args.backtest_id}...")
    orders = fetch_orders(args.project_id, args.backtest_id)
    print(f"Found {len(orders)} orders")

    if not orders:
        print("No orders found")
        return

    # Generate filenames
    name = args.name or stats.get('name', 'backtest').replace(' ', '_').lower()
    timestamp = datetime.now().strftime('%Y%m%d')
    orders_file = os.path.join(args.save_dir, f"{name}_orders_{timestamp}.csv")
    pnl_file = os.path.join(args.save_dir, f"{name}_pnl_{timestamp}.csv")

    # Save orders
    save_orders_csv(orders, orders_file)

    # Calculate P&L
    pnl = calculate_pnl(orders, holdings_value)

    # Print report
    print_pnl_report(pnl, stats)

    # Save P&L summary
    save_pnl_csv(pnl, pnl_file)


if __name__ == '__main__':
    main()
