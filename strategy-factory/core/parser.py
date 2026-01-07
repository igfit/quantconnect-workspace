"""
Results Parser

Extracts and normalizes metrics from QuantConnect backtest results.
"""

import os
import json
import csv
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


@dataclass
class ParsedMetrics:
    """Normalized metrics from a backtest"""
    # Identification
    strategy_id: str
    backtest_id: str
    name: str

    # Performance
    total_return: float  # As decimal (0.25 = 25%)
    cagr: float  # Compound annual growth rate
    sharpe_ratio: float
    sortino_ratio: float

    # Risk
    max_drawdown: float  # As decimal (0.15 = 15%)
    volatility: float

    # Trading
    total_trades: int
    win_rate: float  # As decimal
    profit_factor: float
    avg_win: float
    avg_loss: float

    # Other
    alpha: float
    beta: float
    information_ratio: float
    treynor_ratio: float

    # Metadata
    start_date: str
    end_date: str
    initial_capital: float
    final_equity: float

    # Raw statistics for reference
    raw_statistics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def passes_thresholds(self) -> bool:
        """Check if metrics pass minimum thresholds"""
        if self.sharpe_ratio < config.MIN_SHARPE_RATIO:
            return False
        if self.cagr < config.MIN_CAGR:
            return False
        if self.max_drawdown > config.MAX_DRAWDOWN:
            return False
        if self.total_trades < config.MIN_TRADE_COUNT:
            return False
        if self.win_rate < config.MIN_WIN_RATE:
            return False
        if self.profit_factor < config.MIN_PROFIT_FACTOR:
            return False
        return True

    def is_disqualified(self) -> bool:
        """Check if strategy should be disqualified"""
        if self.max_drawdown > config.DISQUALIFY_MAX_DRAWDOWN:
            return True
        return False

    def get_summary(self) -> str:
        """Get a human-readable summary"""
        status = "PASS" if self.passes_thresholds() else "FAIL"
        if self.is_disqualified():
            status = "DISQUALIFIED"

        return (
            f"{self.name} ({self.strategy_id}) - {status}\n"
            f"  Sharpe: {self.sharpe_ratio:.2f}, CAGR: {self.cagr*100:.1f}%, "
            f"MaxDD: {self.max_drawdown*100:.1f}%\n"
            f"  Trades: {self.total_trades}, Win Rate: {self.win_rate*100:.1f}%, "
            f"Profit Factor: {self.profit_factor:.2f}"
        )


