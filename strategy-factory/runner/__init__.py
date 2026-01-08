"""
Runner Module for Strategy Factory

Handles backtest execution, results parsing, and storage.
"""

from .results_storage import (
    ResultsStorage,
    save_backtest_results,
    load_strategy_results,
    update_comparison_table,
)

__all__ = [
    'ResultsStorage',
    'save_backtest_results',
    'load_strategy_results',
    'update_comparison_table',
]
