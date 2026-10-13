"""CLI: uv run python -m interpreter MAIN.cbl [--search-dir DIR]... [options]

Compiles and runs a COBOL main program through the full pipeline:
  ProLeap parse → IR lowering → CFG → VM execution

Examples:
    uv run python -m interpreter myprogram.cbl
    uv run python -m interpreter cobol/MAINPROG.cbl --search-dir cobol/
    uv run python -m interpreter cobol/MAINPROG.cbl --search-dir cobol/ --max-steps 100000 --log-level INFO
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cli_output import emit_err
from interpreter.project.coprocessor_compile import compile_program
from interpreter.project.entry_point import EntryPoint
from interpreter.run import initial_vm_state, run_linked


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.WARNING),
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m interpreter",
        description="Compile and run a COBOL main program through the full pipeline.",
    )
    ap.add_argument("path", type=Path, help="The main program's COBOL source file")
    ap.add_argument(
        "--search-dir",
        action="append",
        type=Path,
        default=[],
        metavar="DIR",
        help="Search for called programs and copybooks here (repeatable, in order)",
    )
    ap.add_argument(
        "--max-steps",
        type=int,
        default=50_000,
        metavar="N",
        help="Maximum VM steps (default: 50000)",
    )
    ap.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: WARNING)",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Emit IR listing and step-by-step execution to stderr",
    )
    return ap


def main() -> int:
    args = _parser().parse_args()
    _configure_logging(args.log_level)

    target = args.path.resolve()
    if target.is_dir():
        emit_err(f"error: {target} is a directory; give the main program's source file")
        return 2
    if not target.is_file():
        emit_err(f"error: {target} does not exist")
        return 1

    search_dirs = [d.resolve() for d in args.search_dir]
    _, linked = compile_program(
        target.read_bytes(),
        make_cobol_parser(copybook_dirs=search_dirs),
        [],
        source_search_dirs=search_dirs,
    )
    run_linked(
        linked,
        EntryPoint.function(lambda ref: ref.label == linked.entry_func_label),
        max_steps=args.max_steps,
        verbose=args.verbose,
        initial_vm=initial_vm_state(),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
