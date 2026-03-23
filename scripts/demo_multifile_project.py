#!/usr/bin/env python3
"""Demo: multi-file project compilation, linking, execution, and analysis.

Shows the full multi-file pipeline end-to-end:
  1. Import discovery — BFS from entry file, tree-sitter-based extraction
  2. Import resolution — per-language resolver maps imports to local files
  3. Per-module compilation — each file compiled independently to IR
  4. Linking — namespace labels, rebase registers, rewrite cross-module refs
  5. Execution — merged program runs in the VM with cross-module function calls
  6. Interprocedural analysis — cross-module call graphs and dataflow

Creates a temporary multi-file Python project on disk, then runs the
full pipeline programmatically.

Usage:
    poetry run python scripts/demo_multifile_project.py
    poetry run python scripts/demo_multifile_project.py --verbose
    poetry run python scripts/demo_multifile_project.py --language javascript
"""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interpreter.api import analyze_project, run_project
from interpreter.constants import Language
from interpreter.project.compiler import compile_module, compile_project
from interpreter.project.imports import extract_imports
from interpreter.project.resolver import get_resolver
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm import SymbolicValue

logger = logging.getLogger(__name__)

# ── Sample projects per language ─────────────────────────────────

PYTHON_PROJECT = {
    "math_utils.py": """\
PI = 3.14159

def circle_area(radius):
    return PI * radius * radius

def add(a, b):
    return a + b
""",
    "geometry.py": """\
from math_utils import circle_area

class Circle:
    def __init__(self, radius):
        self.radius = radius

    def area(self):
        return circle_area(self.radius)
""",
    "main.py": """\
from math_utils import add, PI
from geometry import Circle

c = Circle(5)
a = c.area()

total = add(10, 20)
result = add(total, 7)
""",
}

JS_PROJECT = {
    "math_utils.js": """\
function add(a, b) {
    return a + b;
}

function multiply(a, b) {
    return a * b;
}
""",
    "main.js": """\
import { add, multiply } from "./math_utils.js";

var sum = add(10, 20);
var product = multiply(3, 7);
var result = add(sum, product);
""",
}

JAVA_PROJECT = {
    "Utils.java": """\
public class Utils {
    public static int add(int a, int b) {
        return a + b;
    }
    public static int square(int x) {
        return x * x;
    }
}
""",
    "Main.java": """\
public class Main {
    public static void main() {
        int sum = Utils.add(3, 4);
        int sq = Utils.square(5);
    }
}
""",
}

C_PROJECT = {
    "helpers.h": """\
int double_it(int x) {
    return x + x;
}
""",
    "main.c": """\
#include "helpers.h"

int main() {
    int result = double_it(21);
    return result;
}
""",
}

_PROJECTS = {
    "python": (PYTHON_PROJECT, Language.PYTHON, "main.py"),
    "javascript": (JS_PROJECT, Language.JAVASCRIPT, "main.js"),
    "java": (JAVA_PROJECT, Language.JAVA, "Main.java"),
    "c": (C_PROJECT, Language.C, "main.c"),
}


# ── Formatting helpers ───────────────────────────────────────────


def _print_header(title: str):
    width = 72
    print(f"\n{'━' * width}")
    print(f"  {title}")
    print(f"{'━' * width}\n")


def _print_subheader(title: str):
    print(f"\n  ── {title} ──\n")


def _format_val(v):
    if isinstance(v, TypedValue):
        return _format_val(v.value)
    if isinstance(v, SymbolicValue):
        return f"sym:{v.name}"
    return repr(v)


def _write_project(tmp_dir: Path, files: dict[str, str]):
    """Write project files to a temp directory."""
    for name, content in files.items():
        path = tmp_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


