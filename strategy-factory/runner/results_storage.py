#!/usr/bin/env python3
"""
Results Storage Utility for Strategy Factory

Saves and manages backtest results with:
- Full order history (orders.csv)
- Round-trip trades (trades.csv)
- P&L by ticker (pnl_by_ticker.csv)
- Summary metrics (metrics.json)
- Equity curve (equity_curve.csv)
- Cross-strategy comparison table

Directory structure:
    backtests/
    ├── {strategy_name}/
    │   ├── {backtest_id}/
    │   │   ├── orders.csv
    │   │   ├── trades.csv
    │   │   ├── pnl_by_ticker.csv
    │   │   ├── metrics.json
    │   │   └── config.json
    │   └── summary.csv
    └── comparison/
        └── all_strategies.csv
"""

import os
import sys
import json
import csv
import hashlib
import base64
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict
from dataclasses import dataclass, asdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import requests
except ImportError:
    requests = None


@dataclass
class BacktestMetrics:
    """Summary metrics for a backtest"""
    strategy_name: str
    universe: str
    backtest_id: str
    period_start: str
    period_end: str
    starting_capital: float = 100000.0
    ending_equity: float = 0.0
    cagr: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    total_trades: int = 0
    win_rate: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    risk_reward: float = 0.0
    profit_factor: float = 0.0
    avg_bars_held: int = 0
    time_in_market: float = 0.0
    total_fees: float = 0.0
    net_profit: float = 0.0

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class Trade:
    """Round-trip trade record"""
    symbol: str
    entry_date: str
    exit_date: str
    direction: str  # "Long" or "Short"
    shares: float
    entry_price: float
    exit_price: float
    pnl_dollars: float
    pnl_pct: float
    bars_held: int
    fees: float = 0.0


