#!/usr/bin/env python3
"""Demo: dataflow analysis on complexly-dependent variables with graph visualisation.

Runs the deterministic frontend on Python source with diamond dependencies,
transitive chains, and function calls, then performs reaching-definitions
analysis and renders the variable dependency graph as a Mermaid flowchart.

Usage:
    poetry run python scripts/demo_dataflow.py
    poetry run python scripts/demo_dataflow.py --verbose
    poetry run python scripts/demo_dataflow.py --output graph.md
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interpreter.cfg import build_cfg
from interpreter.constants import Language
from interpreter.dataflow import analyze
from interpreter.frontend import get_frontend

logger = logging.getLogger(__name__)

# Source with complex variable dependencies:
#   - linear chains (a → b → c)
#   - diamond patterns (a,b → c; a,b → d; c,d → e)
#   - function calls creating transitive deps
#   - multi-operand expressions (total = h + e + b)
SAMPLE_SOURCE = """\
a = 1
b = 2
c = a + b
d = a * b
e = c + d
f = e - a

def square(x):
    return x * x

g = square(c)
h = g + f
total = h + e + b
"""


def _print_header(title: str):
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}\n")


def _render_dependency_mermaid(raw_graph: dict[str, set[str]]) -> str:
    """Convert a raw (direct) dependency graph to a Mermaid flowchart."""
    lines = ["flowchart BT"]
    all_vars = sorted(
        raw_graph.keys() | {v for deps in raw_graph.values() for v in deps}
    )

    for var in all_vars:
        lines.append(f'    {var}["{var}"]')

    emitted: set[tuple[str, str]] = set()
    for var, deps in sorted(raw_graph.items()):
        for dep in sorted(deps):
            edge = (dep, var)
            if edge not in emitted:
                lines.append(f"    {dep} --> {var}")
                emitted.add(edge)

    return "\n".join(lines)


def _compute_depth(raw_graph: dict[str, set[str]]) -> dict[str, int]:
    """Compute the dependency depth of each variable (longest chain from a leaf)."""
    depths: dict[str, int] = {}

    def _depth(var: str, visiting: set[str]) -> int:
        if var in depths:
            return depths[var]
        if var in visiting:
            return 0
        visiting.add(var)
        direct = raw_graph.get(var, set())
        d = (
            (1 + max((_depth(dep, visiting) for dep in direct), default=-1))
            if direct
            else 0
        )
        depths[var] = d
        visiting.discard(var)
        return d

    for v in raw_graph:
        _depth(v, set())
    return depths


def main():
    parser = argparse.ArgumentParser(
        description="Dataflow analysis demo with dependency graph visualisation"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show IR instructions and CFG",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="",
        help="Write Mermaid dependency graph to a file",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    # ── Show source ──
    _print_header("Source (Python)")
    for i, line in enumerate(SAMPLE_SOURCE.strip().splitlines(), 1):
        print(f"  {i:3d} | {line}")

    # ── Phase 1: Lower to IR ──
    _print_header("Phase 1: Lower to IR (deterministic frontend)")
    frontend = get_frontend(Language.PYTHON)
    instructions = frontend.lower(SAMPLE_SOURCE.encode("utf-8"))
    print(f"  {len(instructions)} IR instructions")

    if args.verbose:
        print()
        for inst in instructions:
            print(f"    {inst}")

    # ── Phase 2: Build CFG ──
    _print_header("Phase 2: Build CFG")
    cfg = build_cfg(instructions)
    print(f"  {len(cfg.blocks)} basic blocks")

    if args.verbose:
        print()
        for label, block in cfg.blocks.items():
            print(f"    [{label}]  {len(block.instructions)} instructions")

    # ── Phase 3: Dataflow analysis ──
    _print_header("Phase 3: Dataflow Analysis")
    result = analyze(cfg)

    print(f"  Definitions found   : {len(result.definitions)}")
    print(f"  Def-use chains      : {len(result.def_use_chains)}")
    print(f"  Variables in graph  : {len(result.dependency_graph)}")

    # ── Phase 4: Dependency graphs ──
    raw = result.raw_dependency_graph
    transitive = result.dependency_graph

    _print_header("Phase 4a: Direct Dependencies")
    for var in sorted(raw.keys()):
        deps = sorted(raw[var])
        label = ", ".join(deps) if deps else "(leaf)"
        print(f"  {var} ← {label}")

    _print_header("Phase 4b: Transitive Dependencies")
    for var in sorted(transitive.keys()):
        deps = sorted(transitive[var])
        print(f"  {var} depends on: {', '.join(deps)}")

    # ── Dependency depth ──
    _print_header("Dependency Depth (longest chain from leaf)")
    depths = _compute_depth(raw)
    for var in sorted(depths.keys(), key=lambda v: (depths[v], v)):
        direct = sorted(raw.get(var, set()))
        direct_str = f" ← {', '.join(direct)}" if direct else " (leaf)"
        print(f"  depth {depths[var]}  {var}{direct_str}")

    # ── Mermaid visualisation ──
    _print_header("Mermaid Dependency Graph (paste into mermaid.live)")
    mermaid = _render_dependency_mermaid(raw)
    print(mermaid)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(f"```mermaid\n{mermaid}\n```\n")
        print(f"\n  Written to {output_path}")


if __name__ == "__main__":
    main()
