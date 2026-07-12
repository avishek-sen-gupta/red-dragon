#!/usr/bin/env python3
"""mutation_test.py — run mutmut against named RedDragon target modules.

Usage:
    python scripts/mutation_test.py --list
    python scripts/mutation_test.py --target vm
    python scripts/mutation_test.py --target core
    python scripts/mutation_test.py --target all-core
    python scripts/mutation_test.py --results
    python scripts/mutation_test.py --target vm --use-coverage
"""

from __future__ import annotations

import argparse
import subprocess
import sys

TARGETS: dict[str, list[str]] = {
    "core": [
        "interpreter/ir.py",
        "interpreter/instructions.py",
        "interpreter/register.py",
    ],
    "vm": ["interpreter/vm/"],
    "handlers": ["interpreter/handlers/"],
    "all-core": [
        "interpreter/ir.py",
        "interpreter/instructions.py",
        "interpreter/register.py",
        "interpreter/vm/",
        "interpreter/handlers/",
    ],
}


def run_target(target: str, use_coverage: bool = False) -> int:
    """Run mutmut against the named target. Returns mutmut's exit code."""
    paths = TARGETS[target]
    paths_str = ",".join(paths)

    if use_coverage:
        cov_paths = ",".join(f"--cov={p}" for p in paths)
        cov_cmd = [
            "uv",
            "run",
            "python",
            "-m",
            "pytest",
            *cov_paths.split(),
            "tests/",
            "-q",
            "--tb=no",
        ]
        result = subprocess.run(cov_cmd)
        if result.returncode != 0:
            return result.returncode

    cmd = [
        "uv",
        "run",
        "mutmut",
        "run",
        f"--paths-to-mutate={paths_str}",
    ]
    if use_coverage:
        cmd.append("--use-coverage")

    result = subprocess.run(cmd)
    return result.returncode


def show_results() -> int:
    """Print mutmut results summary from the last run. Returns exit code."""
    result = subprocess.run(["uv", "run", "mutmut", "results"])
    return result.returncode


def list_targets() -> None:
    """Print all available targets and their paths."""
    for name, paths in TARGETS.items():
        print(f"  {name}: {', '.join(paths)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run mutmut on RedDragon core modules.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--target",
        choices=list(TARGETS.keys()),
        help="Named module target to mutate.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available targets and their paths.",
    )
    parser.add_argument(
        "--results",
        action="store_true",
        help="Print mutmut results summary from the last run.",
    )
    parser.add_argument(
        "--use-coverage",
        action="store_true",
        help=(
            "Run pytest --cov first, then pass --use-coverage to mutmut. "
            "Faster for large targets; requires pytest-cov (already installed)."
        ),
    )
    args = parser.parse_args()

    if args.list:
        list_targets()
        return

    if args.results:
        sys.exit(show_results())

    if args.target:
        sys.exit(run_target(args.target, use_coverage=args.use_coverage))

    parser.print_help()


if __name__ == "__main__":
    main()
