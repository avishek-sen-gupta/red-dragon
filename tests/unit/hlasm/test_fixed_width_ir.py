# pyright: standard
"""Fixed-width two's-complement IR builders, executed through the VM."""

from collections.abc import Sequence

from interpreter.hlasm.boolean_connective import (
    AND,
    AND_WITH_COMPLEMENT,
    NAND,
    NOR,
    NOT_XOR,
    OR,
    OR_WITH_COMPLEMENT,
    XOR,
)
from interpreter.hlasm.fixed_width_ir import (
    build_add_logical_carry_cc_ir,
    build_add_logical_cc_ir,
    build_add_signed_cc_ir,
    build_boolean_cc_ir,
    build_compare_logical_cc_ir,
    build_compare_signed_cc_ir,
    build_sign_cc_ir,
    build_sub_logical_borrow_cc_ir,
    build_sub_signed_cc_ir,
    build_to_signed_ir,
    build_wrap_ir,
)
from interpreter.instructions import InstructionBase
from tests.unit.hlasm.straight_line_vm import returned_value


def _pair_of(
    func_ir: Sequence[InstructionBase], left: int, right: int
) -> int | list[int]:
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
        _pair_of(add, left, right)
        for left, right in ((1, 2), (0x7FFFFFFF, 1), (-1, 1), (-5, 1))
    ] == [[3, 2], [-0x80000000, 3], [0, 0], [-4, 1]]
    assert _pair_of(add, -0x80000000, -1) == [0x7FFFFFFF, 3]
    assert _pair_of(build_add_signed_cc_ir("add64", 64), (1 << 63) - 1, 1) == [
        -(1 << 63),
        3,
    ]


def test_sub_signed_32_sets_cc_and_wraps_exactly_at_the_minimum():
    sub = build_sub_signed_cc_ir("sub32", 32)
    assert [
        _pair_of(sub, left, right)
        for left, right in ((5, 3), (3, 5), (7, 7), (0, -0x80000000))
    ] == [[2, 2], [-2, 1], [0, 0], [-0x80000000, 3]]
    assert [_pair_of(sub, -0x80000000, 1), _pair_of(sub, -1, -0x80000000)] == [
        [0x7FFFFFFF, 3],
        [0x7FFFFFFF, 2],
    ]
    assert _pair_of(build_sub_signed_cc_ir("sub64", 64), -(1 << 63), 1) == [
        (1 << 63) - 1,
        3,
    ]


def test_add_logical_32_cc():
    add = build_add_logical_cc_ir("addl32", 32)
    assert [
        _pair_of(add, left, right)
        for left, right in ((0xFFFFFFFF, 1), (1, 1), (0, 0), (0xFFFFFFFF, 2))
    ] == [[0, 2], [2, 1], [0, 0], [1, 3]]
    assert _pair_of(build_add_logical_cc_ir("addl64", 64), (1 << 64) - 1, 1) == [0, 2]


def _sum_of(
    func_ir: Sequence[InstructionBase], left: int, right: int, carry: int
) -> int | list[int]:
    return returned_value(
        func_ir, {"%p_left": left, "%p_right": right, "%p_carry": carry}
    )


def test_add_logical_with_carry_and_subtract_logical_with_borrow_cc():
    add = build_add_logical_carry_cc_ir("addlc32", 32)
    sub = build_sub_logical_borrow_cc_ir("sublb32", 32)
    assert [
        _sum_of(add, left, right, carry)
        for left, right, carry in (
            (0xFFFFFFFF, 0, 1),
            (0xFFFFFFFF, 0xFFFFFFFF, 1),
            (1, 2, 1),
            (0, 0, 0),
        )
    ] == [[0, 2], [0xFFFFFFFF, 3], [4, 1], [0, 0]]
    assert [
        _sum_of(sub, left, right, carry)
        for left, right, carry in (
            (5, 3, 1),
            (3, 3, 1),
            (0, 1, 1),
            (5, 3, 0),
            (0, 0, 0),
            (0, 0xFFFFFFFF, 0),
        )
    ] == [[2, 3], [0, 2], [0xFFFFFFFF, 1], [1, 3], [0xFFFFFFFF, 1], [0, 0]]
    assert [
        _sum_of(build_add_logical_carry_cc_ir("addlc64", 64), (1 << 64) - 1, 0, 1),
        _sum_of(build_sub_logical_borrow_cc_ir("sublb64", 64), 0, (1 << 64) - 1, 0),
    ] == [[0, 2], [0, 0]]


