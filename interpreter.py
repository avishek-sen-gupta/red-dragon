#!/usr/bin/env python3
"""LLM Symbolic Interpreter — CLI entry point."""

from __future__ import annotations

import argparse
import json
import time

from interpreter import constants
from interpreter.cli_output import emit
from interpreter.default_builtins import DEFAULT_BUILTINS
from interpreter.func_name import FuncName
from interpreter.hlasm.bfp_builtins import bfp_builtins
from interpreter.hlasm.clock_builtins import clock_builtins
from interpreter.hlasm.dfp_builtins import dfp_builtins
from interpreter.hlasm.hfp_builtins import hfp_builtins
from interpreter.hlasm.pfpo_builtins import pfpo_builtins
from interpreter.hlasm.system_machine_clock import SystemMachineClock
from interpreter.project.entry_point import EntryPoint
from interpreter.run import run
from interpreter.vm.builtins import compose_builtins


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
        emit("No file provided. Using built-in demo:\n")
        emit(source)
    else:
        with open(args.file) as f:
            source = f.read()

    # Full run
    entry = (
        EntryPoint.function(lambda f, _name=FuncName(args.entry): f.name == _name)
        if args.entry
        else EntryPoint.top_level()
    )
    vm = run(
        source,
        language=args.language,
        entry_point=entry,
        backend=args.backend,
        max_steps=args.max_steps,
        verbose=args.verbose,
        frontend_type=args.frontend,
        builtins=compose_builtins(
            DEFAULT_BUILTINS,
            clock_builtins(
                SystemMachineClock(wall_ns=time.time_ns, cpu_ns=time.process_time_ns)
            ),
            bfp_builtins(),
            hfp_builtins(),
            dfp_builtins(),
            pfpo_builtins(),
        ),
    )

    emit("\n═══ Final VM State ═══")
    emit(json.dumps(vm.to_dict(), indent=2, default=str))


if __name__ == "__main__":
    main()
