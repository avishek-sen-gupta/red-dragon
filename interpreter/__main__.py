"""CLI: uv run python -m interpreter <path> [--entry PROGRAM] [options]

Compiles and runs a COBOL program through the full pipeline:
  CICS pre-pass → ProLeap parse → IR lowering → CFG → VM execution

Examples:
    uv run python -m interpreter myprogram.cbl
    uv run python -m interpreter cobol/ --entry MAINPROG
    uv run python -m interpreter cobol/ --entry MAINPROG --max-steps 100000 --log-level INFO
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from interpreter.constants import Language
from interpreter.project.compiler import compile_directory
from interpreter.project.entry_point import EntryPoint
from interpreter.run import run, run_linked, initial_vm_state


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.WARNING),
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _entry_point(name: str | None) -> EntryPoint:
    if name is None:
        return EntryPoint.top_level()
    name_lower = name.lower()
    return EntryPoint.function(
        lambda ref, _n=name_lower: _n in str(ref.label).lower()
        and "init_params" not in str(ref.label).lower()
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="python -m interpreter",
        description="Compile and run a COBOL program through the full pipeline.",
    )
    ap.add_argument("path", help="COBOL source file (.cbl) or directory of sources")
    ap.add_argument(
        "--entry",
        metavar="PROGRAM",
        help="Entry program name, e.g. MAINPROG (default: top-level execution)",
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
    args = ap.parse_args()

    _configure_logging(args.log_level)

    target = Path(args.path).resolve()
    ep = _entry_point(args.entry)

    if target.is_file():
        run(
            target.read_text(encoding="utf-8"),
            language=Language.COBOL,
            entry_point=ep,
            max_steps=args.max_steps,
            verbose=args.verbose,
        )
    elif target.is_dir():
        linked = compile_directory(target, Language.COBOL)
        run_linked(
            linked,
            ep,
            max_steps=args.max_steps,
            verbose=args.verbose,
            initial_vm=initial_vm_state(),
        )
    else:
        print(f"error: {target} does not exist", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