def test_sign_cc_is_zero_leftmost_bit_one_or_other():
    cc_16 = build_sign_cc_ir("cc16", 16)
    assert [
        returned_value(cc_16, {"%p_value": v}) for v in (0, 0x8000, 0xFFFF, 0x7FFF, 1)
    ] == [0, 1, 1, 2, 2]


def test_compare_cc_is_equal_low_or_high_under_the_signed_or_logical_reading():
    signed_32 = build_compare_signed_cc_ir("cmp32", 32)
    logical_32 = build_compare_logical_cc_ir("cmpl32", 32)
    vectors = ((7, 7), (0x80000000, 1), (1, 0x80000000), (0xFFFFFFFF, -1), (-2, 5))
    assert [_pair_of(signed_32, left, right) for left, right in vectors] == [
        0,
        1,
        2,
        0,
        1,
    ]
    assert [_pair_of(logical_32, left, right) for left, right in vectors] == [
        0,
        2,
        1,
        0,
        2,
    ]
    assert [
        _pair_of(build_compare_signed_cc_ir("cmp64", 64), -(1 << 63), (1 << 63) - 1),
        _pair_of(build_compare_logical_cc_ir("cmpl64", 64), (1 << 64) - 1, 0),
        _pair_of(build_compare_signed_cc_ir("cmp16", 16), 0x8000, 0x7FFF),
        _pair_of(build_compare_logical_cc_ir("cmpl8", 8), 0x80, 0x7F),
    ] == [1, 2, 1, 2]


def test_boolean_connectives_set_the_result_and_cc_zero_or_nonzero_at_the_width():
    word = 0xFFFFFFFF
    doubleword = (1 << 64) - 1
    vectors_32 = {
        "and": (AND, ((0xF0F0F0F0, 0x0F0F0F0F), (0xFF00FF00, 0x0FF00FF0))),
        "or": (OR, ((0, 0), (0x80000000, 1))),
        "xor": (XOR, ((0x1234, 0x1234), (0xFFFF0000, word))),
        "andc": (AND_WITH_COMPLEMENT, ((5, 5), (0xFFFF0000, 0xFF00FF00))),
        "orc": (OR_WITH_COMPLEMENT, ((0, word), (0, 0xFFFF0000))),
        "nand": (NAND, ((word, word), (0, 0))),
        "nor": (NOR, ((1, 0xFFFFFFFE), (0, 0))),
        "nxor": (NOT_XOR, ((0, word), (0x5A, 0x5A))),
    }
    assert {
        name: [
            _pair_of(build_boolean_cc_ir(f"b32.{name}", 32, connective), left, right)
            for left, right in pairs
        ]
        for name, (connective, pairs) in vectors_32.items()
    } == {
        "and": [[0, 0], [0x0F000F00, 1]],
        "or": [[0, 0], [0x80000001, 1]],
        "xor": [[0, 0], [0x0000FFFF, 1]],
        "andc": [[0, 0], [0x00FF0000, 1]],
        "orc": [[0, 0], [0x0000FFFF, 1]],
        "nand": [[0, 0], [word, 1]],
        "nor": [[0, 0], [word, 1]],
        "nxor": [[0, 0], [word, 1]],
    }
    assert [
        _pair_of(build_boolean_cc_ir("b64.nor", 64, NOR), 0, 0),
        _pair_of(build_boolean_cc_ir("b64.andc", 64, AND_WITH_COMPLEMENT), -1, 1),
        _pair_of(build_boolean_cc_ir("b16.and", 16, AND), 0x0123, 0xFEDC),
        _pair_of(build_boolean_cc_ir("b8.and", 8, AND), 0xFF, -16),
        _pair_of(build_boolean_cc_ir("b8.or", 8, OR), 0x0F, -16),
    ] == [[doubleword, 1], [doubleword - 1, 1], [0, 0], [0xF0, 1], [0xFF, 1]]
