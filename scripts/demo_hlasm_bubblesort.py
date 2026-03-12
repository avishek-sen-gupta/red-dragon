#!/usr/bin/env python3
"""Demo: LLM frontend lowers an HLASM bubble sort to IR, then the VM executes it.

Usage:
    poetry run python scripts/demo_hlasm_bubblesort.py
    poetry run python scripts/demo_hlasm_bubblesort.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interpreter.cfg import build_cfg
from interpreter.default_conversion_rules import DefaultTypeConversionRules
from interpreter.llm_client import get_llm_client
from interpreter.llm_frontend import LLMFrontend
from interpreter.registry import build_registry
from interpreter.run import execute_cfg
from interpreter.run_types import VMConfig
from interpreter.type_inference import infer_types
from interpreter.type_resolver import TypeResolver
from interpreter.vm_types import SymbolicValue

logger = logging.getLogger(__name__)

# HLASM bubble sort: sort a 5-element fullword array in ascending order.
# Array: [5, 3, 8, 1, 4] → expected [1, 3, 4, 5, 8]
#
# Pseudocode:
#   n = 5
#   for i = 0 to n-2:
#     swapped = 0
#     for j = 0 to n-2-i:
#       if arr[j] > arr[j+1]:
#         swap arr[j], arr[j+1]
#         swapped = 1
#     if swapped == 0: break
#
# In HLASM, the array is defined as fullwords (F) in storage.
# Registers:
#   R2 = base address of ARR
#   R3 = outer loop counter (passes remaining)
#   R4 = inner loop index (byte offset into array, increments by 4)
#   R5 = inner loop limit (byte offset)
#   R6 = arr[j]
#   R7 = arr[j+1]
#   R8 = swap flag
#   R9 = temp for swap

HLASM_SOURCE = """\
BSORT    CSECT
*--------------------------------------------------------------
* Bubble sort: sort ARR (5 fullwords) in ascending order
* Uses element indices (0-based) rather than byte offsets.
*--------------------------------------------------------------
         LA    R2,ARR           R2 = base address of array
         LA    R3,4             R3 = n-1 = 4 (outer passes)
*
OUTER    SR    R8,R8            swapped = 0
         SR    R4,R4            j = 0 (element index)
         LR    R5,R3            R5 = inner loop limit
*
INNER    L     R6,ARR(R4)       R6 = arr[j]
         LA    R9,1(R4)         R9 = j+1
         L     R7,ARR(R9)       R7 = arr[j+1]
         CR    R6,R7            compare arr[j] with arr[j+1]
         BNH   NOSWAP           if arr[j] <= arr[j+1], skip swap
*                                else swap:
         ST    R7,ARR(R4)       arr[j] = arr[j+1]  (the smaller)
         ST    R6,ARR(R9)       arr[j+1] = arr[j]  (the larger)
         LA    R8,1             swapped = 1
*
NOSWAP   LA    R4,1(R4)         j += 1 (next element)
         CR    R4,R5            compare j with limit
         BL    INNER            if j < limit, continue inner loop
*
         LTR   R8,R8            test swapped flag
         BZ    DONE             if no swaps, array is sorted
         BCT   R3,OUTER         decrement passes, loop if > 0
*
DONE     BR    R14              return
*
ARR      DC    F'5'             arr[0] = 5
         DC    F'3'             arr[1] = 3
         DC    F'8'             arr[2] = 8
         DC    F'1'             arr[3] = 1
         DC    F'4'             arr[4] = 4
         END   BSORT
