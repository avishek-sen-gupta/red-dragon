"""Each run resolves builtin calls through the table it is given."""

from __future__ import annotations

import pytest

from interpreter.cfg import build_cfg
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.func_name import FuncName
from interpreter.project.entry_point import EntryPoint
from interpreter.project.types import LinkedProgram
from interpreter.registry import build_registry
from interpreter.run import (
    Completed,
    initial_vm_state,
    run,
    run_linked,
    run_linked_resumable,
    run_linked_traced,
)
from interpreter.types.typed_value import TypedValue
from interpreter.var_name import VarName
from interpreter.vm.builtin import Builtin
from interpreter.vm.builtins import compose_builtins, core_builtins
from interpreter.vm.duplicate_builtin_error import DuplicateBuiltinError
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import BuiltinResult
from tests.covers import NotLanguageFeature, covers


def _linked(source: str) -> LinkedProgram:
    frontend = get_frontend(Language.PYTHON)
    instructions = frontend.lower(source.encode("utf-8"))
    cfg = build_cfg(instructions)
    registry = build_registry(
        instructions,
        cfg,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )
    return LinkedProgram(
        modules={},
        merged_ir=list(instructions),
        merged_cfg=cfg,
        merged_registry=registry,
        language=Language.PYTHON,
        import_graph={},
        type_env_builder=frontend.type_env_builder,
        symbol_table=frontend.symbol_table,
        func_symbol_table=frontend.func_symbol_table,
        class_symbol_table=frontend.class_symbol_table,
    )


def _tenfold(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    return BuiltinResult(value=args[0].value * 10)


def _halved(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    return BuiltinResult(value=args[0].value // 2)


def _shout(fn: Builtin):
    return compose_builtins(core_builtins(), {FuncName("shout"): fn})


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_each_run_resolves_builtins_through_its_own_table():
    source = "x = shout(6)\n"
    linked = _linked(source)
    top = EntryPoint.top_level()

    def ran(fn: Builtin) -> object:
        vm = run_linked(linked, top, builtins=_shout(fn), initial_vm=initial_vm_state())
        return vm.current_frame.local_vars[VarName("x")].value

    traced, _trace = run_linked_traced(linked, top, builtins=_shout(_halved))
    resumed = run_linked_resumable(
        linked, top, builtins=_shout(_tenfold), initial_vm=initial_vm_state()
    )
    assert isinstance(resumed, Completed)
    unknown = run_linked(
        linked, top, builtins=core_builtins(), initial_vm=initial_vm_state()
    )
    assert (
        ran(_tenfold),
        ran(_halved),
        traced.current_frame.local_vars[VarName("x")].value,
        resumed.vm.current_frame.local_vars[VarName("x")].value,
        type(unknown.current_frame.local_vars[VarName("x")].value).__name__,
        run(source, builtins=_shout(_tenfold))
        .current_frame.local_vars[VarName("x")]
        .value,
        type(run(source).current_frame.local_vars[VarName("x")].value).__name__,
    ) == (60, 3, 3, 60, "SymbolicValue", 60, "SymbolicValue")


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_composing_tables_keeps_every_entry_and_refuses_a_shared_name():
    composed = compose_builtins({FuncName("a"): _tenfold}, {FuncName("b"): _halved}, {})
    assert dict(composed) == {FuncName("a"): _tenfold, FuncName("b"): _halved}
    with pytest.raises(DuplicateBuiltinError) as raised:
        compose_builtins(core_builtins(), {FuncName("len"): _tenfold})
    assert raised.value.name == FuncName("len")
    assert str(raised.value) == "two builtins tables both define len"
