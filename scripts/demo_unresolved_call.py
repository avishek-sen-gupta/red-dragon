"""Demo: compare symbolic vs LLM-plausible resolution of unresolved function calls."""

from interpreter.constants import Language
from interpreter.project.entry_point import EntryPoint
from interpreter.run import run
from interpreter.run_types import UnresolvedCallStrategy
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm_types import SymbolicValue
from interpreter.cli_output import emit

SOURCE = """\
import math

x = math.sqrt(16)
y = x + 1
z = math.floor(7.8)
"""


def _format_val(v):
    if isinstance(v, TypedValue):
        return _format_val(v.value)
    if isinstance(v, SymbolicValue):
        return (
            f"SymbolicValue({v.name}, hint={v.type_hint}, constraints={v.constraints})"
        )
    return repr(v)


def _show_vars(vm):
    frame = vm.call_stack[0]
    for name, val in sorted(frame.local_vars.items()):
        emit(f"    {name} = {_format_val(val)}")


def main():
    emit("=" * 60)
    emit("SOURCE:")
    emit(SOURCE)

    emit("=" * 60)
    emit("MODE 1: symbolic (default)")
    emit("=" * 60)
    vm_sym = run(
        SOURCE,
        language=Language.PYTHON,
        verbose=True,
        unresolved_call_strategy=UnresolvedCallStrategy.SYMBOLIC,
        entry_point=EntryPoint.top_level(),
    )
    emit("\nFinal variables:")
    _show_vars(vm_sym)

    emit()
    emit("=" * 60)
    emit("MODE 2: llm (plausible values)")
    emit("=" * 60)
    vm_llm = run(
        SOURCE,
        language=Language.PYTHON,
        verbose=True,
        unresolved_call_strategy=UnresolvedCallStrategy.LLM,
        entry_point=EntryPoint.top_level(),
    )
    emit("\nFinal variables:")
    _show_vars(vm_llm)


if __name__ == "__main__":
    main()
