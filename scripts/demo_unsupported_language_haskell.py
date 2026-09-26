#!/usr/bin/env python3
"""Demo: LLM frontend lowers an unsupported language to IR, then the VM executes it.

RedDragon has 15 tree-sitter frontends, but the LLM frontend can handle
*any* language — it sends raw source to the LLM and asks it to emit IR.
This demo shows that working end-to-end with Haskell, which has no
tree-sitter frontend in the project.

The pipeline:
  1. LLM Frontend — lowers Haskell source to the universal 27-opcode IR
  2. CFG builder  — constructs basic blocks (deterministic, no LLM)
  3. VM execution — runs the IR; external calls produce symbolic values

Usage:
    uv run python scripts/demo_unsupported_language.py
    uv run python scripts/demo_unsupported_language.py --backend ollama
    uv run python scripts/demo_unsupported_language.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interpreter.cfg import build_cfg
from interpreter.cli_output import emit
from interpreter.llm.llm_client import get_llm_client
from interpreter.llm.llm_frontend import LLMFrontend
from interpreter.registry import build_registry
from interpreter.run import execute_cfg, initial_vm_state
from interpreter.run_types import UnresolvedCallStrategy, VMConfig
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm_types import SymbolicValue

logger = logging.getLogger(__name__)

HASKELL_SOURCE = """\
import Data.Char (toUpper, ord)

factorial :: Int -> Int
factorial 0 = 1
factorial n = n * factorial (n - 1)

x = factorial 5
ch = toUpper 'a'
code = ord ch
total = x + code
"""

LANGUAGE_NAME = "haskell"


def _print_header(title: str):
    width = 60
    emit(f"\n{'=' * width}")
    emit(f"  {title}")
    emit(f"{'=' * width}\n")


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
        emit(f"    {name} = {_format_val(val)}")


def main():
    parser = argparse.ArgumentParser(
        description="LLM frontend demo for unsupported languages"
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

    # ── Show source ──
    _print_header(f"Source ({LANGUAGE_NAME})")
    for i, line in enumerate(HASKELL_SOURCE.strip().splitlines(), 1):
        emit(f"  {i:3d} | {line}")
    emit(f"\n  Note: {LANGUAGE_NAME} has no tree-sitter frontend in RedDragon.")
    emit("  The LLM frontend will lower this to the universal IR.")

    # ── Phase 1: LLM IR generation ──
    _print_header(f"Phase 1: LLM IR Generation ({LANGUAGE_NAME} → IR)")
    emit(f"  Sending {LANGUAGE_NAME} source to LLM for lowering...")

    llm_client = get_llm_client(provider=args.backend)
    frontend = LLMFrontend(llm_client=llm_client, language=LANGUAGE_NAME)

    t0 = time.perf_counter()
    instructions = frontend.lower(HASKELL_SOURCE.encode("utf-8"))
    t_lower = time.perf_counter() - t0

    emit(f"  LLM produced {len(instructions)} IR instructions in {t_lower:.2f}s\n")
    emit("  IR:")
    for inst in instructions:
        emit(f"    {inst}")

    # ── Phase 2: Build CFG ──
    _print_header("Phase 2: Build CFG (deterministic)")
    cfg = build_cfg(instructions)
    emit(f"  {len(cfg.blocks)} basic blocks:")
    for label, block in cfg.blocks.items():
        preds = (
            ", ".join(str(p) for p in block.predecessors)
            if block.predecessors
            else "(none)"
        )
        succs = (
            ", ".join(str(s) for s in block.successors)
            if block.successors
            else "(none)"
        )
        emit(
            f"    [{label}]  {len(block.instructions)} instructions  preds={preds}  succs={succs}"
        )

    # ── Phase 3: Execute ──
    _print_header("Phase 3: VM Execution")
    registry = build_registry(instructions, cfg)
    emit(
        f"  Registry: {len(registry.func_params)} functions, {len(registry.classes)} classes"
    )

    config = VMConfig(
        backend=args.backend,
        max_steps=200,
        verbose=args.verbose,
        source_language=LANGUAGE_NAME,
        unresolved_call_strategy=UnresolvedCallStrategy.LLM,
    )

    t0 = time.perf_counter()
    vm, stats = execute_cfg(cfg, cfg.entry, registry, config, vm=initial_vm_state())
    t_exec = time.perf_counter() - t0

    resolver_note = (
        " (excludes LLM resolver calls shown as '[local] LLM plausible:')"
        if stats.llm_calls == 0
        else ""
    )
    emit(
        f"\n  Execution: {stats.steps} steps, {stats.llm_calls} LLM backend calls"
        f"{resolver_note} in {t_exec:.2f}s"
    )
    emit("\n  Final variables:")
    _show_vars(vm)

    # ── Summary ──
    _print_header("Summary")
    emit(f"  Language          : {LANGUAGE_NAME} (no tree-sitter frontend)")
    emit(f"  IR instructions   : {len(instructions)}")
    emit(f"  CFG blocks        : {len(cfg.blocks)}")
    emit(f"  Functions found   : {len(registry.func_params)}")
    emit(f"  Execution steps   : {stats.steps}")
    emit("  LLM calls (lower) : 1")
    emit(f"  LLM calls (VM backend) : {stats.llm_calls}")
    emit("  LLM calls (resolver)   : see '[local] LLM plausible:' steps above")
    emit(f"  Lowering time     : {t_lower:.2f}s")
    emit(f"  Execution time    : {t_exec:.2f}s")
    emit(f"  Total             : {t_lower + t_exec:.2f}s")


if __name__ == "__main__":
    main()