"""

LANGUAGE_NAME = "hlasm"
EXPECTED_SORTED = [1, 3, 4, 5, 8]


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
    parser = argparse.ArgumentParser(description="LLM frontend demo: HLASM bubble sort")
    parser.add_argument(
        "--backend",
        "-b",
        default="claude",
        choices=["claude", "openai", "ollama", "huggingface"],
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    # ── Show source ──
    _print_header(f"Source ({LANGUAGE_NAME})")
    for i, line in enumerate(HLASM_SOURCE.strip().splitlines(), 1):
        print(f"  {i:3d} | {line}")
    print(f"\n  Input array:    [5, 3, 8, 1, 4]")
    print(f"  Expected sorted: {EXPECTED_SORTED}")

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

    # ── Type Inference ──
    _print_header("Type Inference")
    resolver = TypeResolver(DefaultTypeConversionRules())
    env = infer_types(instructions, resolver)

    print("  Register types:")
    for reg, typ in sorted(env.register_types.items()):
        print(f"    {reg:8s} : {typ}")

    print("\n  Variable types:")
    for var, typ in sorted(env.var_types.items()):
        print(f"    {var:8s} : {typ}")

    from interpreter.type_expr import UNBOUND

    unbound_sigs = env.method_signatures.get(UNBOUND, {})
    if unbound_sigs:
        print("\n  Function signatures:")
        for name, sigs in sorted(unbound_sigs.items()):
            for sig in sigs:
                params = ", ".join(f"{p}: {t}" for p, t in sig.params)
                print(f"    {name}({params}) -> {sig.return_type}")

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

    config = VMConfig(
        backend=args.backend,
        max_steps=2000,
        verbose=args.verbose,
        source_language=LANGUAGE_NAME,
    )

    t0 = time.perf_counter()
    vm, stats = execute_cfg(cfg, cfg.entry, registry, config)
    t_exec = time.perf_counter() - t0

    print(
        f"  Execution: {stats.steps} steps, {stats.llm_calls} LLM calls "
        f"in {t_exec:.2f}s"
    )
    print("\n  Final variables:")
    _show_vars(vm)

    # ── Verify ──
    _print_header("Verification")
    frame = vm.call_vars = vm.call_stack[0]

    # The LLM may represent the array in different ways:
    # 1. As an array object on the heap (arr[0], arr[1], ...)
    # 2. As individual variables (arr_0, arr_1, ... or ARR_0, ARR_1, ...)
    # 3. As a list in a single variable
    # Let's check all possibilities.

    all_vars = frame.local_vars

    # Try to find array-like variables
    arr_candidates = sorted(
        [
            (n, v)
            for n, v in all_vars.items()
            if isinstance(v, (int, float)) and not n.startswith("__")
        ],
        key=lambda x: x[0],
    )

    print(f"  All numeric variables: {[(n, v) for n, v in arr_candidates]}")

    # Check heap for array objects
    if vm.heap:
        print(f"\n  Heap objects ({len(vm.heap)}):")
        for addr, obj in vm.heap.items():
            print(f"    [{addr}] type={obj.type_hint} fields={dict(obj.fields)}")

    # Try to extract the sorted array
    sorted_result = []

    # Strategy 1: look for arr[0]..arr[4] or ARR[0]..ARR[4] in heap
    for addr, obj in vm.heap.items():
        fields = obj.fields
        if any(str(i) in fields for i in range(5)):
            sorted_result = [fields.get(str(i)) for i in range(5)]
            print(f"\n  Found array in heap object [{addr}]: {sorted_result}")
            break

    # Strategy 2: look for variables like arr_0..arr_4
    if not sorted_result:
        for prefix in ("arr_", "ARR_", "arr", "ARR", "a_", "A_"):
            candidates = []
            for i in range(5):
                key = f"{prefix}{i}"
                if key in all_vars:
                    candidates.append(all_vars[key])
            if len(candidates) == 5:
                sorted_result = candidates
                print(
                    f"\n  Found array as variables {prefix}0..{prefix}4: {sorted_result}"
                )
                break

    # Strategy 3: check if any variable holds a list
    if not sorted_result:
        for n, v in all_vars.items():
            if isinstance(v, list) and len(v) == 5:
                sorted_result = v
                print(f"\n  Found array as list in variable '{n}': {sorted_result}")
                break

    if sorted_result:
        concrete = [int(x) if isinstance(x, (int, float)) else x for x in sorted_result]
        if concrete == EXPECTED_SORTED:
            print(f"\n  ✓ CORRECT: {concrete} matches expected {EXPECTED_SORTED}")
        else:
            print(f"\n  ✗ WRONG: {concrete} does not match expected {EXPECTED_SORTED}")
    else:
        print("\n  Could not find array in variables or heap.")
        print("  Dumping all state for manual inspection:")
        print(f"\n  Variables:")
        _show_vars(vm)
        print(f"\n  Heap:")
        for addr, obj in vm.heap.items():
            print(f"    [{addr}] type={obj.type_hint} fields={dict(obj.fields)}")

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
