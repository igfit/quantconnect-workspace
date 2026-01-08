#!/usr/bin/env python3
"""
Simple runner for Claude Universe Generator

Usage:
    # Set API key
    export ANTHROPIC_API_KEY="your-key"

    # Generate universe
    python run_generator.py

    # Or pass key directly
    python run_generator.py --api-key "your-key"

    # Generate for different date
    python run_generator.py --date 2019-01-01

    # Just extract features (no universe generation)
    python run_generator.py --features-only
"""

import os
import sys
import json
import argparse

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from claude_universe_generator import (
    ClaudeUniverseGenerator,
    UniverseType,
    generate_momentum_universe,
    analyze_momentum_features,
)
from momentum_features import (
    get_selection_rules,
    get_anti_patterns,
    get_feature_criteria_prompt,
    score_stock_features,
)


def main():
    parser = argparse.ArgumentParser(description="Generate stock universe using Claude")
    parser.add_argument("--api-key", help="Anthropic API key")
    parser.add_argument("--date", default="2020-01-01", help="Selection date (YYYY-MM-DD)")
    parser.add_argument("--num-stocks", type=int, default=60, help="Target number of stocks")
    parser.add_argument("--features-only", action="store_true", help="Only show feature criteria")
    parser.add_argument("--extract-features", action="store_true", help="Extract features using Claude")
    parser.add_argument("--output-dir", default="strategy-factory/universe/generated")

    args = parser.parse_args()

    # Show features only mode
    if args.features_only:
        print("=" * 60)
        print("MOMENTUM STOCK SELECTION CRITERIA")
        print("=" * 60)
        print("\n".join(get_selection_rules()))
        print("\n=== Anti-Patterns ===")
        for p in get_anti_patterns():
            print(f"  - {p}")
        print("\n=== Claude Prompt Criteria ===")
        print(get_feature_criteria_prompt())
        return 0

    # Get API key
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: No API key provided.")
        print("Either set ANTHROPIC_API_KEY environment variable or use --api-key")
        print("\nExample:")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        print("  python run_generator.py")
        return 1

    # Extract features mode
    if args.extract_features:
        print("=" * 60)
        print("EXTRACTING MOMENTUM FEATURES USING CLAUDE")
        print("=" * 60)

        features = analyze_momentum_features(api_key=api_key)
        print("\nExtracted Features:")
        print(json.dumps(features, indent=2))

        # Save features
        output_path = os.path.join(args.output_dir, "extracted_features.json")
        os.makedirs(args.output_dir, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(features, f, indent=2)
        print(f"\nSaved to: {output_path}")
        return 0

    # Generate universe
    print("=" * 60)
    print(f"GENERATING MOMENTUM UNIVERSE AS OF {args.date}")
    print("=" * 60)
    print("\nUsing Claude to generate and validate stock picks...")
    print("This may take 30-60 seconds.\n")

    try:
        generator = ClaudeUniverseGenerator(api_key=api_key)

        universe = generator.generate_and_validate(
            selection_date=args.date,
            universe_type=UniverseType.HIGH_BETA_MOMENTUM,
            num_stocks=args.num_stocks,
        )

        # Save results
        os.makedirs(args.output_dir, exist_ok=True)
        filepath = universe.save(args.output_dir)

        # Print results
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        print(f"\nUniverse: {universe.name}")
        print(f"Selection Date: {universe.selection_date}")
        print(f"\nFinal Symbols ({len(universe.final_symbols)}):")
        print(", ".join(universe.final_symbols))

        if universe.excluded_symbols:
            print(f"\n❌ Excluded ({len(universe.excluded_symbols)}):")
            for sym, reason in universe.excluded_symbols.items():
                print(f"  - {sym}: {reason}")

        if universe.hindsight_flags:
            print(f"\n⚠️  Hindsight Flags ({len(universe.hindsight_flags)}):")
            for sym, flag in universe.hindsight_flags.items():
                print(f"  - {sym}: {flag}")

        print(f"\n✅ Saved to: {filepath}")

        # Generate Python list for easy copy-paste
        print("\n" + "=" * 60)
        print("COPY-PASTE UNIVERSE")
        print("=" * 60)
        symbols_str = '", "'.join(universe.final_symbols)
        print(f'\nuniverse = ["{symbols_str}"]')

        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
