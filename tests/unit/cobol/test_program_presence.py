"""__cobol_program_present: whether a CALL's entry variable names a function
bound anywhere on the call stack."""

from __future__ import annotations

from interpreter.cobol.byte_builtins import BYTE_BUILTINS
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.features import CobolFeature
from interpreter.func_name import FuncName
from interpreter.ir import CodeLabel
from interpreter.refs.func_ref import BoundFuncRef, FuncRef
from interpreter.types.typed_value import typed_from_runtime
from interpreter.var_name import VarName
from interpreter.vm.vm_types import StackFrame, VMState
from tests.covers import covers


@covers(CobolFeature.CALL)
def test_only_a_bound_function_counts_as_present() -> None:
    entry = BoundFuncRef(
        func_ref=FuncRef(name=FuncName("subp"), label=CodeLabel("func_subp_0"))
    )
    vm = VMState(
        call_stack=[
            StackFrame(
                function_name=FuncName("main"),
                local_vars={
                    VarName("__entry_SUBP"): typed_from_runtime(entry),
                    VarName("__entry_TEXT"): typed_from_runtime("not a function"),
                },
            )
        ]
    )
    present = BYTE_BUILTINS[FuncName(BuiltinName.PROGRAM_PRESENT)]
    assert [
        present([typed_from_runtime(name)], vm).value
        for name in ("__entry_SUBP", "__entry_TEXT", "__entry_NONE")
    ] == [True, False, False]
