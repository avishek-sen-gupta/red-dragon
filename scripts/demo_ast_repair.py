#!/usr/bin/env python3
"""Demo: LLM-assisted AST repair for malformed source code.

Exercises the RepairingFrontendDecorator with a real LLM call:
  1. Shows the broken source and the tree-sitter parse errors
  2. Runs the repair loop (LLM fixes syntax → re-parse → deterministic lowering)
  3. Compares IR output with vs. without repair

Usage:
    poetry run python scripts/demo_ast_repair.py
    poetry run python scripts/demo_ast_repair.py --backend ollama
    poetry run python scripts/demo_ast_repair.py --language javascript
    poetry run python scripts/demo_ast_repair.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interpreter.ast_repair.error_span_extractor import extract
from interpreter.ast_repair.repair_config import RepairConfig
from interpreter.ast_repair.repairing_frontend_decorator import (
    RepairingFrontendDecorator,
)
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.ir import Opcode
from interpreter.llm_client import get_llm_client
from interpreter.parser import TreeSitterParserFactory

BROKEN_SAMPLES: dict[Language, bytes] = {
    Language.PYTHON: b"""\
import math

def calculate_area(radius:
    return math.pi * radius ** 2

def greet(name
    message = f"Hello, {name}!"
    print(message)

result = calculate_area(5)
greeting = greet("World")
""",
    Language.JAVASCRIPT: b"""\
function fibonacci(n {
  if (n <= 1) return n;
  return fibonacci(n - 1) + fibonacci(n - 2)

const result = fibonacci(10;
console.log(result);
""",
}

logger = logging.getLogger(__name__)


def _print_header(title: str):
    width = 68
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}\n")


def _show_source(source: bytes):
    for i, line in enumerate(source.decode("utf-8", errors="replace").splitlines(), 1):
        print(f"  {i:3d} | {line}")


def _show_errors(language: Language, source: bytes):
    parser = TreeSitterParserFactory().get_parser(language)
    tree = parser.parse(source)
    spans = extract(tree.root_node, source, context_lines=2)
    print(f"  tree-sitter has_error: {tree.root_node.has_error}")
    print(f"  Error spans found: {len(spans)}")
    for i, span in enumerate(spans, 1):
        print(f"\n  Span {i} (lines {span.start_line + 1}-{span.end_line + 1}):")
        for line in span.error_text.splitlines():
            print(f"    > {line}")


def _count_symbolics(instructions):
    return sum(
        1
        for inst in instructions
        if inst.opcode == Opcode.SYMBOLIC
        and any("unsupported:" in str(op) for op in inst.operands)
    )


def main():
    parser = argparse.ArgumentParser(
        description="Demo: LLM-assisted AST repair for malformed source"
    )
    parser.add_argument(
        "--backend",
        "-b",
        default="claude",
        choices=["claude", "openai", "ollama", "huggingface"],
        help="LLM provider for repair (default: claude)",
    )
    parser.add_argument(
        "--language",
        "-l",
        default="python",
        choices=list(BROKEN_SAMPLES.keys()),
        help="Language to demo (default: python)",
    )
    parser.add_argument(
        "--max-retries",
        "-r",
        type=int,
        default=3,
        help="Max repair attempts (default: 3)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    language = Language(args.language)
    source = BROKEN_SAMPLES[language]

    # ── Show broken source ──
    _print_header(f"Broken {language.value.title()} Source")
    _show_source(source)

    # ── Show parse errors ──
    _print_header("Tree-Sitter Parse Errors")
    _show_errors(language, source)

    # ── Phase 1: Without repair (baseline) ──
    _print_header("Phase 1: Deterministic Lowering WITHOUT Repair")
    plain_frontend = get_frontend(language)
    t0 = time.perf_counter()
    plain_ir = plain_frontend.lower(source)
    t_plain = time.perf_counter() - t0
    plain_symbolics = _count_symbolics(plain_ir)
    print(f"  IR instructions: {len(plain_ir)}")
    print(f"  SYMBOLIC (unsupported:*): {plain_symbolics}")
    print(f"  Time: {t_plain:.3f}s")

    # ── Phase 2: With LLM repair ──
    _print_header(
        f"Phase 2: Deterministic Lowering WITH LLM Repair (backend={args.backend})"
    )
    repair_client = get_llm_client(provider=args.backend)
    config = RepairConfig(max_retries=args.max_retries, context_lines=3)
    repair_frontend = RepairingFrontendDecorator(
        inner_frontend=get_frontend(language),
        llm_client=repair_client,
        parser_factory=TreeSitterParserFactory(),
        language=language,
        config=config,
    )

    print(f"  Repairing with max {args.max_retries} attempts...")
    t0 = time.perf_counter()
    repaired_ir = repair_frontend.lower(source)
    t_repair = time.perf_counter() - t0
    repaired_symbolics = _count_symbolics(repaired_ir)
    print(f"  IR instructions: {len(repaired_ir)}")
    print(f"  SYMBOLIC (unsupported:*): {repaired_symbolics}")
    print(f"  Time: {t_repair:.3f}s")

    # ── Show repaired source ──
    repaired_source = repair_frontend.last_lowered_source
    _print_header("Repaired Source")
    if repaired_source == source:
        print("  (Repair failed — original source was used as fallback)")
    else:
        print("  (LLM-repaired source that was lowered deterministically)")
    print()
    _show_source(repaired_source)

    # ── Show repaired IR ──
    _print_header("Repaired IR")
    for inst in repaired_ir:
        print(f"  {inst}")

    # ── Summary ──
    _print_header("Summary")
    print(f"  Without repair: {plain_symbolics} unsupported SYMBOLIC instruction(s)")
    print(f"  With repair:    {repaired_symbolics} unsupported SYMBOLIC instruction(s)")
    improvement = plain_symbolics - repaired_symbolics
    if improvement > 0:
        print(f"  Improvement:    {improvement} fewer SYMBOLIC instruction(s)")
    elif improvement == 0:
        print(
            f"  Improvement:    No change (repair may not have been needed or failed)"
        )
    else:
        print(
            f"  Note:           Repair introduced {-improvement} additional SYMBOLIC instruction(s)"
        )
    print(f"\n  Plain frontend time:  {t_plain:.3f}s")
    print(f"  Repair frontend time: {t_repair:.3f}s")


if __name__ == "__main__":
    main()