# ── Main ─────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Multi-file project compilation and execution demo"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show IR and detailed output"
    )
    parser.add_argument(
        "--language",
        "-l",
        default="python",
        choices=list(_PROJECTS.keys()),
        help="Language to demo (default: python)",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    project_files, language, entry_name = _PROJECTS[args.language]

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _write_project(tmp_dir, project_files)
        entry_file = tmp_dir / entry_name

        # ── Show source files ──
        _print_header(f"Multi-File Project Demo ({args.language.upper()})")
        for name, content in project_files.items():
            print(f"  ┌─ {name}")
            for line in content.strip().splitlines():
                print(f"  │ {line}")
            print(f"  └{'─' * 40}")
            print()

        # ── Phase 1: Import discovery ──
        _print_header("Phase 1: Import Discovery")
        t0 = time.perf_counter()

        refs = extract_imports(entry_file.read_bytes(), entry_file, language)
        print(f"  Entry file: {entry_name}")
        print(f"  Imports found: {len(refs)}")
        for ref in refs:
            names_str = ", ".join(ref.names) if ref.names else "(module)"
            rel = " [relative]" if ref.is_relative else ""
            sys_tag = " [system]" if ref.is_system else ""
            print(f"    {ref.kind} {ref.module_path} → {names_str}{rel}{sys_tag}")

        # ── Phase 2: Import resolution ──
        _print_subheader("Resolution")
        resolver = get_resolver(language)
        for ref in refs:
            resolved = resolver.resolve(ref, tmp_dir)
            if resolved.resolved_path:
                print(f"    {ref.module_path} → {resolved.resolved_path.name}")
            elif resolved.is_external:
                print(f"    {ref.module_path} → (external, skipped)")
            else:
                print(f"    {ref.module_path} → (not found)")

        # ── Phase 3: Per-module compilation ──
        _print_header("Phase 2: Per-Module Compilation")
        for name in project_files:
            path = tmp_dir / name
            unit = compile_module(path, language)
            func_names = list(unit.exports.functions.keys())
            class_names = list(unit.exports.classes.keys())
            var_names = list(unit.exports.variables.keys())
            print(f"  {name}:")
            print(f"    IR instructions : {len(unit.ir)}")
            if func_names:
                print(f"    Functions       : {', '.join(func_names)}")
            if class_names:
                print(f"    Classes         : {', '.join(class_names)}")
            if var_names:
                print(f"    Variables       : {', '.join(var_names)}")
            print(f"    Imports         : {len(unit.imports)}")

        # ── Phase 4: Linking ──
        _print_header("Phase 3: Compile + Link Project")
        t1 = time.perf_counter()
        linked = compile_project(entry_file, language, project_root=tmp_dir)
        link_time = time.perf_counter() - t1

        print(f"  Modules compiled  : {len(linked.modules)}")
        print(f"  Merged IR size    : {len(linked.merged_ir)} instructions")
        print(f"  Merged CFG blocks : {len(linked.merged_cfg.blocks)}")
        print(f"  Functions         : {len(linked.merged_registry.func_params)}")
        print(f"  Classes           : {len(linked.merged_registry.classes)}")
        print(f"  Entry block       : {linked.merged_cfg.entry}")
        print(f"  Time              : {link_time * 1000:.1f}ms")

        _print_subheader("Import Graph")
        for src, targets in linked.import_graph.items():
            src_name = src.name
            target_names = [t.name for t in targets]
            if target_names:
                print(f"    {src_name} → {', '.join(target_names)}")
            else:
                print(f"    {src_name} → (no local imports)")

        _print_subheader("Function Registry")
        for label, params in sorted(linked.merged_registry.func_params.items()):
            params_str = ", ".join(params) if params else "(none)"
            print(f"    {label}({params_str})")

        if args.verbose:
            _print_subheader("Merged IR (first 40 instructions)")
            for i, inst in enumerate(linked.merged_ir[:40]):
                print(f"    {inst}")
            if len(linked.merged_ir) > 40:
                print(f"    ... ({len(linked.merged_ir) - 40} more)")

        # ── Phase 5: Execution ──
        _print_header("Phase 4: VM Execution")
        t2 = time.perf_counter()
        vm = run_project(entry_file, language, project_root=tmp_dir, max_steps=500)
        exec_time = time.perf_counter() - t2

        frame = vm.call_stack[0] if vm.call_stack else None
        if frame:
            print(f"  Variables ({len(frame.local_vars)}):")
            for var, val in sorted(frame.local_vars.items()):
                # Skip internal/import variables
                if var.startswith("__") or var.startswith("sym_"):
                    continue
                print(f"    {var} = {_format_val(val)}")

        print(f"\n  Heap objects       : {len(vm.heap)}")
        print(f"  Time               : {exec_time * 1000:.1f}ms")

        # ── Phase 6: Interprocedural analysis ──
        _print_header("Phase 5: Interprocedural Analysis")
        t3 = time.perf_counter()
        result = analyze_project(entry_file, language, project_root=tmp_dir)
        analysis_time = time.perf_counter() - t3

        print(f"  Functions in call graph : {len(result.call_graph.functions)}")
        print(f"  Call sites              : {len(result.call_graph.call_sites)}")
        print(f"  Function summaries      : {len(result.summaries)}")
        print(f"  Time                    : {analysis_time * 1000:.1f}ms")

        if result.call_graph.functions:
            _print_subheader("Discovered Functions")
            for func in sorted(result.call_graph.functions, key=lambda f: f.label):
                print(f"    {func.label}")

        if result.call_graph.call_sites:
            _print_subheader("Call Sites")
            for cs in sorted(
                result.call_graph.call_sites,
                key=lambda c: c.caller.label,
            ):
                for callee in sorted(cs.callees, key=lambda f: f.label):
                    print(f"    {cs.caller.label} → {callee.label}")

        # ── Summary ──
        total_time = time.perf_counter() - t0
        _print_header("Summary")
        print(f"  Language        : {args.language}")
        print(f"  Source files    : {len(project_files)}")
        print(f"  Modules linked  : {len(linked.modules)}")
        print(f"  IR instructions : {len(linked.merged_ir)}")
        print(f"  CFG blocks      : {len(linked.merged_cfg.blocks)}")
        print(f"  Functions       : {len(linked.merged_registry.func_params)}")
        print(f"  LLM calls       : 0 (fully deterministic)")
        print(f"  Total time      : {total_time * 1000:.1f}ms")
        print()


if __name__ == "__main__":
    main()
