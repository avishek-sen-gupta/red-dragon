#!/usr/bin/env python3
"""Demo: end-to-end LLM IR generation + LLM VM execution.

Exercises both LLM integration points in a single pipeline run:
  1. LLM Frontend — source code is lowered to IR by the LLM (not tree-sitter)
  2. LLM Backend  — the VM uses the LLM to resolve unresolved external calls
                    (math.sqrt, math.floor) via plausible value inference

Usage:
    poetry run python scripts/demo_llm_e2e.py
    poetry run python scripts/demo_llm_e2e.py --backend ollama
    poetry run python scripts/demo_llm_e2e.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interpreter import constants
from interpreter.constants import Language
from interpreter.run import run
from interpreter.run_types import UnresolvedCallStrategy
from interpreter.vm_types import SymbolicValue

SAMPLE_SOURCE = """\
import math

x = math.sqrt(16)
y = x + 1
z = math.floor(7.8)
total = x + y + z
"""


def _print_header(title: str):
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}\n")


def _format_val(v):
    if isinstance(v, SymbolicValue):
        return (
            f"SymbolicValue({v.name}, hint={v.type_hint}, "
            f"constraints={v.constraints})"
        )
    return repr(v)


def _show_vars(vm):
    frame = vm.call_stack[0]
    for name, val in sorted(frame.local_vars.items()):
        if name.startswith("__"):
            continue
        print(f"    {name} = {_format_val(val)}")


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end LLM frontend + LLM backend demo"
    )
    parser.add_argument(
        "--backend",
        "-b",
        default="claude",
        choices=["claude", "openai", "ollama", "huggingface"],
        help="LLM provider (default: claude)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging and step-by-step output",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    backend = args.backend

    # ── Show source ──
    _print_header("Source")
    for i, line in enumerate(SAMPLE_SOURCE.strip().splitlines(), 1):
        print(f"  {i:3d} | {line}")

    # ── Phase 1: LLM Frontend (IR generation) ──
    _print_header(f"Phase 1: LLM IR Generation (backend={backend})")
    print("  Lowering source to IR via LLM frontend...")
    t0 = time.perf_counter()
    vm_llm_frontend = run(
        SAMPLE_SOURCE,
        language=Language.PYTHON,
        backend=backend,
        frontend_type=constants.FRONTEND_LLM,
        verbose=args.verbose,
        unresolved_call_strategy=UnresolvedCallStrategy.SYMBOLIC,
    )
    t_frontend = time.perf_counter() - t0

    print(f"\n  LLM frontend + symbolic execution completed in {t_frontend:.2f}s")
    print("  Final variables (external calls are symbolic):")
    _show_vars(vm_llm_frontend)

    # ── Phase 2: LLM Backend (VM execution with plausible resolution) ──
    _print_header(f"Phase 2: LLM VM Execution (backend={backend})")
    print("  Re-running with deterministic frontend + LLM unresolved call resolver...")
    t0 = time.perf_counter()
    vm_llm_backend = run(
        SAMPLE_SOURCE,
        language=Language.PYTHON,
        backend=backend,
        frontend_type=constants.FRONTEND_DETERMINISTIC,
        verbose=args.verbose,
        unresolved_call_strategy=UnresolvedCallStrategy.LLM,
    )
    t_backend = time.perf_counter() - t0

    print(f"\n  Deterministic frontend + LLM resolver completed in {t_backend:.2f}s")
    print("  Final variables (external calls resolved by LLM):")
    _show_vars(vm_llm_backend)

    # ── Summary ──
    _print_header("Summary")
    print(f"  Phase 1 (LLM frontend + symbolic VM) : {t_frontend:.2f}s")
    print(f"  Phase 2 (deterministic + LLM resolver): {t_backend:.2f}s")
    print(f"  Total                                 : {t_frontend + t_backend:.2f}s")


if __name__ == "__main__":
    main()
