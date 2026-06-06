"""Unit tests for CICS system service builtins."""

from tests.covers import covers, NotLanguageFeature
from interpreter.cics.builtins.system import (
    make_assign_builtin,
    make_asktime_builtin,
    make_writeq_td_builtin,
    make_handle_abend_builtin,
    make_abend_builtin,
    make_inquire_builtin,
)
from interpreter.cics.types import DispatchKind, DispatchResult
from interpreter.vm.vm_types import VMState, BuiltinResult
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import UNKNOWN


def _vm() -> VMState:
    return VMState()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_assign_builtin_is_callable():
    builtin = make_assign_builtin(applid="CARDDEMO", sysid="SYS1")
    result = builtin([], _vm())
    assert isinstance(result, BuiltinResult)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_asktime_builtin_returns_positive_integer():
    builtin = make_asktime_builtin()
    result = builtin([], _vm())
    assert isinstance(result, BuiltinResult)
    assert isinstance(result.value, int)
    assert result.value > 0


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_writeq_td_appends_to_queue():
    queue: list[str] = []
    builtin = make_writeq_td_builtin(queue)
    args = [typed("SOME DATA", UNKNOWN), typed("CSMT", UNKNOWN)]
    builtin(args, _vm())
    assert len(queue) == 1
    assert "SOME DATA" in queue[0]
    assert "CSMT" in queue[0]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_handle_abend_is_noop():
    builtin = make_handle_abend_builtin()
    result = builtin([], _vm())
    assert isinstance(result, BuiltinResult)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_abend_builtin_sets_dispatch_result():
    holder: list[DispatchResult | None] = [None]
    builtin = make_abend_builtin(holder)
    args = [typed("CICS", UNKNOWN)]
    builtin(args, _vm())
    assert holder[0] is not None
    assert holder[0].kind == DispatchKind.ABEND
    assert holder[0].abcode == "CICS"


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inquire_program_found():
    cache = {"COSGN00C": object()}
    builtin = make_inquire_builtin(cache)
    args = [typed("COSGN00C", UNKNOWN)]
    result = builtin(args, _vm())
    assert isinstance(result, BuiltinResult)
    assert result.value == 0  # NORMAL


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inquire_program_not_found():
    cache: dict = {}
    builtin = make_inquire_builtin(cache)
    args = [typed("MISSING", UNKNOWN)]
    result = builtin(args, _vm())
    assert result.value == 27  # PGMIDERR
