"""Both numeric encode paths share one digits implementation (red-dragon-bqds),
and COBOL numeric text always satisfies IS NUMERIC (8d3b4e54 contract)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from cobol_numeric.number import from_digits, from_literal, scale_by, to_plain_str
from interpreter.cobol.byte_builtins import (
    _builtin_cobol_prepare_digits,
    _builtin_cobol_prepare_sign,
    _builtin_is_numeric,
)
from interpreter.cobol.cobol_constants import BuiltinName, ByteConstants
from interpreter.cobol.byte_builtins import BYTE_BUILTINS
from interpreter.cobol.features import CobolFeature
from interpreter.cobol.numeric_builtins import _builtin_cobol_to_text
from interpreter.cobol.pic_scale import encode_scaled_digits
from interpreter.func_name import FuncName
from interpreter.types.typed_value import typed_from_runtime
from tests.covers import NotLanguageFeature, covers

_CORPUS = [
    ("123.45", 5, 2, 0),
    ("-123.45", 5, 2, 0),
    ("1.237", 5, 2, 0),
    ("12.5", 3, 0, 0),
    ("12300", 3, 0, 2),
    ("123456", 3, 0, 0),
    ("0", 3, 0, 0),
    ("0.00001", 6, 5, 0),
    ("7", 4, 1, 0),
]


def _runtime_digits(value: str, total: int, decimals: int, scale: int) -> str:
    result = _builtin_cobol_prepare_digits(
        [
            typed_from_runtime(value),
            typed_from_runtime(total),
            typed_from_runtime(decimals),
            typed_from_runtime(True),
            typed_from_runtime(scale),
        ],
        None,
    )
    return "".join(str(d) for d in result.value)


@pytest.mark.parametrize("value, total, decimals, scale", _CORPUS)
@covers(CobolFeature.PIC_CLAUSE)
def test_value_clause_and_runtime_encode_paths_agree(value, total, decimals, scale):
    td = SimpleNamespace(total_digits=total, decimal_digits=decimals, scale=scale)
    assert encode_scaled_digits(value, td) == _runtime_digits(
        value, total, decimals, scale
    )


@covers(CobolFeature.PIC_CLAUSE)
def test_fraction_into_integer_field_truncates_on_the_value_clause_path():
    # red-dragon-bqds: the VALUE path used to store '125' (a 10x shift).
    td = SimpleNamespace(total_digits=3, decimal_digits=0, scale=0)
    assert encode_scaled_digits("12.5", td) == "012"


@covers(CobolFeature.PIC_CLAUSE)
def test_runtime_path_accepts_exact_and_float_values():
    number = from_literal("123.45")
    result = _builtin_cobol_prepare_digits(
        [
            typed_from_runtime(number),
            typed_from_runtime(5),
            typed_from_runtime(2),
            typed_from_runtime(True),
        ],
        None,
    )
    assert result.value == [1, 2, 3, 4, 5]


@covers(CobolFeature.PIC_CLAUSE)
def test_runtime_path_tolerates_non_numeric_text():
    result = _builtin_cobol_prepare_digits(
        [
            typed_from_runtime("ABC"),
            typed_from_runtime(3),
            typed_from_runtime(0),
            typed_from_runtime(False),
        ],
        None,
    )
    assert result.value == [0, 0, 0]


@pytest.mark.parametrize(
    "value, expected",
    [
        ("-1.5", ByteConstants.SIGN_NIBBLE_NEGATIVE),
        ("-0.001", ByteConstants.SIGN_NIBBLE_NEGATIVE),
        ("-0", ByteConstants.SIGN_NIBBLE_POSITIVE),
        ("1.5", ByteConstants.SIGN_NIBBLE_POSITIVE),
    ],
)
@covers(CobolFeature.PIC_CLAUSE)
def test_sign_nibble_follows_the_pre_truncation_sign(value, expected):
    result = _builtin_cobol_prepare_sign(
        [typed_from_runtime(value), typed_from_runtime(True)], None
    )
    assert result.value == expected


@covers(CobolFeature.DISPLAY)
def test_cobol_to_text_renders_numbers_plainly():
    def text(value):
        return _builtin_cobol_to_text([typed_from_runtime(value)], None).value

    assert text(1e-05) == "0.00001"
    assert text(from_digits(80, 2)) == "0.80"
    assert text(42) == "42"
    assert text("ABC") == "ABC"
    assert FuncName(BuiltinName.COBOL_TO_TEXT) in BYTE_BUILTINS


@pytest.mark.parametrize(
    "value",
    [
        from_digits(0, 0),
        from_digits(-5, 3),
        from_digits(18003830, 2),
        scale_by(1, -10),
        scale_by(123, 4),
        from_literal("999999999.999999999"),
        from_digits(-1, 0),
    ],
)
@covers(CobolFeature.CLASS_CONDITION)
def test_every_plain_number_text_is_numeric(value):
    rendered = to_plain_str(value)
    assert _builtin_is_numeric([typed_from_runtime(rendered)], None).value is True
