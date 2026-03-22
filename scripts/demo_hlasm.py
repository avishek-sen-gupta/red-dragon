#!/usr/bin/env python3
"""Demo: LLM frontend lowers HLASM (IBM High Level Assembler) to IR, then the VM executes it.

HLASM is not one of RedDragon's 15 tree-sitter languages.  The LLM frontend
sends the raw source to an LLM constrained by the IR schema, then the
deterministic VM executes the resulting IR.

Usage:
    poetry run python scripts/demo_hlasm.py
    poetry run python scripts/demo_hlasm.py --backend ollama
    poetry run python scripts/demo_hlasm.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interpreter.cfg import build_cfg
from interpreter.llm_client import get_llm_client
from interpreter.llm_frontend import LLMFrontend
from interpreter.registry import build_registry
from interpreter.run import execute_cfg
from interpreter.run_types import VMConfig
from interpreter.types.typed_value import TypedValue
from interpreter.vm_types import SymbolicValue

logger = logging.getLogger(__name__)

# Simple HLASM program: compute sum = 1 + 2 + 3 + ... + 10
# Uses a loop with a counter register and an accumulator.
HLASM_SOURCE = """\
SUMLOOP  CSECT
         SR    R3,R3          Clear accumulator (sum = 0)
         LA    R4,1           Load counter = 1
         LA    R5,10          Load limit = 10
LOOP     AR    R3,R4          sum = sum + counter
         LA    R4,1(R4)       counter = counter + 1
         CR    R4,R5          Compare counter to limit
         BNH   LOOP           Branch if counter <= limit
         ST    R3,SUM         Store result
         BR    R14            Return
SUM      DS    F              Result storage
         END   SUMLOOP
"""

LANGUAGE_NAME = "hlasm"

# Expected: sum of 1..10 = 55


def _print_header(title: str):
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}\n")


def _format_val(v):
    if isinstance(v, TypedValue):
        return _format_val(v.value)
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
    parser = argparse.ArgumentParser(description="LLM frontend demo for HLASM")
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

    # ── Show source ──
    _print_header(f"Source ({LANGUAGE_NAME})")
    for i, line in enumerate(HLASM_SOURCE.strip().splitlines(), 1):
        print(f"  {i:3d} | {line}")
    print(f"\n  Note: {LANGUAGE_NAME} has no tree-sitter frontend in RedDragon.")
    print("  The LLM frontend will lower this to the universal IR.")
    print("  Expected result: SUM = 55 (sum of 1..10)")

    # ── Phase 1: LLM IR generation ──
    _print_header(f"Phase 1: LLM IR Generation ({LANGUAGE_NAME} → IR)")
    print(f"  Sending {LANGUAGE_NAME} source to LLM for lowering...")

    llm_client = get_llm_client(provider=args.backend)
    frontend = LLMFrontend(llm_client=llm_client, language=LANGUAGE_NAME)

    t0 = time.perf_counter()
    instructions = frontend.lower(HLASM_SOURCE.encode("utf-8"))
    t_lower = time.perf_counter() - t0

    print(f"  LLM produced {len(instructions)} IR instructions in {t_lower:.2f}s\n")
    print("  IR:")
    for inst in instructions:
        print(f"    {inst}")

    # ── Phase 2: Build CFG ──
    _print_header("Phase 2: Build CFG (deterministic)")
    cfg = build_cfg(instructions)
    print(f"  {len(cfg.blocks)} basic blocks:")
    for label, block in cfg.blocks.items():
        preds = ", ".join(block.predecessors) if block.predecessors else "(none)"
        succs = ", ".join(block.successors) if block.successors else "(none)"
        print(
            f"    [{label}]  {len(block.instructions)} instructions  "
            f"preds={preds}  succs={succs}"
        )

    # ── Phase 3: Execute ──
    _print_header("Phase 3: VM Execution")
    registry = build_registry(instructions, cfg)
    print(
        f"  Registry: {len(registry.func_params)} functions, "
        f"{len(registry.classes)} classes"
    )

    config = VMConfig(
        backend=args.backend,
        max_steps=500,
        verbose=args.verbose,
        source_language=LANGUAGE_NAME,
    )

    t0 = time.perf_counter()
    vm, stats = execute_cfg(cfg, cfg.entry, registry, config)
    t_exec = time.perf_counter() - t0

    print(
        f"\n  Execution: {stats.steps} steps, {stats.llm_calls} LLM backend calls "
        f"in {t_exec:.2f}s"
    )
    print("\n  Final variables:")
    _show_vars(vm)

    # ── Verify ──
    _print_header("Verification")
    frame = vm.call_stack[0]
    sum_candidates = [
        name
        for name in frame.local_vars
        if "sum" in name.lower() or name in ("R3", "r3")
    ]
    print(f"  Looking for sum result in: {sum_candidates}")
    for name in sum_candidates:
        tv = frame.local_vars[name]
        val = tv.value
        print(f"    {name} = {_format_val(tv)}")
        if isinstance(val, (int, float)) and val == 55:
            print(f"    ✓ CORRECT: {name} = 55 (expected sum of 1..10)")
        elif isinstance(val, (int, float)):
            print(f"    ✗ WRONG: {name} = {val} (expected 55)")

    # Check all numeric vars for 55
    found_55 = [
        (n, tv.value)
        for n, tv in frame.local_vars.items()
        if isinstance(tv.value, (int, float))
        and tv.value == 55
        and not n.startswith("__")
    ]
    if found_55:
        print(f"\n  ✓ Found expected value 55 in: {[n for n, _ in found_55]}")
    else:
        print("\n  ✗ Value 55 not found in any variable.")
        print("  All final variables:")
        _show_vars(vm)

    # ── Summary ──
    _print_header("Summary")
    print(f"  Language          : {LANGUAGE_NAME} (no tree-sitter frontend)")
    print(f"  IR instructions   : {len(instructions)}")
    print(f"  CFG blocks        : {len(cfg.blocks)}")
    print(f"  Execution steps   : {stats.steps}")
    print(f"  LLM calls (lower) : 1")
    print(f"  LLM calls (VM)    : {stats.llm_calls}")
    print(f"  Lowering time     : {t_lower:.2f}s")
    print(f"  Execution time    : {t_exec:.2f}s")
    print(f"  Total             : {t_lower + t_exec:.2f}s")


if __name__ == "__main__":
    main()
