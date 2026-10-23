# pyright: standard
"""The HFP builtins map sign, characteristic and fraction fields to zarch_float values and back: results carry the characteristic modulo 128 and condition bits aligned with the program mask; compare returns the CC."""

from collections.abc import Sequence

from interpreter.func_name import FuncName
from interpreter.hlasm.hfp_builtins import hfp_builtins
from interpreter.types.typed_value import typed
from interpreter.vm.vm import VMState
from tests.covers import NotLanguageFeature, covers

SIGNIFICANCE, UNDERFLOW, OVERFLOW, DIVIDE, SQUARE_ROOT = 0x01, 0x02, 0x10, 0x20, 0x40
ONE, TWO, THREE = [0, 0x41, 0x100000], [0, 0x41, 0x200000], [0, 0x41, 0x300000]
LONG_ONE, LONG_TWO = [0, 0x41, 1 << 52], [0, 0x41, 2 << 52]


def _call(name: str, args: Sequence[list[int]]) -> int | list[int]:
    builtin = hfp_builtins()[FuncName(f"__hlasm_hfp_{name}")]
    return builtin([typed(arg) for arg in args], VMState()).value


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_builtins_return_fields_with_the_wrapped_characteristic_and_conditions():
    assert {
        "add": _call("add_short", [ONE, TWO]),
        "overflow": _call("add_short", [[0, 0x7F, 0xFFFFFF], [0, 0x7F, 0xFFFFFF]]),
        "significance": _call(
            "subtract_unnormalized_short", [ONE, [0, 0x40, 0xFFFFFF]]
        ),
        "underflow": _call("multiply_short", [[0, 1, 0x100000], [0, 1, 0x100000]]),
        "lengthened": _call("multiply_lengthened_short", [THREE, [0, 0x40, 0x555556]]),
        "divide": _call("divide_short", [ONE, [1, 0x41, 0]]),
        "halve": _call("halve_long", [[1, 0x41, 1 << 52 | 1]]),
        "root": _call("square_root_short", [[1, 0x41, 0x400000]]),
        "integer": _call("load_fp_integer_extended", [[1, 0x41, 0x28 << 104 | 1]]),
        "fused": _call("multiply_subtract_short", [TWO, THREE, ONE]),
        "unnormalized": _call("multiply_unnormalized_long", [LONG_TWO, LONG_ONE]),
        "wrapped": _call(
            "multiply_add_unnormalized_long",
            [[0, 0x7F, 1 << 52], [0, 0x7F, 1 << 52], [1, 0, 0]],
        ),
    } == {
        "add": [0, 0x41, 0x300000, 0],
        "overflow": [0, 0, 0x1FFFFF, OVERFLOW],
        "significance": [0, 0x41, 0, SIGNIFICANCE],
        "underflow": [0, 0x41, 0x100000, UNDERFLOW],
        "lengthened": [0, 0x41, 0x10000020000000, 0],
        "divide": [0, 0x41, 0x100000, DIVIDE],
        "halve": [1, 0x40, 0x80000000000008, 0],
        "root": [1, 0x41, 0x400000, SQUARE_ROOT],
        "integer": [1, 0x41, 0x2 << 108, 0],
        "fused": [0, 0x41, 0x500000, 0],
        "unnormalized": [0, 0x42, 2 << 104, 0],
        "wrapped": [0, 0x3E, 1 << 104, 0],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_compare_returns_the_cc_of_the_guard_digit_difference():
    assert [
        _call("compare_short", [ONE, [0, 0x40, 0xFFFFFF]]),
        _call("compare_long", [[0, 0x42, 0], [0, 0x40, 1]]),
        _call("compare_extended", [[1, 0x41, 1 << 108], [0, 0x41, 1 << 108]]),
    ] == [2, 0, 1]
