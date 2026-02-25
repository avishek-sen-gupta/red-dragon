#!/usr/bin/env python3
"""Demo: Chunked LLM frontend IR lowering on a multi-construct Python file.

Exercises the full chunking pipeline:
  1. tree-sitter decomposes source into top-level chunks
  2. Each chunk is lowered to IR independently via the LLM
  3. Registers and labels are renumbered to avoid collisions
  4. Results are reassembled into a single IR stream

Usage:
    poetry run python scripts/run_chunked_demo.py
    poetry run python scripts/run_chunked_demo.py --backend ollama
    poetry run python scripts/run_chunked_demo.py --verbose
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure repo root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from interpreter import constants
from interpreter.cfg import build_cfg
from interpreter.chunked_llm_frontend import ChunkedLLMFrontend, ChunkExtractor
from interpreter.frontend import get_frontend
from interpreter.parser import Parser, TreeSitterParserFactory

SAMPLE_SOURCE = """\
class Account:
    def __init__(self, owner, balance):
        self.owner = owner
        self.balance = balance
        self.history = []

    def deposit(self, amount):
        if amount <= 0:
            return False
        self.balance = self.balance + amount
        self.history.append(amount)
        return True

    def withdraw(self, amount):
        if amount <= 0:
            return False
        if amount > self.balance:
            return False
        self.balance = self.balance - amount
        self.history.append(-amount)
        return True

    def summary(self):
        return self.owner + ": " + str(self.balance)


def transfer(source, dest, amount):
    ok = source.withdraw(amount)
    if ok:
        dest.deposit(amount)
        return True
    return False


def batch_transfer(pairs):
    successes = 0
    i = 0
    while i < len(pairs):
        pair = pairs[i]
        result = transfer(pair[0], pair[1], pair[2])
        if result:
            successes = successes + 1
        i = i + 1
    return successes


alice = Account("Alice", 1000)
bob = Account("Bob", 500)

transfer(alice, bob, 200)

pairs = [[alice, bob, 100], [bob, alice, 50]]
n = batch_transfer(pairs)

a_summary = alice.summary()
b_summary = bob.summary()
"""

LANGUAGE = "python"


def _print_header(title: str):
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}\n")


def _print_chunks(source: str):
    """Show what the chunker extracts before any LLM calls."""
    parser = Parser(TreeSitterParserFactory())
    tree = parser.parse(source, LANGUAGE)
    extractor = ChunkExtractor()
    chunks = extractor.extract_chunks(tree, source.encode(), LANGUAGE)

    print(f"Extracted {len(chunks)} chunks:\n")
    for i, chunk in enumerate(chunks):
        lines = chunk.source_text.count("\n") + 1
        preview = chunk.source_text[:80].replace("\n", " \\ ")
        if len(chunk.source_text) > 80:
            preview += "..."
        print(
            f"  [{i}] {chunk.chunk_type:<12} {chunk.name:<20} "
            f"{lines:>3} lines  (start line {chunk.start_line})"
        )
        print(f"      {preview}")
    print()
    return chunks


def _lower_and_print(backend: str, show_cfg: bool):
    """Run the full chunked lowering pipeline and print results."""
    frontend = get_frontend(
        LANGUAGE,
        frontend_type=constants.FRONTEND_CHUNKED_LLM,
        llm_provider=backend,
    )

    source_bytes = SAMPLE_SOURCE.encode("utf-8")

    t0 = time.perf_counter()
    instructions = frontend.lower(None, source_bytes)
    elapsed = time.perf_counter() - t0

    _print_header("IR Output")
    for inst in instructions:
        print(f"  {inst}")

    # Collect stats
    registers = {inst.result_reg for inst in instructions if inst.result_reg}
    labels = {
        inst.label
        for inst in instructions
        if inst.label and inst.opcode.value == "LABEL"
    }
    symbolics = [inst for inst in instructions if inst.opcode.value == "SYMBOLIC"]
    errors = [
        s for s in symbolics if any("chunk_error:" in str(op) for op in s.operands)
    ]

    _print_header("Summary")
    print(f"  Total IR instructions : {len(instructions)}")
    print(f"  Unique registers      : {len(registers)}")
    print(f"  Labels                : {len(labels)}")
    print(f"  SYMBOLIC params       : {len(symbolics) - len(errors)}")
    print(f"  Chunk errors          : {len(errors)}")
    print(f"  Lowering time         : {elapsed:.2f}s")

    if show_cfg:
        _print_header("CFG")
        cfg = build_cfg(instructions)
        print(cfg)
        print(f"\n  Basic blocks: {len(cfg.blocks)}")


def main():
    parser = argparse.ArgumentParser(description="Chunked LLM frontend demo")
    parser.add_argument(
        "--backend",
        "-b",
        default="claude",
        choices=["claude", "openai", "ollama", "huggingface"],
        help="LLM backend (default: claude)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug logging and show CFG",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    _print_header("Source")
    for i, line in enumerate(SAMPLE_SOURCE.splitlines(), 1):
        print(f"  {i:3d} | {line}")

    _print_header("Chunk Extraction (local, no LLM)")
    _print_chunks(SAMPLE_SOURCE)

    _print_header(f"Lowering via Chunked LLM Frontend (backend={args.backend})")
    _lower_and_print(args.backend, show_cfg=args.verbose)


if __name__ == "__main__":
    main()