class ResultsStorage:
    """
    Manages storage and retrieval of backtest results.
    """

    def __init__(self, base_dir: str = None):
        """
        Initialize storage with base directory.

        Args:
            base_dir: Base directory for results (default: backtests/)
        """
        if base_dir is None:
            # Default to project root's backtests directory
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            base_dir = os.path.join(project_root, "backtests")

        self.base_dir = base_dir
        self.comparison_dir = os.path.join(base_dir, "comparison")

        # Ensure directories exist
        os.makedirs(self.base_dir, exist_ok=True)
        os.makedirs(self.comparison_dir, exist_ok=True)

    def get_strategy_dir(self, strategy_name: str) -> str:
        """Get directory for a strategy's results"""
        safe_name = strategy_name.lower().replace(" ", "_").replace("-", "_")
        path = os.path.join(self.base_dir, safe_name)
        os.makedirs(path, exist_ok=True)
        return path

    def get_backtest_dir(self, strategy_name: str, backtest_id: str) -> str:
        """Get directory for a specific backtest's results"""
        strategy_dir = self.get_strategy_dir(strategy_name)
        # Use short hash for directory name
        short_id = backtest_id[:12] if len(backtest_id) > 12 else backtest_id
        path = os.path.join(strategy_dir, short_id)
        os.makedirs(path, exist_ok=True)
        return path

    def save_orders(self, strategy_name: str, backtest_id: str, orders: List[Dict]) -> str:
        """
        Save orders to CSV.

        Args:
            strategy_name: Name of the strategy
            backtest_id: Backtest ID
            orders: List of order dictionaries from QC API

        Returns:
            Path to saved file
        """
        bt_dir = self.get_backtest_dir(strategy_name, backtest_id)
        filepath = os.path.join(bt_dir, "orders.csv")

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'date', 'symbol', 'direction', 'quantity', 'fill_price',
                'value', 'fees', 'order_id', 'status'
            ])

            for order in orders:
                symbol = order.get('symbol', {}).get('value', 'UNKNOWN')
                qty = order.get('quantity', 0)
                price = order.get('price', 0)
                value = abs(qty * price)
                fees = order.get('orderFee', {}).get('value', {}).get('amount', 0)
                order_id = order.get('id', '')
                status = order.get('status', '')
                created = order.get('createdTime', '')
                direction = 'Buy' if qty > 0 else 'Sell'

                writer.writerow([
                    created, symbol, direction, abs(qty), price,
                    value, fees, order_id, status
                ])

        return filepath

    def save_trades(self, strategy_name: str, backtest_id: str, trades: List[Trade]) -> str:
        """
        Save round-trip trades to CSV.

        Args:
            strategy_name: Name of the strategy
            backtest_id: Backtest ID
            trades: List of Trade objects

        Returns:
            Path to saved file
        """
        bt_dir = self.get_backtest_dir(strategy_name, backtest_id)
        filepath = os.path.join(bt_dir, "trades.csv")

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'symbol', 'entry_date', 'exit_date', 'direction', 'shares',
                'entry_price', 'exit_price', 'pnl_dollars', 'pnl_pct', 'bars_held', 'fees'
            ])

            for trade in trades:
                writer.writerow([
                    trade.symbol, trade.entry_date, trade.exit_date, trade.direction,
                    trade.shares, trade.entry_price, trade.exit_price,
                    trade.pnl_dollars, f"{trade.pnl_pct:.2%}", trade.bars_held, trade.fees
                ])

        return filepath

    def save_pnl_by_ticker(self, strategy_name: str, backtest_id: str,
                           pnl_data: Dict[str, Dict]) -> str:
        """
        Save P&L breakdown by ticker to CSV.

        Args:
            strategy_name: Name of the strategy
            backtest_id: Backtest ID
            pnl_data: Dict of {symbol: {total_trades, wins, losses, ...}}

        Returns:
            Path to saved file
        """
        bt_dir = self.get_backtest_dir(strategy_name, backtest_id)
        filepath = os.path.join(bt_dir, "pnl_by_ticker.csv")

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'symbol', 'total_trades', 'wins', 'losses', 'win_rate',
                'realized_pnl', 'unrealized_pnl', 'total_pnl',
                'avg_win', 'avg_loss', 'rr_ratio'
            ])

            for symbol, data in sorted(pnl_data.items(), key=lambda x: x[1].get('total_pnl', 0), reverse=True):
                win_rate = data.get('wins', 0) / data.get('total_trades', 1) if data.get('total_trades', 0) > 0 else 0
                writer.writerow([
                    symbol,
                    data.get('total_trades', 0),
                    data.get('wins', 0),
                    data.get('losses', 0),
                    f"{win_rate:.1%}",
                    f"{data.get('realized_pnl', 0):.2f}",
                    f"{data.get('unrealized_pnl', 0):.2f}",
                    f"{data.get('total_pnl', 0):.2f}",
                    f"{data.get('avg_win', 0):.1%}" if data.get('avg_win') else "N/A",
                    f"{data.get('avg_loss', 0):.1%}" if data.get('avg_loss') else "N/A",
                    f"{data.get('rr_ratio', 0):.2f}" if data.get('rr_ratio') else "N/A",
                ])

        return filepath

    def save_metrics(self, strategy_name: str, backtest_id: str,
                     metrics: BacktestMetrics) -> str:
        """
        Save summary metrics to JSON.

        Args:
            strategy_name: Name of the strategy
            backtest_id: Backtest ID
            metrics: BacktestMetrics object

        Returns:
            Path to saved file
        """
        bt_dir = self.get_backtest_dir(strategy_name, backtest_id)
        filepath = os.path.join(bt_dir, "metrics.json")

        with open(filepath, 'w') as f:
            json.dump(metrics.to_dict(), f, indent=2)

        return filepath

    def save_config(self, strategy_name: str, backtest_id: str,
                    config: Dict) -> str:
        """
        Save strategy configuration used for this backtest.

        Args:
            strategy_name: Name of the strategy
            backtest_id: Backtest ID
            config: Configuration dictionary

        Returns:
            Path to saved file
        """
        bt_dir = self.get_backtest_dir(strategy_name, backtest_id)
        filepath = os.path.join(bt_dir, "config.json")

        with open(filepath, 'w') as f:
            json.dump(config, f, indent=2)

        return filepath

    def update_strategy_summary(self, strategy_name: str, metrics: BacktestMetrics):
        """
        Update the strategy's summary CSV with a new backtest result.

        Args:
            strategy_name: Name of the strategy
            metrics: BacktestMetrics for this backtest
        """
        strategy_dir = self.get_strategy_dir(strategy_name)
        filepath = os.path.join(strategy_dir, "summary.csv")

        # Check if file exists to determine if we need headers
        write_header = not os.path.exists(filepath)

        with open(filepath, 'a', newline='') as f:
            writer = csv.writer(f)

            if write_header:
                writer.writerow([
                    'timestamp', 'backtest_id', 'universe', 'period',
                    'sharpe', 'cagr', 'max_dd', 'win_rate',
                    'avg_win', 'avg_loss', 'rr', 'trades', 'net_profit'
                ])

            writer.writerow([
                datetime.now().isoformat(),
                metrics.backtest_id[:12],
                metrics.universe,
                f"{metrics.period_start} to {metrics.period_end}",
                f"{metrics.sharpe:.2f}",
                f"{metrics.cagr:.1f}%",
                f"{metrics.max_drawdown:.1f}%",
                f"{metrics.win_rate:.1f}%",
                f"{metrics.avg_win_pct:.1f}%",
                f"{metrics.avg_loss_pct:.1f}%",
                f"{metrics.risk_reward:.2f}",
                metrics.total_trades,
                f"${metrics.net_profit:,.0f}",
            ])

    def update_comparison_table(self, metrics: BacktestMetrics):
        """
        Update the cross-strategy comparison table.

        Args:
            metrics: BacktestMetrics for this backtest
        """
        filepath = os.path.join(self.comparison_dir, "all_strategies.csv")

        # Check if file exists to determine if we need headers
        write_header = not os.path.exists(filepath)

        with open(filepath, 'a', newline='') as f:
            writer = csv.writer(f)

            if write_header:
                writer.writerow([
                    'timestamp', 'strategy', 'universe', 'period', 'backtest_id',
                    'sharpe', 'cagr', 'max_dd', 'win_rate',
                    'avg_win', 'avg_loss', 'rr', 'trades_yr', 'avg_days',
                    'net_profit', 'ending_equity'
                ])

            # Calculate trades per year
            try:
                start = datetime.strptime(metrics.period_start[:10], "%Y-%m-%d")
                end = datetime.strptime(metrics.period_end[:10], "%Y-%m-%d")
                years = (end - start).days / 365.25
                trades_per_year = metrics.total_trades / years if years > 0 else 0
            except:
                trades_per_year = 0

            writer.writerow([
                datetime.now().isoformat(),
                metrics.strategy_name,
                metrics.universe,
                f"{metrics.period_start[:10]} to {metrics.period_end[:10]}",
                metrics.backtest_id[:12],
                f"{metrics.sharpe:.2f}",
                f"{metrics.cagr:.1f}%",
                f"{metrics.max_drawdown:.1f}%",
                f"{metrics.win_rate:.1f}%",
                f"{metrics.avg_win_pct:.1f}%",
                f"{metrics.avg_loss_pct:.1f}%",
                f"{metrics.risk_reward:.2f}",
                f"{trades_per_year:.0f}",
                f"{metrics.avg_bars_held}",
                f"${metrics.net_profit:,.0f}",
                f"${metrics.ending_equity:,.0f}",
            ])

    def load_metrics(self, strategy_name: str, backtest_id: str) -> Optional[BacktestMetrics]:
        """
        Load metrics for a specific backtest.

        Args:
            strategy_name: Name of the strategy
            backtest_id: Backtest ID

        Returns:
            BacktestMetrics object or None if not found
        """
        bt_dir = self.get_backtest_dir(strategy_name, backtest_id)
        filepath = os.path.join(bt_dir, "metrics.json")

        if not os.path.exists(filepath):
            return None

        with open(filepath, 'r') as f:
            data = json.load(f)
            return BacktestMetrics(**data)


