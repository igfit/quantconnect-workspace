#!/usr/bin/env python3
"""
Strategy Factory Pipeline

Main orchestration script that runs backtesting, validation, and ranking
on strategy specs created by Claude Code.

IMPORTANT: This pipeline does NOT generate strategies.
Claude Code generates strategies through first-principles reasoning.
See GENERATE.md for the strategy generation protocol.

Usage:
    # Backtest all specs in the directory
    python run_pipeline.py

    # Backtest specific specs
    python run_pipeline.py --spec-ids abc123,def456

    # Use custom specs directory
    python run_pipeline.py --specs-dir /path/to/specs

    # Other options
    python run_pipeline.py --date-range 10_year --skip-sweep
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from models.strategy_spec import StrategySpec
from generators.ai_generator import StrategySpecManager, load_specs
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
        skip_sweep: bool = False,
        dry_run: bool = False,
        specs_dir: str = None,
        spec_ids: List[str] = None
    ):
        """
        Initialize the pipeline.

        Args:
            date_range: "5_year" or "10_year"
            skip_sweep: Skip parameter sweep phase
            dry_run: Load specs but don't run backtests
            specs_dir: Custom directory to load specs from
            spec_ids: Specific spec IDs to backtest (None = all)
        """
        self.date_range = date_range or config.ACTIVE_DATE_RANGE
        self.skip_sweep = skip_sweep
        self.dry_run = dry_run
        self.specs_dir = specs_dir or config.SPECS_DIR
        self.spec_ids = spec_ids

        # Update config
        config.ACTIVE_DATE_RANGE = self.date_range

        # Components
        self.spec_manager = StrategySpecManager(self.specs_dir)
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

    def phase1_load_specs(self) -> List[StrategySpec]:
        """
        Phase 1: Load strategy specs from files.

        Claude Code generates the specs through reasoning.
        This phase just loads them for backtesting.

        Returns:
            List of loaded StrategySpecs
        """
        print("\n" + "="*60)
        print("PHASE 1: LOAD STRATEGY SPECS")
        print("="*60)

        print(f"\nSpecs directory: {self.specs_dir}")

        if self.spec_ids:
            print(f"Loading specific specs: {self.spec_ids}")
            self.specs = self.spec_manager.load_by_ids(self.spec_ids)
        else:
            print("Loading all specs...")
            self.specs = self.spec_manager.load_all()

        if not self.specs:
            print("\nNo specs found!")
            print("\nClaude Code should generate strategies first.")
            print("See: strategy-factory/GENERATE.md for the protocol.")
            print("\nTo generate strategies, ask Claude Code:")
            print('  "Generate trading strategies"')
            return []

        print(f"\nLoaded {len(self.specs)} strategies:")
        for spec in self.specs:
            print(f"  - {spec.name} ({spec.id[:8]})")
            self._update_registry(spec, "loaded")

        self._save_registry()
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

        if not self.specs:
            print("\nNo specs to backtest. Run Phase 1 first.")
            return {}

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
            f"Strategies Loaded: {len(self.specs) if self.specs else 0}",
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
        print(f"Specs Directory: {self.specs_dir}")
        print(f"Spec IDs: {self.spec_ids or 'all'}")
        print(f"Skip Sweep: {self.skip_sweep}")
        print(f"Dry Run: {self.dry_run}")
        print("="*70)

        # Run phases
        self.phase1_load_specs()

        if not self.specs:
            print("\n" + "="*70)
            print("Pipeline stopped: No specs to process")
            print("="*70)
            return []

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
        self.registry["metadata"]["total_loaded"] = len(self.specs) if self.specs else 0
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
        description="Strategy Factory Pipeline - Backtest strategy specs created by Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
IMPORTANT: This pipeline does NOT generate strategies.
Claude Code generates strategies through first-principles reasoning.
See strategy-factory/GENERATE.md for the generation protocol.

Examples:
    # Backtest all specs in the default directory
    python run_pipeline.py

    # Backtest specific specs by ID
    python run_pipeline.py --spec-ids abc12345,def67890

    # Use a custom specs directory
    python run_pipeline.py --specs-dir /path/to/my/specs

    # Use 10-year backtest period
    python run_pipeline.py --date-range 10_year

    # Skip parameter sweep phase
    python run_pipeline.py --skip-sweep

    # Dry run (load specs but don't run backtests)
    python run_pipeline.py --dry-run

Workflow:
    1. Ask Claude Code to generate strategies (see GENERATE.md)
    2. Claude Code writes specs to strategy-factory/strategies/specs/
    3. Run this pipeline to backtest, validate, and rank
    4. Review results with Claude Code
    5. Iterate
        """
    )

    parser.add_argument(
        "--specs-dir",
        type=str,
        default=None,
        help="Directory containing strategy specs (default: strategy-factory/strategies/specs/)"
    )

    parser.add_argument(
        "--spec-ids",
        type=str,
        default=None,
        help="Comma-separated list of specific spec IDs to backtest (default: all)"
    )

    parser.add_argument(
        "--date-range",
        choices=["5_year", "10_year"],
        default="5_year",
        help="Backtest date range (default: 5_year)"
    )

    parser.add_argument(
        "--skip-sweep",
        action="store_true",
        help="Skip parameter sweep phase"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load specs but don't run backtests"
    )

    args = parser.parse_args()

    # Parse spec IDs
    spec_ids = None
    if args.spec_ids:
        spec_ids = [s.strip() for s in args.spec_ids.split(",")]

    # Run pipeline
    pipeline = Pipeline(
        date_range=args.date_range,
        skip_sweep=args.skip_sweep,
        dry_run=args.dry_run,
        specs_dir=args.specs_dir,
        spec_ids=spec_ids
    )

    pipeline.run()


if __name__ == "__main__":
    main()
