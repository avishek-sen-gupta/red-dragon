"""Demo: compare symbolic vs LLM-plausible resolution of unresolved function calls."""

import json
import sys

from interpreter.run import run
from interpreter.run_types import UnresolvedCallStrategy
from interpreter.vm_types import SymbolicValue, _serialize_value

SOURCE = """\
import math

x = math.sqrt(16)
y = x + 1
z = math.floor(7.8)
"""


def _format_val(v):
    if isinstance(v, SymbolicValue):
        return (
            f"SymbolicValue({v.name}, hint={v.type_hint}, constraints={v.constraints})"
        )
    return repr(v)


def _show_vars(vm):
    frame = vm.call_stack[0]
    for name, val in sorted(frame.local_vars.items()):
        print(f"    {name} = {_format_val(val)}")


def main():
    print("=" * 60)
    print("SOURCE:")
    print(SOURCE)

    print("=" * 60)
    print("MODE 1: symbolic (default)")
    print("=" * 60)
    vm_sym = run(
        SOURCE,
        language="python",
        verbose=True,
        unresolved_call_strategy=UnresolvedCallStrategy.SYMBOLIC,
    )
    print("\nFinal variables:")
    _show_vars(vm_sym)

    print()
    print("=" * 60)
    print("MODE 2: llm (plausible values)")
    print("=" * 60)
    vm_llm = run(
        SOURCE,
        language="python",
        verbose=True,
        unresolved_call_strategy=UnresolvedCallStrategy.LLM,
    )
    print("\nFinal variables:")
    _show_vars(vm_llm)


if __name__ == "__main__":
    main()
