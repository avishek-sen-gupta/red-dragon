# pyright: standard
"""Fixed-width two's-complement IR builders, executed through the VM."""

from collections.abc import Sequence

from interpreter.hlasm.fixed_width_ir import (
    build_add_logical_cc_ir,
    build_add_signed_cc_ir,
    build_to_signed_ir,
    build_wrap_ir,
)
from interpreter.instructions import InstructionBase
from tests.unit.hlasm.straight_line_vm import returned_value


def _add(func_ir: Sequence[InstructionBase], left: int, right: int) -> int | list[int]:
    return returned_value(func_ir, {"%p_left": left, "%p_right": right})


def test_wrap_and_to_signed_reduce_modulo_the_width():
    wrap_32 = build_wrap_ir("wrap32", 32)
    signed_32 = build_to_signed_ir("signed32", 32)
    signed_64 = build_to_signed_ir("signed64", 64)
    assert [returned_value(wrap_32, {"%p_value": v}) for v in (-1, 1 << 32, 5)] == [
        0xFFFFFFFF,
        0,
        5,
    ]
    assert [
        returned_value(signed_32, {"%p_value": v})
        for v in (0xFFFFFFFF, 0x80000000, 0x7FFFFFFF, -1)
    ] == [-1, -0x80000000, 0x7FFFFFFF, -1]
    assert returned_value(signed_64, {"%p_value": (1 << 64) - 2}) == -2


def test_add_signed_32_sets_cc_and_wraps():
    add = build_add_signed_cc_ir("add32", 32)
    assert [
        _add(add, left, right)
        for left, right in ((1, 2), (0x7FFFFFFF, 1), (-1, 1), (-5, 1))
    ] == [[3, 2], [-0x80000000, 3], [0, 0], [-4, 1]]
    assert _add(add, -0x80000000, -1) == [0x7FFFFFFF, 3]
    assert _add(build_add_signed_cc_ir("add64", 64), (1 << 63) - 1, 1) == [
        -(1 << 63),
        3,
    ]


def test_add_logical_32_cc():
    add = build_add_logical_cc_ir("addl32", 32)
    assert [
        _add(add, left, right)
        for left, right in ((0xFFFFFFFF, 1), (1, 1), (0, 0), (0xFFFFFFFF, 2))
    ] == [[0, 2], [2, 1], [0, 0], [1, 3]]
    assert _add(build_add_logical_cc_ir("addl64", 64), (1 << 64) - 1, 1) == [0, 2]
