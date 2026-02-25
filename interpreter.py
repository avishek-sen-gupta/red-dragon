#!/usr/bin/env python3
"""LLM Symbolic Interpreter — CLI entry point."""

from __future__ import annotations

import argparse
import json

from interpreter.parser import Parser, TreeSitterParserFactory
from interpreter.frontend import get_frontend
from interpreter.cfg import build_cfg
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
        "--frontend",
        "-f",
        default=constants.FRONTEND_DETERMINISTIC,
        choices=[constants.FRONTEND_DETERMINISTIC, constants.FRONTEND_LLM],
        help="Frontend type: deterministic (tree-sitter) or llm (default: deterministic)",
    )

    args = parser.parse_args()

    if not args.file:
        # Demo mode: use a built-in example
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

    # Parse & lower
    if args.frontend == constants.FRONTEND_LLM:
        frontend = get_frontend(
            args.language,
            frontend_type=constants.FRONTEND_LLM,
            llm_provider=args.backend,
        )
        instructions = frontend.lower(None, source.encode("utf-8"))
    else:
        tree = Parser(TreeSitterParserFactory()).parse(source, args.language)
        frontend = get_frontend(args.language)
        instructions = frontend.lower(tree, source.encode("utf-8"))

    if args.ir_only:
        print("═══ IR ═══")
        for inst in instructions:
            print(f"  {inst}")
        return

    cfg = build_cfg(instructions)

    if args.cfg_only:
        print("═══ CFG ═══")
        print(cfg)
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