def calculate_trades_from_orders(orders: List[Dict]) -> List[Trade]:
    """
    Calculate round-trip trades from order list using FIFO matching.

    Args:
        orders: List of order dictionaries from QC API

    Returns:
        List of Trade objects
    """
    # Group orders by symbol
    symbol_orders = defaultdict(list)
    for order in orders:
        symbol = order.get('symbol', {}).get('value', 'UNKNOWN')
        symbol_orders[symbol].append(order)

    trades = []

    for symbol, sym_orders in symbol_orders.items():
        # Sort by date
        sym_orders.sort(key=lambda x: x.get('createdTime', ''))

        # Track open lots for FIFO matching
        open_lots = []  # [{qty, price, date}]

        for order in sym_orders:
            qty = order.get('quantity', 0)
            price = order.get('price', 0)
            date = order.get('createdTime', '')[:10]
            fees = order.get('orderFee', {}).get('value', {}).get('amount', 0)

            if qty > 0:
                # Buy - add to open lots
                open_lots.append({
                    'qty': qty,
                    'price': price,
                    'date': date,
                    'fees': fees,
                })
            elif qty < 0 and open_lots:
                # Sell - match against open lots (FIFO)
                shares_to_close = abs(qty)
                exit_price = price
                exit_date = date

                while shares_to_close > 0 and open_lots:
                    lot = open_lots[0]

                    if lot['qty'] <= shares_to_close:
                        # Close entire lot
                        pnl_dollars = (exit_price - lot['price']) * lot['qty']
                        pnl_pct = (exit_price - lot['price']) / lot['price'] if lot['price'] > 0 else 0

                        # Calculate days held
                        try:
                            entry_dt = datetime.strptime(lot['date'], "%Y-%m-%d")
                            exit_dt = datetime.strptime(exit_date, "%Y-%m-%d")
                            bars_held = (exit_dt - entry_dt).days
                        except:
                            bars_held = 0

                        trades.append(Trade(
                            symbol=symbol,
                            entry_date=lot['date'],
                            exit_date=exit_date,
                            direction="Long",
                            shares=lot['qty'],
                            entry_price=lot['price'],
                            exit_price=exit_price,
                            pnl_dollars=pnl_dollars,
                            pnl_pct=pnl_pct,
                            bars_held=bars_held,
                            fees=lot['fees'] + fees,
                        ))

                        shares_to_close -= lot['qty']
                        open_lots.pop(0)
                    else:
                        # Partial lot close
                        pnl_dollars = (exit_price - lot['price']) * shares_to_close
                        pnl_pct = (exit_price - lot['price']) / lot['price'] if lot['price'] > 0 else 0

                        try:
                            entry_dt = datetime.strptime(lot['date'], "%Y-%m-%d")
                            exit_dt = datetime.strptime(exit_date, "%Y-%m-%d")
                            bars_held = (exit_dt - entry_dt).days
                        except:
                            bars_held = 0

                        trades.append(Trade(
                            symbol=symbol,
                            entry_date=lot['date'],
                            exit_date=exit_date,
                            direction="Long",
                            shares=shares_to_close,
                            entry_price=lot['price'],
                            exit_price=exit_price,
                            pnl_dollars=pnl_dollars,
                            pnl_pct=pnl_pct,
                            bars_held=bars_held,
                            fees=fees,  # Allocate exit fees to this trade
                        ))

                        lot['qty'] -= shares_to_close
                        shares_to_close = 0

    return trades


