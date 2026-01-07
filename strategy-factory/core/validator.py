"""
Strategy Validator

Performs walk-forward validation and regime analysis to ensure
strategies are robust and not overfit.
"""

import os
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.strategy_spec import StrategySpec
from core.parser import ParsedMetrics
import config


@dataclass
class ValidationResult:
    """Results from walk-forward validation"""
    strategy_id: str
    name: str

    # Walk-forward results by period
    train_metrics: Optional[ParsedMetrics]
    validate_metrics: Optional[ParsedMetrics]
    test_metrics: Optional[ParsedMetrics]

    # Consistency scores
    train_sharpe: float
    validate_sharpe: float
    test_sharpe: float

    # Overall validation
    passes_walk_forward: bool
    consistency_score: float  # 0-1, higher is better

    # Regime analysis
    bull_market_return: Optional[float]
    bear_market_return: Optional[float]
    sideways_return: Optional[float]
    regime_robustness: float  # 0-1

    # Final verdict
    is_valid: bool
    validation_notes: List[str]

    def get_summary(self) -> str:
        """Get human-readable summary"""
        status = "VALID" if self.is_valid else "INVALID"
        return (
            f"{self.name} - {status}\n"
            f"  Walk-Forward: Train={self.train_sharpe:.2f}, "
            f"Val={self.validate_sharpe:.2f}, Test={self.test_sharpe:.2f}\n"
            f"  Consistency: {self.consistency_score:.2f}, "
            f"Regime Robustness: {self.regime_robustness:.2f}\n"
            f"  Notes: {'; '.join(self.validation_notes)}"
        )