class ResultsParser:
    """Parse and extract metrics from QC backtest results"""

    def parse(
        self,
        raw_response: Dict[str, Any],
        strategy_id: str,
        backtest_id: str,
        name: str = ""
    ) -> ParsedMetrics:
        """
        Parse raw QC API response into normalized metrics.

        Args:
            raw_response: Raw response from QC API
            strategy_id: Strategy ID
            backtest_id: Backtest ID
            name: Strategy name

        Returns:
            ParsedMetrics object
        """
        backtest = raw_response.get("backtest", {})
        stats = backtest.get("statistics", {})

        # Helper to safely get float values
        def get_float(key: str, default: float = 0.0) -> float:
            value = stats.get(key, default)
            if isinstance(value, str):
                # Remove % signs and convert
                value = value.replace('%', '').replace('$', '').replace(',', '')
                try:
                    return float(value)
                except ValueError:
                    return default
            return float(value) if value is not None else default

        def get_pct(key: str, default: float = 0.0) -> float:
            """Get percentage value and convert to decimal"""
            value = get_float(key, default * 100)
            # QC returns percentages as whole numbers (e.g., 25 for 25%)
            # But some might already be decimals, so check magnitude
            if abs(value) > 10:  # Likely a percentage like 25%
                return value / 100
            return value

        # Extract metrics
        # Note: QC API uses "Total Orders" not "Total Trades", "Net Profit" not "Total Net Profit"
        return ParsedMetrics(
            strategy_id=strategy_id,
            backtest_id=backtest_id,
            name=name or backtest.get("name", "Unknown"),

            # Performance
            total_return=get_pct("Net Profit", 0),
            cagr=get_pct("Compounding Annual Return", 0),
            sharpe_ratio=get_float("Sharpe Ratio", 0),
            sortino_ratio=get_float("Sortino Ratio", 0),

            # Risk
            max_drawdown=abs(get_pct("Drawdown", 0)),
            volatility=get_pct("Annual Standard Deviation", 0),

            # Trading - QC uses "Total Orders" not "Total Trades"
            total_trades=int(get_float("Total Orders", 0)),
            win_rate=get_pct("Win Rate", 0),
            profit_factor=get_float("Profit-Loss Ratio", 1),
            avg_win=get_float("Average Win", 0),
            avg_loss=abs(get_float("Average Loss", 0)),

            # Other
            alpha=get_float("Alpha", 0),
            beta=get_float("Beta", 0),
            information_ratio=get_float("Information Ratio", 0),
            treynor_ratio=get_float("Treynor Ratio", 0),

            # Metadata - QC uses "Start Equity" and "End Equity"
            start_date=backtest.get("created", ""),
            end_date=backtest.get("ended", ""),
            initial_capital=get_float("Start Equity", config.DEFAULT_INITIAL_CAPITAL),
            final_equity=get_float("End Equity", 0),

            raw_statistics=stats
        )

    def save_metrics(self, metrics: ParsedMetrics, strategy_id: str) -> str:
        """
        Save metrics to JSON file.

        Returns:
            Filepath
        """
        result_dir = os.path.join(config.RESULTS_DIR, strategy_id)
        os.makedirs(result_dir, exist_ok=True)

        filepath = os.path.join(result_dir, "metrics.json")
        with open(filepath, 'w') as f:
            json.dump(metrics.to_dict(), f, indent=2)

        return filepath

    def load_metrics(self, strategy_id: str) -> Optional[ParsedMetrics]:
        """Load metrics from JSON file"""
        filepath = os.path.join(config.RESULTS_DIR, strategy_id, "metrics.json")
        if not os.path.exists(filepath):
            return None

        with open(filepath, 'r') as f:
            data = json.load(f)

        # Reconstruct ParsedMetrics
        return ParsedMetrics(**data)

    def save_summary_csv(self, metrics_list: List[ParsedMetrics], filename: str = "summary.csv"):
        """
        Save multiple metrics to a summary CSV file.

        Args:
            metrics_list: List of ParsedMetrics
            filename: Output filename
        """
        if not metrics_list:
            return

        filepath = os.path.join(config.RESULTS_DIR, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # Define columns
        columns = [
            "strategy_id", "name", "sharpe_ratio", "cagr", "max_drawdown",
            "total_trades", "win_rate", "profit_factor", "alpha", "beta",
            "passes_thresholds", "is_disqualified"
        ]

        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(columns)

            for m in metrics_list:
                row = [
                    m.strategy_id,
                    m.name,
                    f"{m.sharpe_ratio:.3f}",
                    f"{m.cagr*100:.2f}%",
                    f"{m.max_drawdown*100:.2f}%",
                    m.total_trades,
                    f"{m.win_rate*100:.1f}%",
                    f"{m.profit_factor:.2f}",
                    f"{m.alpha:.3f}",
                    f"{m.beta:.3f}",
                    m.passes_thresholds(),
                    m.is_disqualified()
                ]
                writer.writerow(row)

        print(f"Summary saved to: {filepath}")
        return filepath


def parse_backtest_result(
    raw_response: Dict[str, Any],
    strategy_id: str,
    backtest_id: str,
    name: str = ""
) -> ParsedMetrics:
    """Convenience function to parse backtest results"""
    parser = ResultsParser()
    return parser.parse(raw_response, strategy_id, backtest_id, name)


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    # Test with sample data matching actual QC API response format
    sample_response = {
        "success": True,
        "backtest": {
            "backtestId": "test-123",
            "name": "Test Strategy",
            "statistics": {
                "Net Profit": "25.5%",  # QC uses "Net Profit" not "Total Net Profit"
                "Compounding Annual Return": "15.2%",
                "Sharpe Ratio": "1.25",
                "Sortino Ratio": "1.8",
                "Drawdown": "12.5%",
                "Annual Standard Deviation": "0.18",  # Can be decimal
                "Total Orders": "45",  # QC uses "Total Orders" not "Total Trades"
                "Win Rate": "55%",
                "Profit-Loss Ratio": "1.65",
                "Average Win": "2.50%",
                "Average Loss": "-1.50%",
                "Alpha": "0.05",
                "Beta": "0.85",
                "Start Equity": "100000",  # QC uses "Start Equity"
                "End Equity": "125500",  # QC uses "End Equity"
            }
        }
    }

    print("Testing Results Parser...")
    parser = ResultsParser()
    metrics = parser.parse(sample_response, "test-strategy", "test-123")

    print("\nParsed Metrics:")
    print(metrics.get_summary())

    print(f"\nPasses thresholds: {metrics.passes_thresholds()}")
    print(f"Is disqualified: {metrics.is_disqualified()}")