def calculate_pnl_by_ticker(trades: List[Trade]) -> Dict[str, Dict]:
    """
    Calculate P&L summary by ticker from trades.

    Args:
        trades: List of Trade objects

    Returns:
        Dict of {symbol: {total_trades, wins, losses, ...}}
    """
    pnl_data = defaultdict(lambda: {
        'total_trades': 0,
        'wins': 0,
        'losses': 0,
        'realized_pnl': 0.0,
        'unrealized_pnl': 0.0,  # Would need current prices for this
        'total_pnl': 0.0,
        'win_pnls': [],
        'loss_pnls': [],
    })

    for trade in trades:
        symbol = trade.symbol
        pnl_data[symbol]['total_trades'] += 1
        pnl_data[symbol]['realized_pnl'] += trade.pnl_dollars
        pnl_data[symbol]['total_pnl'] += trade.pnl_dollars

        if trade.pnl_dollars > 0:
            pnl_data[symbol]['wins'] += 1
            pnl_data[symbol]['win_pnls'].append(trade.pnl_pct)
        else:
            pnl_data[symbol]['losses'] += 1
            pnl_data[symbol]['loss_pnls'].append(trade.pnl_pct)

    # Calculate averages
    for symbol, data in pnl_data.items():
        if data['win_pnls']:
            data['avg_win'] = sum(data['win_pnls']) / len(data['win_pnls'])
        else:
            data['avg_win'] = 0

        if data['loss_pnls']:
            data['avg_loss'] = sum(data['loss_pnls']) / len(data['loss_pnls'])
        else:
            data['avg_loss'] = 0

        if data['avg_loss'] != 0:
            data['rr_ratio'] = abs(data['avg_win'] / data['avg_loss'])
        else:
            data['rr_ratio'] = 0

        # Clean up temporary lists
        del data['win_pnls']
        del data['loss_pnls']

    return dict(pnl_data)


# ============================================================================
# Convenience Functions
# ============================================================================

