#!/usr/bin/env python3
"""
Calculate P&L per ticker from QC backtest orders.
Fetches end prices from the backtest's latest trade prices.
"""
import json
import sys
import subprocess
from collections import defaultdict


def fetch_orders(project_id, backtest_id):
    """Fetch all orders from QC API"""
    import re
    orders = []
    for start in range(0, 1000, 100):
        end = start + 100
        cmd = f'./scripts/qc-api.sh orders {project_id} "{backtest_id}" {start} {end} 2>/dev/null'
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            output = result.stdout

            # Find JSON object in output - look for opening brace
            start_idx = output.find('{')
            if start_idx == -1:
                break

            # Parse the JSON from that point
            json_str = output[start_idx:]
            data = json.loads(json_str)

            if 'orders' in data and data['orders']:
                orders.extend(data['orders'])
                if len(data['orders']) < 100:
                    break  # Last page
            else:
                break
        except Exception as e:
            print(f"Error fetching orders at {start}: {e}")
            break
    return orders


def fetch_backtest_stats(project_id, backtest_id):
    """Fetch backtest statistics"""
    cmd = f'./scripts/qc-api.sh results {project_id} "{backtest_id}"'
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        # Find JSON in output
        for line in result.stdout.split('\n'):
            if line.strip().startswith('{'):
                data = json.loads(line)
                if 'backtest' in data:
                    return data['backtest']
    except:
        pass
    return None


def load_orders_from_files(prefix='orders'):
    """Load orders from local JSON files"""
    orders = []
    for i in range(1, 10):
        try:
            with open(f'/tmp/{prefix}{i}.json') as fp:
                data = json.load(fp)
                if 'orders' in data:
                    orders.extend(data['orders'])
        except:
            pass
    return orders


def get_end_prices(orders):
    """
    Get end prices by tracking the latest price seen for each ticker.
    Uses the most recent trade price (buy or sell) as proxy for current price.
    """
    # Sort orders by time
    sorted_orders = sorted(orders, key=lambda x: x.get('time', ''))

    end_prices = {}
    for order in sorted_orders:
        ticker = order.get('symbol', {}).get('value', 'UNKNOWN')
        price = float(order.get('price', 0))
        if price > 0:
            end_prices[ticker] = price  # Keep updating to get latest

    return end_prices


def calc_pnl(orders, end_prices):
    """Calculate P&L per ticker using FIFO"""
    positions = defaultdict(list)  # ticker -> [(qty, price), ...]
    realized_pnl = defaultdict(float)

    for order in sorted(orders, key=lambda x: x.get('time', '')):
        ticker = order.get('symbol', {}).get('value', 'UNKNOWN')
        direction = order.get('direction', 0)  # 0=Buy, 1=Sell
        qty = abs(float(order.get('quantity', 0)))
        price = float(order.get('price', 0))

        if direction == 0:  # Buy
            positions[ticker].append((qty, price))
        else:  # Sell
            remaining = qty
            while remaining > 0 and positions[ticker]:
                pos_qty, pos_price = positions[ticker][0]
                if pos_qty <= remaining:
                    realized_pnl[ticker] += pos_qty * (price - pos_price)
                    remaining -= pos_qty
                    positions[ticker].pop(0)
                else:
                    realized_pnl[ticker] += remaining * (price - pos_price)
                    positions[ticker][0] = (pos_qty - remaining, pos_price)
                    remaining = 0

    # Calculate unrealized P&L using end prices
    unrealized_pnl = defaultdict(float)
    cost_basis = defaultdict(float)

    for ticker, pos_list in positions.items():
        end_price = end_prices.get(ticker, 0)
        for qty, entry_price in pos_list:
            cost_basis[ticker] += qty * entry_price
            if end_price > 0:
                unrealized_pnl[ticker] += qty * (end_price - entry_price)

    return realized_pnl, unrealized_pnl, cost_basis, positions


