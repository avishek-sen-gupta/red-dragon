"""Allow running viz as a module: poetry run python -m viz <source_file>

Compare mode:
  poetry run python -m viz --compare c:demo.c rust:demo.rs python:demo.py
"""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RedDragon Pipeline Visualizer — interactive TUI"
    )

    subparsers = parser.add_subparsers(dest="mode")

    # Default mode: single file
    parser.add_argument("source_file", nargs="?", help="Path to source file")
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

    # Compare mode
    compare_parser = subparsers.add_parser(
        "compare", help="Compare pipeline across languages"
    )
    compare_parser.add_argument(
        "specs",
        nargs="+",
        help="Language:file pairs (e.g., c:demo.c rust:demo.rs)",
    )
    compare_parser.add_argument(
        "-s",
        "--max-steps",
        type=int,
        default=300,
        help="Maximum execution steps (default: 300)",
    )

    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    if args.mode == "compare":
        _run_compare(args)
    elif args.source_file:
        _run_single(args)
    else:
        parser.print_help()
        sys.exit(1)


def _run_single(args) -> None:
    from viz.app import PipelineApp
    from viz.pipeline import run_pipeline

    with open(args.source_file) as f:
        source = f.read()

    result = run_pipeline(source, language=args.language, max_steps=args.max_steps)
    app = PipelineApp(result)
    app.run()


def _run_compare(args) -> None:
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
