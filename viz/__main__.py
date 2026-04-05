"""Allow running viz as a module: poetry run python -m viz <source_file>

Single file:
  poetry run python -m viz demo.c -l c

Compare mode:
  poetry run python -m viz compare c:demo.c rust:demo.rs

Lowering trace:
  poetry run python -m viz lower demo.py -l python

Coverage matrix:
  poetry run python -m viz coverage
  poetry run python -m viz coverage -l python,javascript,rust

Multi-file project:
  poetry run python -m viz project /path/to/dir -l java -s 500
"""

from __future__ import annotations

import argparse
import logging
import sys


def main() -> None:
    # Detect subcommand by checking first arg
    subcommand = sys.argv[1] if len(sys.argv) > 1 else ""
    dispatch = {
        "compare": _main_compare,
        "lower": _main_lower,
        "coverage": _main_coverage,
        "project": _main_project,
    }
    handler = dispatch.get(subcommand, _main_single)
    handler()


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

    results = [
        run_pipeline(open(path).read(), language=lang, max_steps=args.max_steps)
        for spec in args.specs
        for lang, path in [spec.split(":", 1)]
    ]

    app = CompareApp(results)
    app.run()


def _main_lower() -> None:
    parser = argparse.ArgumentParser(
        description="RedDragon Lowering Trace — interactive TUI"
    )
    parser.add_argument("lower", help="lower subcommand")
    parser.add_argument("source_file", help="Path to source file to trace")
    parser.add_argument(
        "-l", "--language", default="python", help="Source language (default: python)"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    from viz.lowering_app import LoweringApp
    from viz.lowering_trace import trace_lowering

    with open(args.source_file) as f:
        source = f.read()

    result = trace_lowering(source, language=args.language)
    app = LoweringApp(result)
    app.run()


def _main_coverage() -> None:
    parser = argparse.ArgumentParser(
        description="RedDragon Frontend Coverage Matrix — interactive TUI"
    )
    parser.add_argument("coverage", help="coverage subcommand")
    parser.add_argument(
        "-l",
        "--languages",
        default="",
        help="Comma-separated languages (default: all)",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    from viz.coverage import build_coverage
    from viz.coverage_app import CoverageApp

    languages = [l.strip() for l in args.languages.split(",") if l.strip()] or None
    coverages = build_coverage(languages)
    app = CoverageApp(coverages)
    app.run()


def _main_project() -> None:
    parser = argparse.ArgumentParser(
        description="RedDragon Project Visualizer — multi-file TUI"
    )
    parser.add_argument("project", help="project subcommand")
    parser.add_argument("directory", help="Path to project root directory")
    parser.add_argument(
        "-l", "--language", required=True, help="Source language (required)"
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

    from pathlib import Path

    from viz.project_app import ProjectApp
    from viz.project_pipeline import run_project_pipeline

    directory = Path(args.directory).resolve()
    result = run_project_pipeline(directory, language=args.language)
    app = ProjectApp(result, project_root=directory, max_steps=args.max_steps)
    app.run()


main()