def main():
    # Check if project_id and backtest_id provided
    if len(sys.argv) >= 3:
        project_id = sys.argv[1]
        backtest_id = sys.argv[2]
        print(f"Fetching orders from QC API: project={project_id}, backtest={backtest_id}")
        orders = fetch_orders(project_id, backtest_id)
        stats = fetch_backtest_stats(project_id, backtest_id)
    else:
        # Load from files
        prefix = sys.argv[1] if len(sys.argv) > 1 else 'orders'
        print(f"Loading orders from /tmp/{prefix}*.json files")
        orders = load_orders_from_files(prefix)
        stats = None

    if not orders:
        print("No orders found")
        return

    # Get end prices from orders
    end_prices = get_end_prices(orders)

    # Calculate P&L
    realized, unrealized, cost_basis, positions = calc_pnl(orders, end_prices)

    # Get all tickers
    all_tickers = set(realized.keys()) | set(unrealized.keys())

    print(f"\n{'='*100}")
    print(f"{'TICKER':<8} {'REALIZED P&L':>15} {'UNREALIZED':>14} {'TOTAL P&L':>15} {'SHARES':>8} {'COST BASIS':>12}")
    print(f"{'='*100}")

    total_realized = 0
    total_unrealized = 0
    total_cost = 0

    results = []
    for ticker in sorted(all_tickers):
        r = realized.get(ticker, 0)
        u = unrealized.get(ticker, 0)
        c = cost_basis.get(ticker, 0)
        total = r + u
        open_qty = sum(q for q, _ in positions.get(ticker, []))
        results.append((ticker, r, u, total, open_qty, c))
        total_realized += r
        total_unrealized += u
        total_cost += c

    # Sort by total P&L descending
    results.sort(key=lambda x: x[3], reverse=True)

    for ticker, r, u, total, open_qty, c in results:
        cost_str = f"${c:>10,.0f}" if c > 0 else f"{'':>11}"
        shares_str = f"{open_qty:>7,.0f}" if open_qty > 0 else f"{'':>7}"
        print(f"{ticker:<8} ${r:>14,.2f} ${u:>13,.2f} ${total:>14,.2f} {shares_str} {cost_str}")

    print(f"{'='*100}")
    print(f"{'TOTAL':<8} ${total_realized:>14,.2f} ${total_unrealized:>13,.2f} ${total_realized + total_unrealized:>14,.2f}")

    # Show backtest stats if available
    if stats:
        portfolio = stats.get('totalPerformance', {}).get('portfolioStatistics', {})
        if portfolio:
            print(f"\n--- Backtest Statistics ---")
            print(f"Start Equity:  ${float(portfolio.get('startEquity', 0)):>15,.2f}")
            print(f"End Equity:    ${float(portfolio.get('endEquity', 0)):>15,.2f}")
            print(f"CAGR:          {float(portfolio.get('compoundingAnnualReturn', 0))*100:>15.2f}%")
            print(f"Sharpe:        {float(portfolio.get('sharpeRatio', 0)):>15.3f}")
            print(f"Max Drawdown:  {float(portfolio.get('drawdown', 0))*100:>15.2f}%")

    # Open positions detail
    print(f"\n{'='*100}")
    print("OPEN POSITIONS (End of Backtest)")
    print(f"{'='*100}")
    print(f"{'TICKER':<8} {'SHARES':>10} {'AVG COST':>12} {'END PRICE':>12} {'UNREALIZED':>14} {'% GAIN':>10}")
    print(f"{'-'*100}")

    open_positions = [(t, q, c, u) for t, r, u, total, q, c in results if q > 0]
    open_positions.sort(key=lambda x: x[3], reverse=True)

    for ticker, shares, cost, unrealized_val in open_positions:
        avg_cost = cost / shares if shares > 0 else 0
        end_price = end_prices.get(ticker, 0)
        pct_gain = ((end_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0
        print(f"{ticker:<8} {shares:>10,.0f} ${avg_cost:>10,.2f} ${end_price:>10,.2f} ${unrealized_val:>13,.2f} {pct_gain:>9.1f}%")

    print(f"\nTotal orders: {len(orders)}")
    print(f"Open positions: {len(open_positions)}")
    print(f"Total cost basis: ${total_cost:,.0f}")
    print(f"Total unrealized: ${total_unrealized:,.2f}")

    # Show end prices used
    print(f"\n--- End Prices (from latest trades) ---")
    for ticker in sorted(end_prices.keys()):
        if any(t == ticker and q > 0 for t, q, c, u in open_positions):
            print(f"{ticker}: ${end_prices[ticker]:.2f}")

    print(f"\nNote: End prices are derived from the LATEST trade for each ticker.")
    print(f"If the last trade was a BUY (entry), end price = cost, so unrealized = $0.")
    print(f"This is expected for positions opened near end of backtest.")


if __name__ == '__main__':
    main()
