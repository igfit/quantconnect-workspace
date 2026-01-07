"""
Strategy Ranker

Scores and ranks strategies based on multiple metrics with configurable weights.
"""

import os
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.parser import ParsedMetrics
from core.validator import ValidationResult
import config


@dataclass
class RankedStrategy:
    """A strategy with its ranking information"""
    strategy_id: str
    name: str
    metrics: ParsedMetrics
    validation: Optional[ValidationResult]

    # Scores
    raw_score: float  # Before penalties
    final_score: float  # After penalties
    rank: int

    # Score breakdown
    score_breakdown: Dict[str, float]
    penalties: List[str]

    def get_summary(self) -> str:
        """Get human-readable summary"""
        return (
            f"#{self.rank}: {self.name} (Score: {self.final_score:.3f})\n"
            f"  Sharpe: {self.metrics.sharpe_ratio:.2f}, "
            f"CAGR: {self.metrics.cagr*100:.1f}%, "
            f"MaxDD: {self.metrics.max_drawdown*100:.1f}%\n"
            f"  Trades: {self.metrics.total_trades}, "
            f"Win Rate: {self.metrics.win_rate*100:.1f}%\n"
            f"  Penalties: {', '.join(self.penalties) if self.penalties else 'None'}"
        )


class StrategyRanker:
    """
    Rank strategies using weighted scoring.

    Scoring formula:
    score = (w1 * sharpe_score) + (w2 * cagr_score) + (w3 * drawdown_score) +
            (w4 * profit_factor_score) + (w5 * win_rate_score)

    Then apply penalties for:
    - High turnover
    - Low trade count
    - Single-regime success
    """

    def __init__(
        self,
        weights: Dict[str, float] = None,
        score_ranges: Dict[str, Tuple[float, float]] = None
    ):
        """
        Args:
            weights: Scoring weights (default from config)
            score_ranges: Normalization ranges (default from config)
        """
        self.weights = weights or config.SCORING_WEIGHTS
        self.score_ranges = score_ranges or config.SCORE_RANGES

    def normalize(self, value: float, metric_name: str) -> float:
        """
        Normalize a metric value to 0-1 range.

        Args:
            value: Raw metric value
            metric_name: Name of the metric for range lookup

        Returns:
            Normalized value between 0 and 1
        """
        if metric_name not in self.score_ranges:
            return min(max(value, 0), 1)

        min_val, max_val = self.score_ranges[metric_name]

        # For drawdown, invert (lower is better)
        if metric_name == "max_drawdown":
            value = max_val - value

        # Normalize
        if max_val == min_val:
            return 0.5

        normalized = (value - min_val) / (max_val - min_val)
        return min(max(normalized, 0), 1)

    def calculate_raw_score(self, metrics: ParsedMetrics) -> Tuple[float, Dict[str, float]]:
        """
        Calculate raw score before penalties.

        Returns:
            (raw_score, score_breakdown)
        """
        breakdown = {}

        # Sharpe ratio
        sharpe_norm = self.normalize(metrics.sharpe_ratio, "sharpe_ratio")
        breakdown["sharpe"] = sharpe_norm * self.weights["sharpe_ratio"]

        # CAGR
        cagr_norm = self.normalize(metrics.cagr, "cagr")
        breakdown["cagr"] = cagr_norm * self.weights["cagr"]

        # Max drawdown (inverted - lower is better)
        dd_norm = self.normalize(metrics.max_drawdown, "max_drawdown")
        breakdown["max_drawdown"] = dd_norm * self.weights["max_drawdown"]

        # Profit factor
        pf_norm = self.normalize(metrics.profit_factor, "profit_factor")
        breakdown["profit_factor"] = pf_norm * self.weights["profit_factor"]

        # Win rate
        wr_norm = self.normalize(metrics.win_rate, "win_rate")
        breakdown["win_rate"] = wr_norm * self.weights["win_rate"]

        raw_score = sum(breakdown.values())
        return raw_score, breakdown

    def apply_penalties(
        self,
        raw_score: float,
        metrics: ParsedMetrics,
        validation: ValidationResult = None
    ) -> Tuple[float, List[str]]:
        """
        Apply penalties to raw score.

        Returns:
            (final_score, list of penalty descriptions)
        """
        score = raw_score
        penalties = []

        # Penalty for high turnover (>50 trades/year for 4-5 year period)
        # Estimate years from typical backtest period
        years = 4.5  # Approximate
        trades_per_year = metrics.total_trades / years
        if trades_per_year > 50:
            score *= config.PENALTY_HIGH_TURNOVER
            penalties.append(f"High turnover ({trades_per_year:.0f}/year)")

        # Penalty for low trade count
        if metrics.total_trades < config.MIN_TRADE_COUNT:
            score *= config.PENALTY_LOW_TRADE_COUNT
            penalties.append(f"Low trade count ({metrics.total_trades})")

        # Penalty for single-regime success
        if validation:
            if not validation.passes_walk_forward:
                score *= config.PENALTY_SINGLE_REGIME
                penalties.append("Failed walk-forward")
            elif validation.consistency_score < 0.5:
                score *= 0.85
                penalties.append(f"Low consistency ({validation.consistency_score:.2f})")

        # Penalty for very high beta (market-dependent)
        if metrics.beta > 1.3:
            score *= 0.9
            penalties.append(f"High beta ({metrics.beta:.2f})")

        # Bonus for positive alpha (capped)
        if metrics.alpha > 0.05:
            score *= min(1.1, 1 + metrics.alpha)

        return score, penalties

    def rank_strategy(
        self,
        strategy_id: str,
        name: str,
        metrics: ParsedMetrics,
        validation: ValidationResult = None
    ) -> RankedStrategy:
        """
        Calculate score for a single strategy.

        Args:
            strategy_id: Strategy identifier
            name: Strategy name
            metrics: Parsed backtest metrics
            validation: Optional validation result

        Returns:
            RankedStrategy object (rank will be 0 until sorted)
        """
        raw_score, breakdown = self.calculate_raw_score(metrics)
        final_score, penalties = self.apply_penalties(raw_score, metrics, validation)

        return RankedStrategy(
            strategy_id=strategy_id,
            name=name,
            metrics=metrics,
            validation=validation,
            raw_score=raw_score,
            final_score=final_score,
            rank=0,
            score_breakdown=breakdown,
            penalties=penalties
        )

    def rank_strategies(
        self,
        strategies: List[Tuple[str, str, ParsedMetrics, Optional[ValidationResult]]]
    ) -> List[RankedStrategy]:
        """
        Rank multiple strategies.

        Args:
            strategies: List of (strategy_id, name, metrics, validation) tuples

        Returns:
            List of RankedStrategy sorted by final_score descending
        """
        ranked = []

        for strategy_id, name, metrics, validation in strategies:
            ranked_strategy = self.rank_strategy(strategy_id, name, metrics, validation)
            ranked.append(ranked_strategy)

        # Sort by final score descending
        ranked.sort(key=lambda x: x.final_score, reverse=True)

        # Assign ranks
        for i, strategy in enumerate(ranked):
            strategy.rank = i + 1

        return ranked

    def get_top_n(
        self,
        ranked_strategies: List[RankedStrategy],
        n: int = 5
    ) -> List[RankedStrategy]:
        """Get top N strategies"""
        return ranked_strategies[:n]

    def generate_report(self, ranked_strategies: List[RankedStrategy]) -> str:
        """Generate a text report of rankings"""
        lines = [
            "=" * 70,
            "STRATEGY RANKING REPORT",
            "=" * 70,
            ""
        ]

        for strategy in ranked_strategies:
            lines.append(strategy.get_summary())
            lines.append("-" * 40)

        lines.append(f"\nTotal strategies ranked: {len(ranked_strategies)}")

        # Add score distribution
        if ranked_strategies:
            scores = [s.final_score for s in ranked_strategies]
            lines.append(f"Score range: {min(scores):.3f} - {max(scores):.3f}")
            lines.append(f"Top score: {ranked_strategies[0].final_score:.3f}")

        return "\n".join(lines)