class StrategyValidator:
    """
    Validate strategies using walk-forward testing and regime analysis.

    Walk-forward validation ensures the strategy works on out-of-sample data.
    Regime analysis ensures it's not just a bull-market strategy.
    """

    def __init__(self, date_range: str = None):
        """
        Args:
            date_range: Date range config to use ("5_year" or "10_year")
        """
        self.date_range = date_range or config.ACTIVE_DATE_RANGE
        self.dates = config.DATE_RANGES[self.date_range]

    def validate_walk_forward(
        self,
        train_metrics: ParsedMetrics,
        validate_metrics: ParsedMetrics,
        test_metrics: ParsedMetrics
    ) -> Tuple[bool, float, List[str]]:
        """
        Validate using walk-forward results.

        Args:
            train_metrics: Results from training period
            validate_metrics: Results from validation period
            test_metrics: Results from test period

        Returns:
            (passes, consistency_score, notes)
        """
        notes = []

        # Extract Sharpe ratios
        train_sharpe = train_metrics.sharpe_ratio if train_metrics else 0
        val_sharpe = validate_metrics.sharpe_ratio if validate_metrics else 0
        test_sharpe = test_metrics.sharpe_ratio if test_metrics else 0

        # Check all periods are profitable
        all_profitable = all([
            train_sharpe > 0,
            val_sharpe > 0,
            test_sharpe > 0
        ])

        if not all_profitable:
            notes.append("Not profitable in all periods")

        # Check Sharpe decay
        # We expect some decay but not too much
        if train_sharpe > 0:
            val_decay = (train_sharpe - val_sharpe) / train_sharpe if train_sharpe else 1
            test_decay = (train_sharpe - test_sharpe) / train_sharpe if train_sharpe else 1

            if val_decay > 0.5:
                notes.append(f"High validation decay: {val_decay:.0%}")
            if test_decay > 0.5:
                notes.append(f"High test decay: {test_decay:.0%}")
        else:
            notes.append("Training period not profitable")

        # Calculate consistency score
        if train_sharpe > 0 and val_sharpe > 0 and test_sharpe > 0:
            # Score based on how close validation and test are to training
            val_ratio = min(val_sharpe / train_sharpe, 1.0)
            test_ratio = min(test_sharpe / train_sharpe, 1.0)
            consistency_score = (val_ratio + test_ratio) / 2

            # Bonus for test being close to validation (stability)
            if val_sharpe > 0:
                stability = 1 - abs(test_sharpe - val_sharpe) / val_sharpe
                consistency_score = (consistency_score + max(0, stability)) / 2
        else:
            consistency_score = 0

        # Determine pass/fail
        passes = (
            all_profitable and
            val_sharpe >= config.MIN_SHARPE_RATIO * 0.7 and  # Allow some decay
            test_sharpe >= config.MIN_SHARPE_RATIO * 0.5 and
            consistency_score >= 0.4
        )

        if passes:
            notes.append("Walk-forward validation passed")
        else:
            notes.append("Walk-forward validation failed")

        return passes, consistency_score, notes

    def analyze_regime_robustness(
        self,
        metrics: ParsedMetrics,
        benchmark_returns: Dict[str, float] = None
    ) -> Tuple[float, Dict[str, float], List[str]]:
        """
        Analyze performance across different market regimes.

        For now, this is a simplified version that checks if
        the strategy has reasonable drawdown (bear market proxy)
        and isn't purely correlated with the market.

        Args:
            metrics: Strategy metrics
            benchmark_returns: Optional benchmark returns by regime

        Returns:
            (robustness_score, regime_returns, notes)
        """
        notes = []
        regime_returns = {
            "bull": None,
            "bear": None,
            "sideways": None
        }

        # Simplified regime analysis based on available metrics
        # In a full implementation, we'd run separate backtests for each regime

        # Use alpha and beta as proxies for regime robustness
        alpha = metrics.alpha if metrics else 0
        beta = metrics.beta if metrics else 1

        # Good strategies have positive alpha (outperform benchmark)
        if alpha > 0.05:
            notes.append(f"Positive alpha: {alpha:.3f}")
            alpha_score = min(alpha / 0.1, 1.0)  # Cap at 10% alpha
        else:
            notes.append(f"Low or negative alpha: {alpha:.3f}")
            alpha_score = max(0, alpha / 0.1)

        # Beta between 0.5 and 1.5 is reasonable
        if 0.5 <= beta <= 1.5:
            beta_score = 1.0
        elif beta < 0.5:
            notes.append(f"Very low beta: {beta:.2f} (may underperform in bull)")
            beta_score = 0.5
        else:
            notes.append(f"High beta: {beta:.2f} (vulnerable in bear)")
            beta_score = max(0, 1.5 / beta)

        # Max drawdown as bear market proxy
        max_dd = metrics.max_drawdown if metrics else 0.5
        if max_dd < 0.15:
            dd_score = 1.0
            notes.append("Low drawdown, likely bear-resistant")
        elif max_dd < 0.25:
            dd_score = 0.7
        else:
            dd_score = max(0, 0.4 - (max_dd - 0.25))
            notes.append(f"High drawdown: {max_dd:.1%}")

        # Combined robustness score
        robustness_score = (alpha_score * 0.4 + beta_score * 0.3 + dd_score * 0.3)

        return robustness_score, regime_returns, notes

    def validate(
        self,
        strategy_id: str,
        name: str,
        full_metrics: ParsedMetrics,
        train_metrics: ParsedMetrics = None,
        validate_metrics: ParsedMetrics = None,
        test_metrics: ParsedMetrics = None
    ) -> ValidationResult:
        """
        Full validation of a strategy.

        Args:
            strategy_id: Strategy identifier
            name: Strategy name
            full_metrics: Metrics from full backtest period
            train_metrics: Optional training period metrics
            validate_metrics: Optional validation period metrics
            test_metrics: Optional test period metrics

        Returns:
            ValidationResult
        """
        notes = []

        # Walk-forward validation
        if train_metrics and validate_metrics and test_metrics:
            passes_wf, consistency, wf_notes = self.validate_walk_forward(
                train_metrics, validate_metrics, test_metrics
            )
            notes.extend(wf_notes)
        else:
            # Simplified validation with just full period
            passes_wf = full_metrics.passes_thresholds() if full_metrics else False
            consistency = 0.5 if passes_wf else 0
            notes.append("No walk-forward data, using full period only")

        # Regime analysis
        regime_score, regime_returns, regime_notes = self.analyze_regime_robustness(full_metrics)
        notes.extend(regime_notes)

        # Final verdict
        is_valid = (
            passes_wf and
            regime_score >= 0.3 and
            (full_metrics is None or not full_metrics.is_disqualified())
        )

        if full_metrics and full_metrics.is_disqualified():
            notes.append("Disqualified due to extreme metrics")
            is_valid = False

        return ValidationResult(
            strategy_id=strategy_id,
            name=name,
            train_metrics=train_metrics,
            validate_metrics=validate_metrics,
            test_metrics=test_metrics,
            train_sharpe=train_metrics.sharpe_ratio if train_metrics else 0,
            validate_sharpe=validate_metrics.sharpe_ratio if validate_metrics else 0,
            test_sharpe=test_metrics.sharpe_ratio if test_metrics else 0,
            passes_walk_forward=passes_wf,
            consistency_score=consistency,
            bull_market_return=regime_returns.get("bull"),
            bear_market_return=regime_returns.get("bear"),
            sideways_return=regime_returns.get("sideways"),
            regime_robustness=regime_score,
            is_valid=is_valid,
            validation_notes=notes
        )

    def quick_validate(self, metrics: ParsedMetrics) -> Tuple[bool, List[str]]:
        """
        Quick validation using only full-period metrics.

        Useful for initial filtering before full walk-forward validation.

        Args:
            metrics: Full period metrics

        Returns:
            (is_valid, notes)
        """
        notes = []

        if metrics.is_disqualified():
            notes.append("Disqualified")
            return False, notes

        if not metrics.passes_thresholds():
            notes.append("Does not meet minimum thresholds")
            return False, notes

        # Additional quick checks
        if metrics.total_trades < 20:
            notes.append("Too few trades for reliable statistics")
            return False, notes

        if metrics.sharpe_ratio > 4:
            notes.append("Suspiciously high Sharpe - possible overfitting")
            return False, notes

        notes.append("Passes quick validation")
        return True, notes