def save_backtest_results(
    strategy_name: str,
    backtest_id: str,
    orders: List[Dict],
    stats: Dict,
    universe: str = "unknown",
    config: Dict = None,
    base_dir: str = None
) -> str:
    """
    Save all backtest results in one call.

    Args:
        strategy_name: Name of the strategy
        backtest_id: Backtest ID from QC
        orders: List of orders from QC API
        stats: Backtest stats from QC API
        universe: Universe name (e.g., "etf_core", "sector_spdrs")
        config: Strategy configuration (optional)
        base_dir: Base directory for results

    Returns:
        Path to backtest results directory
    """
    storage = ResultsStorage(base_dir)

    # Save orders
    storage.save_orders(strategy_name, backtest_id, orders)

    # Calculate and save trades
    trades = calculate_trades_from_orders(orders)
    storage.save_trades(strategy_name, backtest_id, trades)

    # Calculate and save P&L by ticker
    pnl_data = calculate_pnl_by_ticker(trades)
    storage.save_pnl_by_ticker(strategy_name, backtest_id, pnl_data)

    # Extract metrics from stats
    runtime = stats.get('runtimeStatistics', {})

    # Parse values
    def parse_value(s):
        if isinstance(s, (int, float)):
            return float(s)
        try:
            return float(s.replace('$', '').replace(',', '').replace('%', '').replace('-', ''))
        except:
            return 0.0

    # Calculate trade statistics
    total_trades = len(trades)
    winners = [t for t in trades if t.pnl_dollars > 0]
    losers = [t for t in trades if t.pnl_dollars <= 0]
    win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0
    avg_win = sum(t.pnl_pct for t in winners) / len(winners) * 100 if winners else 0
    avg_loss = sum(t.pnl_pct for t in losers) / len(losers) * 100 if losers else 0
    avg_bars = sum(t.bars_held for t in trades) / total_trades if total_trades > 0 else 0
    risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else 0

    metrics = BacktestMetrics(
        strategy_name=strategy_name,
        universe=universe,
        backtest_id=backtest_id,
        period_start=stats.get('backtestStart', ''),
        period_end=stats.get('backtestEnd', ''),
        starting_capital=100000.0,
        ending_equity=parse_value(runtime.get('Equity', '0')),
        cagr=parse_value(runtime.get('Compounding Annual Return', '0')),
        sharpe=parse_value(runtime.get('Sharpe Ratio', '0')),
        max_drawdown=parse_value(runtime.get('Drawdown', '0')),
        total_trades=total_trades,
        win_rate=win_rate,
        avg_win_pct=avg_win,
        avg_loss_pct=avg_loss,
        risk_reward=risk_reward,
        profit_factor=parse_value(runtime.get('Profit-Loss Ratio', '0')),
        avg_bars_held=int(avg_bars),
        total_fees=parse_value(runtime.get('Fees', '0')),
        net_profit=parse_value(runtime.get('Net Profit', '0')),
    )

    # Save metrics
    storage.save_metrics(strategy_name, backtest_id, metrics)

    # Save config if provided
    if config:
        storage.save_config(strategy_name, backtest_id, config)

    # Update summary tables
    storage.update_strategy_summary(strategy_name, metrics)
    storage.update_comparison_table(metrics)

    return storage.get_backtest_dir(strategy_name, backtest_id)


def load_strategy_results(strategy_name: str, backtest_id: str,
                          base_dir: str = None) -> Optional[BacktestMetrics]:
    """Load metrics for a specific backtest."""
    storage = ResultsStorage(base_dir)
    return storage.load_metrics(strategy_name, backtest_id)


def update_comparison_table(metrics: BacktestMetrics, base_dir: str = None):
    """Update the cross-strategy comparison table."""
    storage = ResultsStorage(base_dir)
    storage.update_comparison_table(metrics)


if __name__ == "__main__":
    # Test the module
    print("Results Storage Module")
    print("=" * 50)

    storage = ResultsStorage()
    print(f"Base directory: {storage.base_dir}")
    print(f"Comparison directory: {storage.comparison_dir}")

    # Test directory creation
    test_dir = storage.get_strategy_dir("test_strategy")
    print(f"Strategy directory: {test_dir}")

    bt_dir = storage.get_backtest_dir("test_strategy", "abc123def456")
    print(f"Backtest directory: {bt_dir}")
