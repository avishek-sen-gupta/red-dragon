# pyright: standard
"""The DFP builtins map [negative, e, significand] fields to zarch_float values and back, and report results in the FPC's mask and DXC layouts, the quantum bit included."""

from collections.abc import Sequence

from interpreter.func_name import FuncName
from interpreter.hlasm.dfp_builtins import dfp_builtins
from interpreter.hlasm.dfp_fields import dfp_fields_of, dfp_value_of
from interpreter.types.typed_value import typed
from interpreter.vm.vm import VMState
from tests.covers import NotLanguageFeature, covers
from zarch_float.dfp_format import EXTENDED, LONG
from zarch_float.dfp_value import DfpValue
from zarch_float.float_kind import FloatKind

NEAREST_EVEN = 8
TOWARD_ZERO = 9
ONE = [0, 398, 1]
TWO = [0, 398, 2]
THREE = [0, 398, 3]
ZERO = [0, 398, 0]
INFINITY = [0, -1, 0]
QNAN = [0, -2, 7]
LARGEST = [0, 767, 10**16 - 1]
TEN = [0, 398, 10]
NO_FIELDS = [0, 0, 0]


def _call(name: str, args: Sequence[int | list[int]]) -> int | list[int]:
    builtin = dfp_builtins()[FuncName(f"__hlasm_dfp_{name}")]
    return builtin([typed(arg) for arg in args], VMState()).value


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_fields_map_every_kind_to_a_value_and_back():
    values = {
        "+1 long": ([0, 398, 1], LONG, DfpValue(LONG, False, FloatKind.FINITE, 1, 0)),
        "-0 at the bottom": (
            [1, 0, 0],
            LONG,
            DfpValue(LONG, True, FloatKind.ZERO, 0, -398),
        ),
        "-infinity": ([1, -1, 0], LONG, DfpValue(LONG, True, FloatKind.INFINITY)),
        "qnan payload": (
            [0, -2, 5],
            EXTENDED,
            DfpValue(EXTENDED, False, FloatKind.QNAN, 5),
        ),
        "snan payload": ([1, -3, 9], LONG, DfpValue(LONG, True, FloatKind.SNAN, 9)),
        "extended 1": (
            [0, 6176, 1],
            EXTENDED,
            DfpValue(EXTENDED, False, FloatKind.FINITE, 1, 0),
        ),
    }

    assert {name: dfp_value_of(f, fmt) for name, (f, fmt, v) in values.items()} == {
        name: v for name, (f, fmt, v) in values.items()
    }
    assert {name: dfp_fields_of(v) for name, (f, fmt, v) in values.items()} == {
        name: f for name, (f, fmt, v) in values.items()
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_builtins_return_value_scaled_value_trap_flags_and_dxcs():
    assert {
        "add": _call("add_long", [NEAREST_EVEN, ONE, TWO]),
        "inexact quotient": _call("divide_long", [NEAREST_EVEN, ONE, THREE]),
        "divide by zero": _call("divide_long", [NEAREST_EVEN, ONE, ZERO]),
        "overflow": _call("multiply_long", [NEAREST_EVEN, LARGEST, TEN]),
        "quantize": _call("quantize_long", [NEAREST_EVEN, [0, 396, 123], [0, 397, 1]]),
        "reround": _call("reround_long", [NEAREST_EVEN, [0, 398, 123456], 3]),
        "integral": _call("round_to_integral_extended", [TOWARD_ZERO, [1, 6175, 25]]),
        "compare": _call("compare_long", [ONE, TWO]),
        "compare and signal": _call("compare_signaling_long", [ONE, QNAN]),
    } == {
        "add": [*THREE, *THREE, 0, 0, 0, 0, 0],
        "inexact quotient": [
            *[0, 382, 3333333333333333],
            *[0, 382, 3333333333333333],
            0x0C,
            0x0C,
            0,
            0x08,
            0,
        ],
        "divide by zero": [*INFINITY, *INFINITY, 0x40, 0x40, 0, 0, 0],
        "overflow": [*INFINITY, 0, 192, 10**16 - 1, 0x2C, 0x2C, 0x20, 0x0C, 0],
        "quantize": [0, 397, 12, 0, 397, 12, 0x0C, 0x0C, 0, 0x08, 0],
        "reround": [0, 401, 123, 0, 401, 123, 0x0C, 0x0C, 0, 0x08, 0],
        "integral": [1, 6176, 2, 1, 6176, 2, 0x0C, 0x0C, 0, 0x08, 0],
        "compare": [*NO_FIELDS, *NO_FIELDS, 0, 0, 0, 0, 1],
        "compare and signal": [*NO_FIELDS, *NO_FIELDS, 0x80, 0x80, 0, 0, 3],
    }
