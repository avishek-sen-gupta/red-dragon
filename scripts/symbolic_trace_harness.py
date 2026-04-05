#!/usr/bin/env python3
"""Execute a multi-file project function and trace all symbolic values.

Compiles a project directory, executes a target function, and produces a
deterministic report of every symbolic value in the final VM state plus
the instruction/block where each symbolic was first created.

Usage:
    # Search for candidate entry points:
    poetry run python scripts/symbolic_trace_harness.py \\
        --root /path/to/project \\
        --language java \\
        --search MyClass

    # Execute a specific function and trace symbolics:
    poetry run python scripts/symbolic_trace_harness.py \\
        --root /path/to/project \\
        --language java \\
        --label 'module.package.MyClass.func_main_4'

Options:
    --root          Project root directory to compile
    --language      Source language (java, python, javascript, etc.)
    --label         Exact CodeLabel of the function to execute
    --search        Search for functions whose label contains this substring
    --max-steps     Maximum VM execution steps (default: 2000)
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interpreter.constants import Language
from interpreter.project.compiler import compile_directory
from interpreter.project.entry_point import EntryPoint
from interpreter.run import run_linked_traced
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm_types import SymbolicValue


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Compile a multi-file project and trace symbolic values."
    )
    p.add_argument(
        "--root", type=Path, required=True, help="Project root directory to compile"
    )
    p.add_argument(
        "--language",
        type=str,
        required=True,
        help="Source language (java, python, javascript, ...)",
    )
    p.add_argument(
        "--label",
        type=str,
        default=None,
        help="Exact CodeLabel of the function to execute",
    )
    p.add_argument(
        "--search",
        type=str,
        default=None,
        help="Search for functions whose label contains this substring",
    )
    p.add_argument(
        "--max-steps",
        type=int,
        default=2000,
        help="Maximum VM execution steps (default: 2000)",
    )
    return p.parse_args()


def resolve_language(name: str) -> Language:
    """Map a CLI language string to Language enum."""
    lookup = {member.value.lower(): member for member in Language}
    lookup.update({member.name.lower(): member for member in Language})
    key = name.lower()
    if key not in lookup:
        valid = sorted(
            {m.value.lower() for m in Language} | {m.name.lower() for m in Language}
        )
        print(f"Unknown language '{name}'. Valid: {', '.join(valid)}", file=sys.stderr)
        sys.exit(1)
    return lookup[key]


def compile_project(root: Path, lang: Language):
    """Compile and link the project, returning the LinkedProgram."""
    print(f"=== Compiling {root} ({lang.value}) ===")
    linked = compile_directory(root, lang)
    print(
        f"  {len(linked.modules)} modules, "
        f"{len(linked.merged_ir)} IR instructions, "
        f"{len(linked.func_symbol_table)} functions"
    )
    return linked


def search_functions(linked, substring: str) -> None:
    """Print all functions whose label contains the given substring."""
    print(f"\n=== Functions matching '{substring}' ===")
    matches = []
    for label, ref in linked.func_symbol_table.items():
        if substring in str(label):
            matches.append((str(label), ref.name))
    if not matches:
        print("  (no matches)")
    else:
        for label_str, name in sorted(matches):
            print(f"  {label_str}  ->  {name}")
    print(f"\n  Total: {len(matches)} matches")


def _unwrap(val):
    """Unwrap TypedValue to get raw value."""
    return val.value if isinstance(val, TypedValue) else val


def execute_and_trace(linked, label: str, max_steps: int) -> None:
    """Execute a function by exact label and report symbolic values."""
    print(f"\n=== Executing: {label} (max_steps={max_steps}) ===")
    entry = EntryPoint.function(lambda f, _lbl=label: str(f.label) == _lbl)

    try:
        vm, trace = run_linked_traced(linked, entry, max_steps=max_steps)
    except Exception as e:
        print(f"\nExecution failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        return

    print(f"\n  Steps: {trace.stats.steps}")
    print(f"  LLM calls: {trace.stats.llm_calls}")
    print(f"  Symbolic count: {trace.stats.final_symbolic_count}")
    print(f"  Heap objects: {trace.stats.final_heap_objects}")

    # --- Final state symbolic values ---
    print(f"\n=== Symbolic Values in Final State ===")

    final_step = trace.steps[-1] if trace.steps else None
    if not final_step:
        print("  (no execution steps recorded)")
        return

    final_vm = final_step.vm_state

    sym_in_vars = []
    sym_in_regs = []
    sym_in_heap = []

    for frame_idx, frame in enumerate(final_vm.call_stack):
        for var, val in frame.local_vars.items():
            raw = _unwrap(val)
            if isinstance(raw, SymbolicValue):
                sym_in_vars.append((frame_idx, str(frame.function_name), str(var), raw))
        for reg, val in frame.registers.items():
            raw = _unwrap(val)
            if isinstance(raw, SymbolicValue):
                sym_in_regs.append((frame_idx, str(frame.function_name), str(reg), raw))

    for addr, obj in final_vm.heap_items():
        for field, val in obj.fields.items():
            raw = _unwrap(val)
            if isinstance(raw, SymbolicValue):
                sym_in_heap.append((str(addr), str(field), raw))

    print(f"\n  Local vars ({len(sym_in_vars)}):")
    for frame_idx, func, var, sym in sym_in_vars[:50]:
        print(f"    [{frame_idx}] {func} :: {var} = {sym.name} (hint={sym.type_hint})")

    print(f"\n  Registers ({len(sym_in_regs)}):")
    for frame_idx, func, reg, sym in sym_in_regs[:50]:
        print(f"    [{frame_idx}] {func} :: {reg} = {sym.name} (hint={sym.type_hint})")

    print(f"\n  Heap fields ({len(sym_in_heap)}):")
    for addr, field, sym in sym_in_heap[:50]:
        print(f"    {addr}.{field} = {sym.name} (hint={sym.type_hint})")

    # --- Creation points ---
    print(f"\n=== Symbolic Value Creation Points ===")
    sym_first_seen: dict[str, dict] = {}
    for step in trace.steps:
        update = step.update
        for _reg, val in update.register_writes.items():
            raw = _unwrap(val)
            if isinstance(raw, SymbolicValue) and raw.name not in sym_first_seen:
                sym_first_seen[raw.name] = {
                    "step": step.step_index,
                    "instruction": str(step.instruction),
                    "block": str(step.block_label),
                    "hint": raw.type_hint,
                }
        for _var, val in update.var_writes.items():
            raw = _unwrap(val)
            if isinstance(raw, SymbolicValue) and raw.name not in sym_first_seen:
                sym_first_seen[raw.name] = {
                    "step": step.step_index,
                    "instruction": str(step.instruction),
                    "block": str(step.block_label),
                    "hint": raw.type_hint,
                }

    for name, info in sorted(sym_first_seen.items(), key=lambda x: x[1]["step"]):
        print(f"  {name} (hint={info['hint']})")
        print(f"    Step {info['step']}: {info['instruction'][:120]}")
        print(f"    Block: {info['block']}")
        print()

    total = len(sym_in_vars) + len(sym_in_regs) + len(sym_in_heap)
    print(
        f"=== Summary: {total} symbolic values, {len(sym_first_seen)} unique creation points ==="
    )


def main() -> None:
    args = parse_args()

    if not args.root.exists():
        print(f"Error: root directory does not exist: {args.root}", file=sys.stderr)
        sys.exit(1)

    lang = resolve_language(args.language)
    linked = compile_project(args.root, lang)

    if args.search:
        search_functions(linked, args.search)
    elif args.label:
        execute_and_trace(linked, args.label, args.max_steps)
    else:
        print(
            "Error: specify --label to execute or --search to find functions.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
