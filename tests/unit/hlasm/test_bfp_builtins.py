# pyright: standard
"""The BFP builtins map sign, biased-exponent and fraction fields to zarch_float values and back, and report results in the FPC's mask and DXC layouts."""

from collections.abc import Sequence

from interpreter.func_name import FuncName
from interpreter.hlasm.bfp_builtins import bfp_builtins
from interpreter.hlasm.bfp_fields import BfpFields, fields_of, value_of
from interpreter.types.typed_value import typed
from interpreter.vm.vm import VMState
from tests.covers import NotLanguageFeature, covers
from tests.unit.zarch_float.bfp_bits import long_of, short_of
from zarch_float.bfp_format import EXTENDED, LONG, SHORT
from zarch_float.bfp_value import BfpValue
from zarch_float.float_kind import FloatKind

NEAREST_EVEN = 4
TOWARD_ZERO = 5
TOWARD_NEGATIVE = 7
FRACTION_HALF = 1 << 51


def _call(name: str, args: Sequence[int | list[int]]) -> int | list[int]:
    builtin = bfp_builtins()[FuncName(name)]
    return builtin([typed(arg) for arg in args], VMState()).value


def _long(x: float) -> list[int]:
    fields = fields_of(long_of(x))
    return [int(fields.negative), fields.biased_exponent, fields.fraction]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_fields_map_every_class_to_a_value_and_back():
    fields = {
        "+0 long": (BfpFields(False, 0, 0), LONG, long_of(0.0)),
        "-1.5 long": (BfpFields(True, 1023, FRACTION_HALF), LONG, long_of(-1.5)),
        "min subnormal short": (BfpFields(False, 0, 1), SHORT, short_of(2.0**-149)),
        "-inf short": (BfpFields(True, 255, 0), SHORT, short_of(-float("inf"))),
        "qnan extended": (
            BfpFields(False, 0x7FFF, (1 << 111) | 3),
            EXTENDED,
            BfpValue(EXTENDED, False, FloatKind.QNAN, 3),
        ),
        "snan long": (
            BfpFields(True, 2047, 9),
            LONG,
            BfpValue(LONG, True, FloatKind.SNAN, 9),
        ),
        "2 extended": (
            BfpFields(False, 16384, 0),
            EXTENDED,
            BfpValue(EXTENDED, False, FloatKind.FINITE, 1 << 112, -111),
        ),
    }

    assert {name: value_of(f, fmt) for name, (f, fmt, value) in fields.items()} == {
        name: value for name, (f, fmt, value) in fields.items()
    }
    assert {name: fields_of(value) for name, (f, fmt, value) in fields.items()} == {
        name: f for name, (f, fmt, value) in fields.items()
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_builtins_return_value_scaled_value_trap_flags_dxcs_and_cc():
    assert {
        "add": _call("__hlasm_bfp_add_long", [NEAREST_EVEN, _long(1.0), _long(2.0)]),
        "overflow": _call(
            "__hlasm_bfp_multiply_short",
            [NEAREST_EVEN, [0, 227, 0], [0, 227, 0]],
        ),
        "inexact": _call(
            "__hlasm_bfp_add_short", [NEAREST_EVEN, [0, 127, 0], [0, 97, 0]]
        ),
        "divide by zero": _call(
            "__hlasm_bfp_divide_long", [NEAREST_EVEN, _long(1.0), _long(0.0)]
        ),
        "fused": _call(
            "__hlasm_bfp_multiply_add_long",
            [NEAREST_EVEN, _long(2.0), _long(3.0), _long(1.0)],
        ),
        "integral": _call(
            "__hlasm_bfp_round_to_integral_short", [TOWARD_ZERO, [1, 128, 1 << 21]]
        ),
        "root": _call(
            "__hlasm_bfp_square_root_extended", [NEAREST_EVEN, [0, 16385, 0]]
        ),
        "lengthened": _call(
            "__hlasm_bfp_multiply_lengthened_short", [[0, 127, 1 << 22], [0, 255, 1]]
        ),
        "divide to integer": _call(
            "__hlasm_bfp_divide_to_integer_long",
            [NEAREST_EVEN, NEAREST_EVEN, _long(7.0), _long(2.0)],
        ),
        "partial": _call(
            "__hlasm_bfp_divide_to_integer_long",
            [NEAREST_EVEN, NEAREST_EVEN, _long(2.0**60), _long(3.0)],
        ),
        "nan quotient": _call(
            "__hlasm_bfp_divide_to_integer_short",
            [NEAREST_EVEN, NEAREST_EVEN, [0, 127, 0], [0, 255, 1]],
        ),
    } == {
        "add": [*_long(3.0), *_long(3.0), 0, 0, 0, 0, 0],
        "overflow": [0, 255, 0, 0, 135, 0, 0x28, 0x28, 0x20, 0x0C, 0],
        "inexact": [0, 127, 0, 0, 127, 0, 0x08, 0x08, 0, 0x08, 0],
        "divide by zero": [
            *_long(float("inf")),
            *_long(float("inf")),
            0x40,
            0x40,
            0,
            0,
            0,
        ],
        "fused": [*_long(7.0), *_long(7.0), 0, 0, 0, 0, 0],
        "integral": [1, 128, 0, 1, 128, 0, 0x08, 0x08, 0, 0x08, 0],
        "root": [0, 16384, 0, 0, 16384, 0, 0, 0, 0, 0, 0],
        "lengthened": [
            0,
            2047,
            1 << 51 | 1 << 29,
            0,
            2047,
            1 << 51 | 1 << 29,
            0x80,
            0x80,
            0,
            0,
            0,
        ],
        "divide to integer": [*_long(-1.0), *_long(-1.0), 0, 0, 0, 0, 0, *_long(4.0)],
        "partial": [
            *_long(64.0),
            *_long(64.0),
            0,
            0,
            0,
            0,
            2,
            *_long(384307168202282304.0),
        ],
        "nan quotient": [
            0,
            255,
            1 << 22 | 1,
            0,
            255,
            1 << 22 | 1,
            0x80,
            0x80,
            0,
            0,
            1,
            0,
            255,
            1 << 22 | 1,
        ],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_conversion_builtins_report_the_integer_image_and_cc_or_the_rounded_value():
    assert {
        "to fixed inexact": _call(
            "__hlasm_bfp_to_fixed_32_long", [NEAREST_EVEN, _long(2.5)]
        ),
        "to fixed incremented": _call(
            "__hlasm_bfp_to_fixed_32_long", [NEAREST_EVEN, _long(-3.5)]
        ),
        "to fixed nan": _call(
            "__hlasm_bfp_to_fixed_32_short", [NEAREST_EVEN, [0, 255, 1 << 22]]
        ),
        "to fixed minus zero": _call(
            "__hlasm_bfp_to_fixed_64_long", [NEAREST_EVEN, _long(-0.0)]
        ),
        "to logical negative": _call(
            "__hlasm_bfp_to_logical_64_extended", [NEAREST_EVEN, [1, 16383, 0]]
        ),
        "to logical too large": _call(
            "__hlasm_bfp_to_logical_32_long", [TOWARD_ZERO, _long(2.0**32)]
        ),
        "from fixed": _call("__hlasm_bfp_from_fixed_short", [NEAREST_EVEN, 2**24 + 1]),
        "from fixed toward minus": _call(
            "__hlasm_bfp_from_fixed_long", [TOWARD_NEGATIVE, -(2**53 + 1)]
        ),
        "rounded overflow": _call(
            "__hlasm_bfp_rounded_to_short_long",
            [NEAREST_EVEN, [0, 2046, (1 << 52) - 1]],
        ),
        "rounded snan": _call(
            "__hlasm_bfp_rounded_to_long_extended", [NEAREST_EVEN, [1, 0x7FFF, 1 << 60]]
        ),
    } == {
        "to fixed inexact": [2, 0, 0, 2, 0, 0, 0x08, 0x08, 0, 0x08, 2],
        "to fixed incremented": [
            0xFFFFFFFC,
            0,
            0,
            0xFFFFFFFC,
            0,
            0,
            0x08,
            0x08,
            0,
            0x0C,
            1,
        ],
        "to fixed nan": [
            0x80000000,
            0,
            0,
            0x80000000,
            0,
            0,
            0x88,
            0x88,
            0,
            0x08,
            3,
        ],
        "to fixed minus zero": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        "to logical negative": [0, 0, 0, 0, 0, 0, 0x88, 0x88, 0, 0x08, 3],
        "to logical too large": [
            0xFFFFFFFF,
            0,
            0,
            0xFFFFFFFF,
            0,
            0,
            0x88,
            0x88,
            0,
            0x08,
            3,
        ],
        "from fixed": [0, 151, 0, 0, 151, 0, 0x08, 0x08, 0, 0x08, 0],
        "from fixed toward minus": [
            1,
            1076,
            1,
            1,
            1076,
            1,
            0x08,
            0x08,
            0,
            0x0C,
            0,
        ],
        "rounded overflow": [0, 255, 0, 0, 1535, 0, 0x28, 0x28, 0x2C, 0x0C, 0],
        "rounded snan": [
            1,
            2047,
            1 << 51 | 1,
            1,
            2047,
            1 << 51 | 1,
            0x80,
            0x80,
            0,
            0,
            0,
        ],
    }
