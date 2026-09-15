"""__cobol_add/subtract/multiply/divide and __cobol_to_float builtins."""

from __future__ import annotations

from cobol_numeric.number import from_literal, to_plain_str
from interpreter.cobol.byte_builtins import BYTE_BUILTINS
from interpreter.cobol.cobol_constants import BuiltinName
from interpreter.cobol.features import CobolFeature
from interpreter.func_name import FuncName
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm import Operators
from tests.covers import covers


def _call(name: str, *values):
    builtin = BYTE_BUILTINS[FuncName(name)]
    return builtin([typed_from_runtime(v) for v in values], None).value


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_multiply_float_operand_is_converted_exactly():
    assert _call(BuiltinName.COBOL_MULTIPLY, 4.35, 100, 0) == 435


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_integer_results_come_back_as_int():
    result = _call(BuiltinName.COBOL_DIVIDE, 2023, 4, 0)
    assert result == 505 and isinstance(result, int)


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_fractional_results_are_exact():
    assert to_plain_str(_call(BuiltinName.COBOL_DIVIDE, 7, 2, 1)) == "3.5"
    assert to_plain_str(_call(BuiltinName.COBOL_ADD, "0.1", 0.7, 2)) == "0.80"
    assert (
        to_plain_str(_call(BuiltinName.COBOL_SUBTRACT, from_literal("1.00"), 3, 2))
        == "-2.00"
    )


@covers(CobolFeature.ON_SIZE_ERROR)
def test_division_by_zero_is_uncomputable():
    assert _call(BuiltinName.COBOL_DIVIDE, 1, 0, 2) is Operators.UNCOMPUTABLE


@covers(CobolFeature.ARITHMETIC_EXPRESSION)
def test_non_numeric_operand_is_uncomputable():
    assert _call(BuiltinName.COBOL_ADD, " ", 1, 0) is Operators.UNCOMPUTABLE


@covers(CobolFeature.USAGE_COMP_2)
def test_to_float():
    assert _call(BuiltinName.COBOL_TO_FLOAT, from_literal("1.25")) == 1.25
    assert _call(BuiltinName.COBOL_TO_FLOAT, 1.5) == 1.5
    assert _call(BuiltinName.COBOL_TO_FLOAT, 3) == 3.0
