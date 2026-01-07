#!/usr/bin/env python3
"""
Strategy Factory Pipeline

Main orchestration script that runs the full strategy generation,
backtesting, validation, and ranking pipeline.

Usage:
    python run_pipeline.py --help
    python run_pipeline.py --date-range 5_year --batch-size 15
    python run_pipeline.py --skip-sweep --dry-run
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from models.strategy_spec import StrategySpec
from generators.ai_generator import AIStrategyGenerator
from generators.param_sweeper import ParameterSweeper
from core.compiler import StrategyCompiler, save_compiled_strategy
from core.runner import QCRunner, BacktestResult
from core.parser import ResultsParser, ParsedMetrics
from core.validator import StrategyValidator, ValidationResult
from core.ranker import StrategyRanker, RankedStrategy


class Pipeline:
    """Main pipeline orchestrator"""

    def __init__(
        self,
        date_range: str = None,
        batch_size: int = None,
        skip_sweep: bool = False,
        dry_run: bool = False
    ):
        """
        Initialize the pipeline.

        Args:
            date_range: "5_year" or "10_year"
            batch_size: Max strategies to generate
            skip_sweep: Skip parameter sweep phase
            dry_run: Generate but don't run backtests
        """
        self.date_range = date_range or config.ACTIVE_DATE_RANGE
        self.batch_size = batch_size or config.DEFAULT_BATCH_SIZE
        self.skip_sweep = skip_sweep
        self.dry_run = dry_run

        # Update config
        config.ACTIVE_DATE_RANGE = self.date_range

        # Components
        self.generator = AIStrategyGenerator()
        self.sweeper = ParameterSweeper()
        self.compiler = StrategyCompiler()
        self.parser = ResultsParser()
        self.validator = StrategyValidator(self.date_range)
        self.ranker = StrategyRanker()
        self.runner = None  # Initialized lazily

        # Results storage
        self.specs: List[StrategySpec] = []
        self.backtest_results: Dict[str, BacktestResult] = {}
        self.parsed_metrics: Dict[str, ParsedMetrics] = {}
        self.validation_results: Dict[str, ValidationResult] = {}
        self.ranked_strategies: List[RankedStrategy] = []

        # Registry
        self.registry = self._load_registry()

    def _load_registry(self) -> Dict[str, Any]:
        """Load the strategy registry"""
        if os.path.exists(config.REGISTRY_PATH):
            with open(config.REGISTRY_PATH, 'r') as f:
                return json.load(f)
        return {"strategies": [], "metadata": {}}

    def _save_registry(self):
        """Save the strategy registry"""
        self.registry["updated_at"] = datetime.utcnow().isoformat()
        os.makedirs(os.path.dirname(config.REGISTRY_PATH), exist_ok=True)
        with open(config.REGISTRY_PATH, 'w') as f:
            json.dump(self.registry, f, indent=2)

    def _update_registry(self, spec: StrategySpec, status: str, metrics: ParsedMetrics = None):
        """Update registry with strategy info"""
        entry = {
            "id": spec.id,
            "name": spec.name,
            "created_at": spec.created_at,
            "status": status,
            "parent_id": spec.parent_id,
        }
        if metrics:
            entry["sharpe_ratio"] = metrics.sharpe_ratio
            entry["cagr"] = metrics.cagr
            entry["max_drawdown"] = metrics.max_drawdown

        # Check if exists
        existing = next((s for s in self.registry["strategies"] if s["id"] == spec.id), None)
        if existing:
            existing.update(entry)
        else:
            self.registry["strategies"].append(entry)

    def _get_runner(self) -> QCRunner:
        """Get or create QC runner with sandbox project"""
        if self.runner is None:
            self.runner = QCRunner()
            if not self.dry_run:
                self.runner.get_or_create_sandbox_project()
        return self.runner

    def phase1_generate(self) -> List[StrategySpec]:
        """
        Phase 1: Generate strategies using AI.

        Returns:
            List of generated StrategySpecs
        """
        print("\n" + "="*60)
        print("PHASE 1: STRATEGY GENERATION")
        print("="*60)

        self.specs = self.generator.generate_all(self.batch_size)
        print(f"\nGenerated {len(self.specs)} strategies")

        # Save specs
        for spec in self.specs:
            filepath = os.path.join(config.SPECS_DIR, f"{spec.id}.json")
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            spec.save(filepath)
            self._update_registry(spec, "generated")

        self._save_registry()
        print(f"Saved specs to {config.SPECS_DIR}")

        return self.specs

    def phase2_initial_backtest(self) -> Dict[str, ParsedMetrics]:
        """
        Phase 2: Run initial backtests on all strategies.

        Returns:
            Dict mapping strategy_id to ParsedMetrics
        """
        print("\n" + "="*60)
        print("PHASE 2: INITIAL BACKTESTS")
        print("="*60)

        dates = config.DATE_RANGES[self.date_range]["full"]
        print(f"Period: {dates[0]} to {dates[1]}")

        if self.dry_run:
            print("\n[DRY RUN] Skipping actual backtests")
            return {}

        runner = self._get_runner()

        for i, spec in enumerate(self.specs, 1):
            print(f"\n[{i}/{len(self.specs)}] Backtesting: {spec.name}")

            try:
                # Compile
                code = self.compiler.compile(spec, dates[0], dates[1])
                save_compiled_strategy(spec, code)

                # Run backtest
                result = runner.run_full_backtest(
                    code=code,
                    strategy_id=spec.id,
                    backtest_name=f"{spec.id}_{datetime.now().strftime('%Y%m%d_%H%M')}"
                )

                self.backtest_results[spec.id] = result

                if result.success:
                    # Parse metrics
                    metrics = self.parser.parse(
                        result.raw_response,
                        spec.id,
                        result.backtest_id,
                        spec.name
                    )
                    self.parsed_metrics[spec.id] = metrics
                    self.parser.save_metrics(metrics, spec.id)
                    self._update_registry(spec, "backtested", metrics)

                    print(f"   {metrics.get_summary()}")
                else:
                    print(f"   FAILED: {result.error}")
                    self._update_registry(spec, "failed")

            except Exception as e:
                print(f"   ERROR: {e}")
                self._update_registry(spec, "error")

        self._save_registry()
        return self.parsed_metrics

    def phase3_filter(self) -> List[StrategySpec]:
        """
        Phase 3: Filter to strategies meeting thresholds.

        Returns:
            List of passing StrategySpecs
        """
        print("\n" + "="*60)
        print("PHASE 3: FILTERING")
        print("="*60)

        passing = []
        for spec in self.specs:
            if spec.id not in self.parsed_metrics:
                continue

            metrics = self.parsed_metrics[spec.id]

            if metrics.passes_thresholds() and not metrics.is_disqualified():
                passing.append(spec)
                print(f"  PASS: {spec.name} (Sharpe: {metrics.sharpe_ratio:.2f})")
            else:
                print(f"  FAIL: {spec.name}")

        print(f"\n{len(passing)} strategies passed filtering")

        self.specs = passing
        return passing

    def phase4_parameter_sweep(self) -> List[StrategySpec]:
        """
        Phase 4: Parameter sweep on passing strategies.

        Returns:
            List of all strategy variations
        """
        if self.skip_sweep:
            print("\n[SKIPPED] Phase 4: Parameter Sweep")
            return self.specs

        print("\n" + "="*60)
        print("PHASE 4: PARAMETER SWEEP")
        print("="*60)

        all_variations = []

        for spec in self.specs:
            if not spec.parameters:
                all_variations.append(spec)
                continue

            print(f"\nSweeping: {spec.name}")
            variations = self.sweeper.sweep(spec)
            print(f"  Generated {len(variations)} variations")
            all_variations.extend(variations)

        print(f"\nTotal variations: {len(all_variations)}")

        # Backtest variations
        if not self.dry_run and all_variations:
            print("\nBacktesting variations...")
            dates = config.DATE_RANGES[self.date_range]["full"]
            runner = self._get_runner()

            for i, var in enumerate(all_variations, 1):
                if var.id in self.parsed_metrics:
                    continue  # Already tested

                print(f"\n[{i}/{len(all_variations)}] {var.name[:50]}...")

                try:
                    code = self.compiler.compile(var, dates[0], dates[1])
                    result = runner.run_full_backtest(
                        code=code,
                        strategy_id=var.id,
                        backtest_name=f"{var.id}_{datetime.now().strftime('%H%M%S')}"
                    )

                    if result.success:
                        metrics = self.parser.parse(
                            result.raw_response,
                            var.id,
                            result.backtest_id,
                            var.name
                        )
                        self.parsed_metrics[var.id] = metrics
                        print(f"   Sharpe: {metrics.sharpe_ratio:.2f}, CAGR: {metrics.cagr*100:.1f}%")
                    else:
                        print(f"   FAILED")

                except Exception as e:
                    print(f"   ERROR: {e}")

        self.specs = all_variations
        return all_variations

    def phase5_validate(self) -> Dict[str, ValidationResult]:
        """
        Phase 5: Validate strategies.

        Returns:
            Dict mapping strategy_id to ValidationResult
        """
        print("\n" + "="*60)
        print("PHASE 5: VALIDATION")
        print("="*60)

        for spec in self.specs:
            if spec.id not in self.parsed_metrics:
                continue

            metrics = self.parsed_metrics[spec.id]

            # Quick validation (full walk-forward would require additional backtests)
            is_valid, notes = self.validator.quick_validate(metrics)

            result = self.validator.validate(
                spec.id,
                spec.name,
                metrics
            )

            self.validation_results[spec.id] = result

            status = "VALID" if result.is_valid else "INVALID"
            print(f"  {status}: {spec.name[:40]}... (score: {result.consistency_score:.2f})")

        valid_count = sum(1 for v in self.validation_results.values() if v.is_valid)
        print(f"\n{valid_count} strategies validated")

        return self.validation_results

    def phase6_rank(self) -> List[RankedStrategy]:
        """
        Phase 6: Rank strategies.

        Returns:
            List of RankedStrategy sorted by score
        """
        print("\n" + "="*60)
        print("PHASE 6: RANKING")
        print("="*60)

        # Prepare data for ranking
        strategies_to_rank = []

        for spec in self.specs:
            if spec.id not in self.parsed_metrics:
                continue

            metrics = self.parsed_metrics[spec.id]
            validation = self.validation_results.get(spec.id)

            # Only rank valid strategies
            if validation and not validation.is_valid:
                continue

            strategies_to_rank.append((spec.id, spec.name, metrics, validation))

        # Rank
        self.ranked_strategies = self.ranker.rank_strategies(strategies_to_rank)

        # Print rankings
        print(self.ranker.generate_report(self.ranked_strategies))

        return self.ranked_strategies

    def phase7_report(self, top_n: int = 5) -> str:
        """
        Phase 7: Generate final report.

        Args:
            top_n: Number of top strategies to highlight

        Returns:
            Report string
        """
        print("\n" + "="*60)
        print("PHASE 7: FINAL REPORT")
        print("="*60)

        lines = [
            "="*70,
            "STRATEGY FACTORY - PIPELINE RESULTS",
            f"Generated: {datetime.now().isoformat()}",
            f"Date Range: {self.date_range}",
            "="*70,
            "",
            f"Strategies Generated: {self.generator.generated_count if hasattr(self.generator, 'generated_count') else 'N/A'}",
            f"Backtests Completed: {len(self.parsed_metrics)}",
            f"Strategies Validated: {sum(1 for v in self.validation_results.values() if v.is_valid)}",
            f"Final Ranked: {len(self.ranked_strategies)}",
            "",
            "="*70,
            f"TOP {top_n} STRATEGIES FOR PAPER TRADING",
            "="*70,
        ]

        top_strategies = self.ranker.get_top_n(self.ranked_strategies, top_n)

        for strategy in top_strategies:
            lines.append("")
            lines.append(strategy.get_summary())
            lines.append("")

            # Add strategy details
            spec = next((s for s in self.specs if s.id == strategy.strategy_id), None)
            if spec:
                lines.append(f"  Rationale: {spec.rationale[:100]}...")
                lines.append(f"  Universe: {spec.universe.symbols[:5]}...")
                lines.append(f"  Indicators: {[i.type for i in spec.indicators]}")
            lines.append("-"*40)

        lines.extend([
            "",
            "="*70,
            "NEXT STEPS",
            "="*70,
            "1. Review top strategies and their rationales",
            "2. Set up paper trading on QuantConnect",
            "3. Monitor for 1-3 months before live deployment",
            "4. Document any live vs backtest discrepancies",
            "",
        ])

        report = "\n".join(lines)

        # Save report
        report_path = os.path.join(config.RESULTS_DIR, f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, 'w') as f:
            f.write(report)

        print(report)
        print(f"\nReport saved to: {report_path}")

        return report

    def run(self) -> List[RankedStrategy]:
        """
        Run the complete pipeline.

        Returns:
            List of top ranked strategies
        """
        start_time = datetime.now()

        print("\n" + "="*70)
        print("STRATEGY FACTORY PIPELINE")
        print(f"Started: {start_time.isoformat()}")
        print(f"Date Range: {self.date_range}")
        print(f"Batch Size: {self.batch_size}")
        print(f"Skip Sweep: {self.skip_sweep}")
        print(f"Dry Run: {self.dry_run}")
        print("="*70)

        # Run phases
        self.phase1_generate()
        self.phase2_initial_backtest()
        self.phase3_filter()
        self.phase4_parameter_sweep()
        self.phase5_validate()
        self.phase6_rank()
        self.phase7_report()

        # Save final metrics summary
        if self.parsed_metrics:
            self.parser.save_summary_csv(list(self.parsed_metrics.values()))

        # Update registry metadata
        self.registry["metadata"]["last_pipeline_run"] = datetime.utcnow().isoformat()
        self.registry["metadata"]["total_generated"] = len(self.specs)
        self.registry["metadata"]["total_backtested"] = len(self.parsed_metrics)
        self._save_registry()

        end_time = datetime.now()
        duration = end_time - start_time

        print(f"\n{'='*70}")
        print(f"Pipeline completed in {duration}")
        print(f"{'='*70}")

        return self.ranked_strategies


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Strategy Factory Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_pipeline.py                          # Run with defaults
    python run_pipeline.py --date-range 10_year     # Use 10-year backtest period
    python run_pipeline.py --batch-size 5 --dry-run # Generate 5 strategies, no backtests
    python run_pipeline.py --skip-sweep             # Skip parameter optimization
        """
    )

    parser.add_argument(
        "--date-range",
        choices=["5_year", "10_year"],
        default="5_year",
        help="Backtest date range (default: 5_year)"
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=15,
        help="Number of strategies to generate (default: 15)"
    )

    parser.add_argument(
        "--skip-sweep",
        action="store_true",
        help="Skip parameter sweep phase"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate strategies but don't run backtests"
    )

    args = parser.parse_args()

    # Run pipeline
    pipeline = Pipeline(
        date_range=args.date_range,
        batch_size=args.batch_size,
        skip_sweep=args.skip_sweep,
        dry_run=args.dry_run
    )

    pipeline.run()


if __name__ == "__main__":
    main()
