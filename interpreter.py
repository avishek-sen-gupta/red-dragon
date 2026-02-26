#!/usr/bin/env python3
"""LLM Symbolic Interpreter — CLI entry point."""

from __future__ import annotations

import argparse
import json

from interpreter.api import (
    lower_source,
    dump_ir,
    build_cfg_from_source,
    dump_cfg,
    dump_mermaid,
)
from interpreter.run import run
from interpreter import constants


def main():
    parser = argparse.ArgumentParser(description="LLM Symbolic Interpreter")
    parser.add_argument("file", nargs="?", help="Source file to interpret")
    parser.add_argument(
        "--language", "-l", default="python", help="Source language (default: python)"
    )
    parser.add_argument(
        "--entry", "-e", default="", help="Entry point label or function name"
    )
    parser.add_argument(
        "--backend",
        "-b",
        default="claude",
        choices=["claude", "openai", "ollama", "huggingface"],
        help="LLM backend (default: claude)",
    )
    parser.add_argument(
        "--max-steps",
        "-n",
        type=int,
        default=100,
        help="Maximum interpretation steps (default: 100)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print IR, CFG, and step-by-step execution",
    )
    parser.add_argument(
        "--ir-only", action="store_true", help="Only print the IR (no LLM execution)"
    )
    parser.add_argument(
        "--cfg-only", action="store_true", help="Only print the CFG (no LLM execution)"
    )
    parser.add_argument(
        "--mermaid",
        action="store_true",
        help="Output CFG as a Mermaid flowchart diagram",
    )
    parser.add_argument(
        "--function",
        default="",
        help="Extract CFG for a single function (use with --mermaid or --cfg-only)",
    )
    parser.add_argument(
        "--frontend",
        "-f",
        default=constants.FRONTEND_DETERMINISTIC,
        choices=[
            constants.FRONTEND_DETERMINISTIC,
            constants.FRONTEND_LLM,
            constants.FRONTEND_CHUNKED_LLM,
        ],
        help="Frontend type: deterministic, llm, or chunked_llm (default: deterministic)",
    )

    args = parser.parse_args()

    if not args.file:
        source = """\
def factorial(n):
    if n <= 1:
        return 1
    else:
        return n * factorial(n - 1)

result = factorial(5)
"""
        print("No file provided. Using built-in demo:\n")
        print(source)
    else:
        with open(args.file) as f:
            source = f.read()

    if args.ir_only:
        print("═══ IR ═══")
        print(dump_ir(source, args.language, args.frontend, args.backend))
        return

    if args.mermaid:
        print(
            dump_mermaid(
                source, args.language, args.frontend, args.backend, args.function
            )
        )
        return

    if args.cfg_only:
        print("═══ CFG ═══")
        print(
            dump_cfg(source, args.language, args.frontend, args.backend, args.function)
        )
        return

    # Full run
    vm = run(
        source,
        language=args.language,
        entry_point=args.entry,
        backend=args.backend,
        max_steps=args.max_steps,
        verbose=args.verbose,
        frontend_type=args.frontend,
    )

    print("\n═══ Final VM State ═══")
    print(json.dumps(vm.to_dict(), indent=2, default=str))


if __name__ == "__main__":
    main()
