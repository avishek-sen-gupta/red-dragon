"""Whether a CALLed program's entry variable is bound in the run unit."""

from __future__ import annotations

from collections.abc import Sequence

from interpreter.refs.func_ref import BoundFuncRef
from interpreter.types.typed_value import TypedValue
from interpreter.var_name import VarName
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult


def program_present(args: Sequence[TypedValue], vm: VMState) -> BuiltinResult:
    entry = VarName(str(args[0].value))
    return BuiltinResult(
        value=any(
            isinstance(frame.local_vars[entry].value, BoundFuncRef)
            for frame in vm.call_stack
            if entry in frame.local_vars
        )
    )
