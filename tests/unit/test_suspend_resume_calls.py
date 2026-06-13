"""Suspend/resume across NESTED CALLs.

A Suspend reached while several call frames are live must capture the entire
nested context (every frame's registers, locals, and return point live in
vm.call_stack), and resume must continue and unwind the returns correctly — even
after the continuation has been serialized and the pipeline rebuilt from scratch.
"""

from __future__ import annotations

import pickle

from interpreter import constants
from interpreter.cfg import build_cfg
from interpreter.func_name import FuncName
from interpreter.ir import Opcode, CodeLabel
from interpreter.refs.func_ref import BoundFuncRef, FuncRef
from interpreter.register import Register
from interpreter.registry import build_registry
from interpreter.run import Completed, Suspended, resume, run_resumable
from interpreter.types.type_expr import UNKNOWN
from interpreter.types.typed_value import typed, unwrap
from interpreter.var_name import VarName
from interpreter.vm.vm_types import StackFrame, VMState
from tests.unit.cfg_helpers import make_instructions


def _result(vm) -> int:
    return unwrap(vm.current_frame.local_vars[VarName("result")])


def _func_symbols(*names: str):
    return {
        CodeLabel(f"func_{n}_0"): FuncRef(
            name=FuncName(n), label=CodeLabel(f"func_{n}_0")
        )
        for n in names
    }


def _vm_with_callables(*names: str) -> VMState:
    """A fresh VM whose main frame can resolve each callable by name."""
    vm = VMState()
    locals_ = {
        VarName(n): typed(
            BoundFuncRef(func_ref=FuncRef(FuncName(n), CodeLabel(f"func_{n}_0"))),
            UNKNOWN,
        )
        for n in names
    }
    vm.call_stack.append(
        StackFrame(
            function_name=FuncName(constants.MAIN_FRAME_NAME), local_vars=locals_
        )
    )
    return vm


# main: a=100; r = sub(); result = r + a; return       (a persists across the call)
# sub: yield 7; return injected
_ONE_LEVEL = make_instructions(
    (Opcode.LABEL, {"label": CodeLabel("entry")}),
    (Opcode.CONST, {"result_reg": Register("%0"), "operands": [100]}),
    (Opcode.STORE_VAR, {"operands": ["a", "%0"]}),
    (Opcode.CALL_FUNCTION, {"result_reg": Register("%1"), "operands": ["sub"]}),
    (Opcode.LOAD_VAR, {"result_reg": Register("%2"), "operands": ["a"]}),
    (Opcode.BINOP, {"result_reg": Register("%3"), "operands": ["+", "%1", "%2"]}),
    (Opcode.STORE_VAR, {"operands": ["result", "%3"]}),
    (Opcode.RETURN, {"operands": ["%3"]}),
    (Opcode.LABEL, {"label": CodeLabel("func_sub_0")}),
    (Opcode.CONST, {"result_reg": Register("%10"), "operands": [7]}),
    (Opcode.SUSPEND, {"result_reg": Register("%11"), "operands": ["%10"]}),
    (Opcode.RETURN, {"operands": ["%11"]}),
)


def test_suspend_resume_inside_nested_call():
    cfg = build_cfg(_ONE_LEVEL)
    registry = build_registry(_ONE_LEVEL, cfg, func_symbol_table=_func_symbols("sub"))

    out = run_resumable(cfg, "entry", registry, vm=_vm_with_callables("sub"))
    assert isinstance(out, Suspended)
    assert out.value == 7
    # Suspended INSIDE the call: both frames (main + sub) are captured.
    assert len(out.state.vm.call_stack) == 2

    done = resume(cfg, registry, out.state, 50)  # sub resumes with 50
    assert isinstance(done, Completed)
    # sub returned 50 to main; main added its persisted a=100 → 150.
    assert _result(done.vm) == 150


def test_nested_call_resume_from_scratch():
    cfg1 = build_cfg(_ONE_LEVEL)
    reg1 = build_registry(_ONE_LEVEL, cfg1, func_symbol_table=_func_symbols("sub"))
    out = run_resumable(cfg1, "entry", reg1, vm=_vm_with_callables("sub"))
    assert isinstance(out, Suspended) and len(out.state.vm.call_stack) == 2

    # Serialize the 2-frame continuation; rebuild the whole pipeline; resume.
    # (trusted, self-generated pickle data.)
    blob = pickle.dumps(out.state)
    del cfg1, reg1, out

    cfg2 = build_cfg(_ONE_LEVEL)
    reg2 = build_registry(_ONE_LEVEL, cfg2, func_symbol_table=_func_symbols("sub"))
    done = resume(cfg2, reg2, pickle.loads(blob), 50)
    assert isinstance(done, Completed)
    assert _result(done.vm) == 150


# main: b=1000; r = sub(); result = r + b; return
# sub:  c=200;  r2 = subsub(); return r2 + c
# subsub: yield 7; return injected
_TWO_LEVELS = make_instructions(
    (Opcode.LABEL, {"label": CodeLabel("entry")}),
    (Opcode.CONST, {"result_reg": Register("%0"), "operands": [1000]}),
    (Opcode.STORE_VAR, {"operands": ["b", "%0"]}),
    (Opcode.CALL_FUNCTION, {"result_reg": Register("%1"), "operands": ["sub"]}),
    (Opcode.LOAD_VAR, {"result_reg": Register("%2"), "operands": ["b"]}),
    (Opcode.BINOP, {"result_reg": Register("%3"), "operands": ["+", "%1", "%2"]}),
    (Opcode.STORE_VAR, {"operands": ["result", "%3"]}),
    (Opcode.RETURN, {"operands": ["%3"]}),
    (Opcode.LABEL, {"label": CodeLabel("func_sub_0")}),
    (Opcode.CONST, {"result_reg": Register("%10"), "operands": [200]}),
    (Opcode.STORE_VAR, {"operands": ["c", "%10"]}),
    (Opcode.CALL_FUNCTION, {"result_reg": Register("%11"), "operands": ["subsub"]}),
    (Opcode.LOAD_VAR, {"result_reg": Register("%12"), "operands": ["c"]}),
    (Opcode.BINOP, {"result_reg": Register("%13"), "operands": ["+", "%11", "%12"]}),
    (Opcode.RETURN, {"operands": ["%13"]}),
    (Opcode.LABEL, {"label": CodeLabel("func_subsub_0")}),
    (Opcode.CONST, {"result_reg": Register("%20"), "operands": [7]}),
    (Opcode.SUSPEND, {"result_reg": Register("%21"), "operands": ["%20"]}),
    (Opcode.RETURN, {"operands": ["%21"]}),
)


def test_suspend_resume_two_levels_deep():
    cfg = build_cfg(_TWO_LEVELS)
    registry = build_registry(
        _TWO_LEVELS, cfg, func_symbol_table=_func_symbols("sub", "subsub")
    )

    out = run_resumable(cfg, "entry", registry, vm=_vm_with_callables("sub", "subsub"))
    assert isinstance(out, Suspended)
    assert out.value == 7
    # main + sub + subsub all live on the stack at the suspend.
    assert len(out.state.vm.call_stack) == 3

    done = resume(cfg, registry, out.state, 5)
    assert isinstance(done, Completed)
    # subsub returns 5 → sub adds c=200 → 205 → main adds b=1000 → 1205.
    assert _result(done.vm) == 1205