def validate_strategy(
    strategy_id: str,
    name: str,
    full_metrics: ParsedMetrics,
    train_metrics: ParsedMetrics = None,
    validate_metrics: ParsedMetrics = None,
    test_metrics: ParsedMetrics = None,
    date_range: str = None
) -> ValidationResult:
    """Convenience function for validation"""
    validator = StrategyValidator(date_range)
    return validator.validate(
        strategy_id, name, full_metrics,
        train_metrics, validate_metrics, test_metrics
    )


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    from core.parser import ParsedMetrics

    print("="*60)
    print("Strategy Validator Test")
    print("="*60)

    # Create mock metrics
    def create_mock_metrics(sharpe, cagr, max_dd, trades, name="Test"):
        return ParsedMetrics(
            strategy_id="test",
            backtest_id="test",
            name=name,
            total_return=cagr * 4,
            cagr=cagr,
            sharpe_ratio=sharpe,
            sortino_ratio=sharpe * 1.2,
            max_drawdown=max_dd,
            volatility=0.20,
            total_trades=trades,
            win_rate=0.55,
            profit_factor=1.5,
            avg_win=250,
            avg_loss=150,
            alpha=0.05,
            beta=0.9,
            information_ratio=0.5,
            treynor_ratio=0.1,
            start_date="2020-01-01",
            end_date="2024-12-31",
            initial_capital=100000,
            final_equity=150000,
            raw_statistics={}
        )

    # Test 1: Good strategy
    print("\nTest 1: Good Strategy")
    train = create_mock_metrics(1.5, 0.20, 0.12, 50, "Train")
    validate = create_mock_metrics(1.2, 0.15, 0.15, 45, "Validate")
    test = create_mock_metrics(1.0, 0.12, 0.18, 40, "Test")
    full = create_mock_metrics(1.2, 0.15, 0.15, 135, "Full")

    validator = StrategyValidator()
    result = validator.validate("test-good", "Good Strategy", full, train, validate, test)
    print(result.get_summary())

    # Test 2: Overfit strategy
    print("\nTest 2: Overfit Strategy")
    train2 = create_mock_metrics(2.5, 0.40, 0.10, 50, "Train")
    validate2 = create_mock_metrics(0.5, 0.05, 0.25, 45, "Validate")
    test2 = create_mock_metrics(0.2, 0.02, 0.30, 40, "Test")
    full2 = create_mock_metrics(1.0, 0.15, 0.20, 135, "Full")

    result2 = validator.validate("test-overfit", "Overfit Strategy", full2, train2, validate2, test2)
    print(result2.get_summary())

    # Test 3: Quick validation
    print("\nTest 3: Quick Validation")
    is_valid, notes = validator.quick_validate(full)
    print(f"Quick valid: {is_valid}, Notes: {notes}")