def rank_strategies(
    strategies: List[Tuple[str, str, ParsedMetrics, Optional[ValidationResult]]]
) -> List[RankedStrategy]:
    """Convenience function to rank strategies"""
    ranker = StrategyRanker()
    return ranker.rank_strategies(strategies)


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    from core.parser import ParsedMetrics

    print("="*60)
    print("Strategy Ranker Test")
    print("="*60)

    # Create mock metrics
    def create_mock(name, sharpe, cagr, max_dd, trades, pf, wr, alpha, beta):
        return ParsedMetrics(
            strategy_id=name.lower().replace(" ", "_"),
            backtest_id="test",
            name=name,
            total_return=cagr * 4,
            cagr=cagr,
            sharpe_ratio=sharpe,
            sortino_ratio=sharpe * 1.2,
            max_drawdown=max_dd,
            volatility=0.20,
            total_trades=trades,
            win_rate=wr,
            profit_factor=pf,
            avg_win=250,
            avg_loss=150,
            alpha=alpha,
            beta=beta,
            information_ratio=0.5,
            treynor_ratio=0.1,
            start_date="2020-01-01",
            end_date="2024-12-31",
            initial_capital=100000,
            final_equity=100000 * (1 + cagr * 4),
            raw_statistics={}
        )

    # Create test strategies
    strategies = [
        ("s1", "High Sharpe Momentum",
         create_mock("High Sharpe Momentum", 1.8, 0.25, 0.12, 80, 2.0, 0.58, 0.08, 0.9), None),
        ("s2", "Steady Growth",
         create_mock("Steady Growth", 1.2, 0.15, 0.10, 60, 1.5, 0.55, 0.05, 0.7), None),
        ("s3", "High Risk High Return",
         create_mock("High Risk High Return", 1.0, 0.35, 0.30, 120, 1.8, 0.52, 0.02, 1.4), None),
        ("s4", "Low Trade Count",
         create_mock("Low Trade Count", 1.5, 0.20, 0.08, 20, 2.2, 0.60, 0.06, 0.8), None),
        ("s5", "Market Follower",
         create_mock("Market Follower", 0.9, 0.12, 0.18, 45, 1.3, 0.48, -0.02, 1.0), None),
    ]

    # Rank
    ranker = StrategyRanker()
    ranked = ranker.rank_strategies(strategies)

    # Print report
    print(ranker.generate_report(ranked))

    # Show top 3
    print("\n" + "="*60)
    print("TOP 3 STRATEGIES FOR PAPER TRADING")
    print("="*60)
    for s in ranker.get_top_n(ranked, 3):
        print(f"\n{s.get_summary()}")
