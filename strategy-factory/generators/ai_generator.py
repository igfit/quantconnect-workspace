"""
AI Strategy Generator - Helper Module

DEPRECATED: Template generation removed.

Claude Code now generates strategies through first-principles reasoning,
not hardcoded templates. See GENERATE.md for the strategy generation protocol.

This module provides utility functions for:
- Loading strategy specs from files
- Saving strategy specs to files
- Managing the spec directory

Strategy generation is now handled by Claude Code reasoning, documented in:
- PRD.md: Product requirements and vision
- GENERATE.md: Meta-reasoning protocol for Claude Code
- PLAN.md: Technical implementation details
"""

import os
import json
from typing import List, Optional
from glob import glob

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.strategy_spec import StrategySpec
import config


class StrategySpecManager:
    """
    Manages strategy specification files.

    Handles loading, saving, and listing strategy specs.
    Actual strategy generation is done by Claude Code through reasoning.
    """

    def __init__(self, specs_dir: str = None):
        """
        Initialize the spec manager.

        Args:
            specs_dir: Directory containing spec files (default: config.SPECS_DIR)
        """
        self.specs_dir = specs_dir or config.SPECS_DIR

    def load_all(self) -> List[StrategySpec]:
        """
        Load all strategy specs from the specs directory.

        Returns:
            List of StrategySpec objects
        """
        specs = []
        pattern = os.path.join(self.specs_dir, "*.json")

        for filepath in glob(pattern):
            try:
                spec = StrategySpec.load(filepath)
                specs.append(spec)
            except Exception as e:
                print(f"WARNING: Failed to load {filepath}: {e}")

        return specs

    def load_by_ids(self, spec_ids: List[str]) -> List[StrategySpec]:
        """
        Load specific strategy specs by their IDs.

        Args:
            spec_ids: List of strategy IDs to load

        Returns:
            List of StrategySpec objects
        """
        specs = []

        for spec_id in spec_ids:
            filepath = os.path.join(self.specs_dir, f"{spec_id}.json")

            if os.path.exists(filepath):
                try:
                    spec = StrategySpec.load(filepath)
                    specs.append(spec)
                except Exception as e:
                    print(f"WARNING: Failed to load {spec_id}: {e}")
            else:
                print(f"WARNING: Spec not found: {spec_id}")

        return specs

    def save(self, spec: StrategySpec) -> str:
        """
        Save a strategy spec to file.

        Args:
            spec: StrategySpec to save

        Returns:
            Filepath where spec was saved
        """
        os.makedirs(self.specs_dir, exist_ok=True)
        filepath = os.path.join(self.specs_dir, f"{spec.id}.json")
        spec.save(filepath)
        return filepath

    def save_all(self, specs: List[StrategySpec]) -> List[str]:
        """
        Save multiple strategy specs to files.

        Args:
            specs: List of StrategySpecs to save

        Returns:
            List of filepaths
        """
        return [self.save(spec) for spec in specs]

    def list_ids(self) -> List[str]:
        """
        List all strategy IDs in the specs directory.

        Returns:
            List of strategy IDs
        """
        pattern = os.path.join(self.specs_dir, "*.json")
        return [
            os.path.basename(f).replace(".json", "")
            for f in glob(pattern)
        ]

    def count(self) -> int:
        """Count total specs in directory."""
        return len(self.list_ids())

    def delete(self, spec_id: str) -> bool:
        """
        Delete a strategy spec file.

        Args:
            spec_id: ID of spec to delete

        Returns:
            True if deleted, False if not found
        """
        filepath = os.path.join(self.specs_dir, f"{spec_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False


# =============================================================================
# DEPRECATED: AIStrategyGenerator
# =============================================================================

class AIStrategyGenerator:
    """
    DEPRECATED: Strategy template generation has been removed.

    Claude Code now generates strategies through first-principles reasoning.
    See GENERATE.md for the meta-reasoning protocol.

    This class now only provides backward-compatible methods for loading
    specs from files.
    """

    def __init__(self, specs_dir: str = None):
        """Initialize with optional custom specs directory."""
        self.manager = StrategySpecManager(specs_dir)
        self.generated_count = 0

    def generate_all(self, batch_size: int = None) -> List[StrategySpec]:
        """
        DEPRECATED: No longer generates strategies.

        Now loads existing specs from files.
        Claude Code should generate specs through reasoning, not this method.

        Args:
            batch_size: Max specs to return (None = all)

        Returns:
            List of StrategySpec objects loaded from files
        """
        print("\n" + "="*60)
        print("NOTE: Template generation has been removed.")
        print("Loading existing specs from files instead.")
        print("Claude Code should generate strategies through reasoning.")
        print("See: strategy-factory/GENERATE.md")
        print("="*60 + "\n")

        specs = self.manager.load_all()

        if batch_size is not None and len(specs) > batch_size:
            specs = specs[:batch_size]

        self.generated_count = len(specs)
        return specs

    def save_strategies(self, strategies: List[StrategySpec]) -> List[str]:
        """Save strategies to spec files."""
        return self.manager.save_all(strategies)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def load_specs(specs_dir: str = None, spec_ids: List[str] = None) -> List[StrategySpec]:
    """
    Load strategy specs from files.

    Args:
        specs_dir: Directory containing specs (default: config.SPECS_DIR)
        spec_ids: Optional list of specific IDs to load (None = all)

    Returns:
        List of StrategySpec objects
    """
    manager = StrategySpecManager(specs_dir)

    if spec_ids:
        return manager.load_by_ids(spec_ids)
    else:
        return manager.load_all()


def save_spec(spec: StrategySpec, specs_dir: str = None) -> str:
    """
    Save a strategy spec to file.

    Args:
        spec: StrategySpec to save
        specs_dir: Directory to save to (default: config.SPECS_DIR)

    Returns:
        Filepath where spec was saved
    """
    manager = StrategySpecManager(specs_dir)
    return manager.save(spec)


# =============================================================================
# CLI / TESTING
# =============================================================================

if __name__ == "__main__":
    print("="*60)
    print("Strategy Spec Manager")
    print("="*60)

    manager = StrategySpecManager()

    print(f"\nSpecs directory: {manager.specs_dir}")
    print(f"Total specs: {manager.count()}")

    if manager.count() > 0:
        print("\nExisting specs:")
        for spec_id in manager.list_ids():
            print(f"  - {spec_id}")

        print("\nLoading all specs...")
        specs = manager.load_all()
        for spec in specs:
            print(f"\n  {spec.name}")
            print(f"    ID: {spec.id}")
            print(f"    Universe: {spec.universe.symbols[:3]}...")
            print(f"    Indicators: {[i.type for i in spec.indicators]}")
    else:
        print("\nNo specs found.")
        print("Claude Code should generate strategies through reasoning.")
        print("See: strategy-factory/GENERATE.md")
