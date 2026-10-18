"""Tests for FUNCTION CHAR and ORD as IR, over the native (EBCDIC) collating sequence."""

from interpreter.cobol.byte_builtins import BYTE_BUILTINS
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.ordinal_function_ir import emit_char, emit_ord
from interpreter.func_name import FuncName
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import covers
from tests.unit.cobol.emitted_ir import ParamValue, run_emitted


def _char(n: ParamValue) -> ParamValue:
    return run_emitted(emit_char, (n,))


def _ord(c: ParamValue) -> ParamValue:
    return run_emitted(emit_ord, (c,))


def _uncomputable(value: ParamValue) -> bool:
    return isinstance(value, SymbolicValue)


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_char_is_the_character_at_a_native_position_counted_from_one():
    assert (
        _char("194"),
        _char("241"),
        _uncomputable(_char("0")),
        _uncomputable(_char("257")),
        _uncomputable(_char(SymbolicValue("n"))),
        FuncName("__char") in BYTE_BUILTINS,
    ) == ("A", "0", True, True, True, False)


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_ord_is_a_characters_native_position_and_inverts_char():
    assert (
        _ord("A"),
        _ord("0"),
        _ord(_char("194")),
        _uncomputable(_ord(SymbolicValue("c"))),
        FuncName("__ord_char") in BYTE_BUILTINS,
    ) == (194, 241, 194, True, False)
