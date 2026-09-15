"""Builtins that accept exact COBOL values after the boundary migration."""

from __future__ import annotations

from cobol_asg.edit_picture import format_edited
from cobol_numeric.number import from_digits, from_literal
from interpreter.cobol.byte_builtins import (
    _builtin_cobol_blank_when_zero,
    _builtin_cobol_round,
    _builtin_float_to_bytes,
    _builtin_integer_of_date,
    _coerce_intrinsic_int,
)
from interpreter.cobol.cobol_constants import ByteConstants
from interpreter.cobol.features import CobolFeature
from interpreter.types.typed_value import typed_from_runtime
from interpreter.vm.vm import Operators
from tests.covers import covers


def _args(*values):
    return [typed_from_runtime(v) for v in values]


@covers(CobolFeature.ROUNDED_CLAUSE)
def test_round_accepts_exact_values_and_returns_plain_text():
    assert _builtin_cobol_round(_args(from_literal("0.665"), 2), None).value == "0.67"
    assert _builtin_cobol_round(_args(from_digits(1, 10), 2), None).value == "0.00"


@covers(CobolFeature.ROUNDED_CLAUSE)
def test_round_non_numeric_text_is_uncomputable():
    assert _builtin_cobol_round(_args("ABC", 2), None).value is Operators.UNCOMPUTABLE


@covers(CobolFeature.PIC_CLAUSE)
def test_blank_when_zero_recognises_exact_zero_text():
    encoded = [0xF0, 0xF0, 0xF0]
    assert (
        _builtin_cobol_blank_when_zero(_args(encoded, "0.00", 3), None).value
        == [ByteConstants.EBCDIC_SPACE] * 3
    )
    assert (
        _builtin_cobol_blank_when_zero(_args(encoded, "0.01", 3), None).value == encoded
    )


@covers(CobolFeature.USAGE_COMP_2)
def test_float_to_bytes_accepts_exact_values():
    import struct

    assert _builtin_float_to_bytes(_args(from_literal("1.25"), 8), None).value == list(
        struct.pack(">d", 1.25)
    )


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_integer_of_date_accepts_exact_whole_values():
    assert (
        _builtin_integer_of_date(_args(from_literal("20240101")), None).value == 154498
    )


@covers(CobolFeature.INTRINSIC_FUNCTION)
def test_integer_argument_coercion_accepts_exact_whole_values():
    assert _coerce_intrinsic_int(from_literal("12")) == 12
    assert _coerce_intrinsic_int(from_literal("12.5")) is None


@covers(CobolFeature.NUMERIC_EDITED)
def test_edit_picture_formats_exact_value_text():
    assert format_edited("1.50", "ZZ9.99") == "  1.50"
    assert format_edited("0.50", ".99") == ".50"
