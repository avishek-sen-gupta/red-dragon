"""Allow running viz as a module: poetry run python -m viz <source_file>

Single file:
  poetry run python -m viz demo.c -l c

Compare mode:
  poetry run python -m viz compare c:demo.c rust:demo.rs
"""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> None:
    # Detect compare mode by checking if first arg is "compare"
    if len(sys.argv) > 1 and sys.argv[1] == "compare":
        _main_compare()
    else:
        _main_single()


def _main_single() -> None:
    parser = argparse.ArgumentParser(
        description="RedDragon Pipeline Visualizer — interactive TUI"
    )
    parser.add_argument("source_file", help="Path to source file to visualize")
    parser.add_argument(
        "-l", "--language", default="python", help="Source language (default: python)"
    )
    parser.add_argument(
        "-s",
        "--max-steps",
        type=int,
        default=300,
        help="Maximum execution steps (default: 300)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    from viz.app import PipelineApp
    from viz.pipeline import run_pipeline

    with open(args.source_file) as f:
        source = f.read()

    result = run_pipeline(source, language=args.language, max_steps=args.max_steps)
    app = PipelineApp(result)
    app.run()


def _main_compare() -> None:
    parser = argparse.ArgumentParser(
        description="RedDragon Pipeline Comparator — side-by-side TUI"
    )
    parser.add_argument("compare", help="compare subcommand")
    parser.add_argument(
        "specs",
        nargs="+",
        help="Language:file pairs (e.g., c:demo.c rust:demo.rs)",
    )
    parser.add_argument(
        "-s",
        "--max-steps",
        type=int,
        default=300,
        help="Maximum execution steps (default: 300)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    from viz.compare_app import CompareApp
    from viz.pipeline import run_pipeline

    results = []
    for spec in args.specs:
        lang, path = spec.split(":", 1)
        with open(path) as f:
            source = f.read()
        result = run_pipeline(source, language=lang, max_steps=args.max_steps)
        results.append(result)

    app = CompareApp(results)
    app.run()


main()
