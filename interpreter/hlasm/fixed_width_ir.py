# pyright: standard
"""IR builders for fixed-width two's-complement arithmetic, truncating division, bitwise connectives, shifts and rotates, and their condition codes."""

from collections.abc import Callable

from interpreter.hlasm.boolean_connective import BooleanConnective
from interpreter.hlasm.hlasm_constants import (
    LIST_SET,
    MAKE_LIST,
    PARAM_CARRY,
    PARAM_LEFT,
    PARAM_RIGHT,
    PARAM_VALUE,
)
from interpreter.instructions import (
    Binop,
    CallFunction,
    Const,
    InstructionBase,
    Return_,
)
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Fragment = tuple[Register, tuple[InstructionBase, ...]]

MAXIMUM_SHIFT_BITS = 64
MAXIMUM_DIVIDEND_BITS = 128


def _reg(prefix: str, role: str) -> Register:
    return Register(f"%{prefix}.{role}")


def _const(prefix: str, role: str, value: int) -> Fragment:
    reg = _reg(prefix, role)
    return reg, (Const.int_(reg, value),)


def _binop(
    prefix: str, role: str, operator: BinopKind, left: Register, right: Register
) -> Fragment:
    reg = _reg(prefix, role)
    return reg, (Binop(result_reg=reg, operator=operator, left=left, right=right),)


def _binop_const(
    prefix: str, role: str, operator: BinopKind, left: Register, right: int
) -> Fragment:
    constant, constant_ir = _const(f"{prefix}.{role}", "k", right)
    result, result_ir = _binop(prefix, role, operator, left, constant)
    return result, (*constant_ir, *result_ir)


def _wrap(prefix: str, value: Register, bits: int) -> Fragment:
    return _binop_const(prefix, "wrapped", BinopKind.MOD, value, 1 << bits)


def _to_signed(prefix: str, value: Register, bits: int) -> Fragment:
    half = 1 << (bits - 1)
    biased, biased_ir = _binop_const(prefix, "biased", BinopKind.ADD, value, half)
    wrapped, wrapped_ir = _wrap(prefix, biased, bits)
    signed, signed_ir = _binop_const(prefix, "signed", BinopKind.SUB, wrapped, half)
    return signed, (*biased_ir, *wrapped_ir, *signed_ir)


def _nonzero_bit(prefix: str, value: Register, bits: int) -> Fragment:
    negated, negated_ir = _binop_const(prefix, "neg", BinopKind.MUL, value, -1)
    either, either_ir = _binop(prefix, "either", BinopKind.BIT_OR, value, negated)
    top, top_ir = _binop_const(prefix, "top", BinopKind.RSHIFT, either, bits)
    bit, bit_ir = _binop_const(prefix, "nonzero", BinopKind.BIT_AND, top, 1)
    return bit, (*negated_ir, *either_ir, *top_ir, *bit_ir)


def _sign_bit(prefix: str, value: Register, bits: int) -> Fragment:
    top, top_ir = _binop_const(prefix, "sign_top", BinopKind.RSHIFT, value, bits - 1)
    bit, bit_ir = _binop_const(prefix, "sign", BinopKind.BIT_AND, top, 1)
    return bit, (*top_ir, *bit_ir)


def _pair(prefix: str, first: Register, second: Register) -> Fragment:
    size, size_ir = _const(prefix, "pair_size", 2)
    zero, zero_ir = _const(prefix, "pair_zero", 0)
    one, one_ir = _const(prefix, "pair_one", 1)
    empty = _reg(prefix, "pair_empty")
    half = _reg(prefix, "pair_half")
    full = _reg(prefix, "pair")
    return full, (
        *size_ir,
        *zero_ir,
        *one_ir,
        CallFunction(result_reg=empty, func_name=MAKE_LIST, args=(size, zero)),
        CallFunction(result_reg=half, func_name=LIST_SET, args=(empty, zero, first)),
        CallFunction(result_reg=full, func_name=LIST_SET, args=(half, one, second)),
    )


def _overflow_cc(prefix: str, base_cc: Register, overflow: Register) -> Fragment:
    gap, gap_ir = _binop_const(prefix, "cc_gap", BinopKind.SUB, base_cc, 3)
    lift, lift_ir = _binop(prefix, "cc_lift", BinopKind.MUL, gap, overflow)
    cc, cc_ir = _binop(prefix, "cc", BinopKind.SUB, base_cc, lift)
    return cc, (*gap_ir, *lift_ir, *cc_ir)


def _sign_cc(prefix: str, result: Register, bits: int) -> Fragment:
    nonzero, nonzero_ir = _nonzero_bit(f"{prefix}.res", result, bits)
    negative, negative_ir = _sign_bit(prefix, result, bits)
    doubled, doubled_ir = _binop_const(prefix, "nz2", BinopKind.MUL, nonzero, 2)
    base, base_ir = _binop(prefix, "cc_base", BinopKind.SUB, doubled, negative)
    return base, (*nonzero_ir, *negative_ir, *doubled_ir, *base_ir)


def _signed_cc(
    prefix: str, result: Register, overflow: Register, bits: int
) -> Fragment:
    base, base_ir = _sign_cc(prefix, result, bits)
    cc, cc_ir = _overflow_cc(prefix, base, overflow)
    return cc, (*base_ir, *cc_ir)


def build_sign_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    cc, cc_ir = _sign_cc(func_name, PARAM_VALUE, bits)
    return [*cc_ir, Return_(value_reg=cc)]


def build_nonzero_ir(func_name: str, bits: int) -> list[InstructionBase]:
    nonzero, nonzero_ir = _nonzero_bit(func_name, PARAM_VALUE, bits)
    return [*nonzero_ir, Return_(value_reg=nonzero)]


def build_wrap_ir(func_name: str, bits: int) -> list[InstructionBase]:
    wrapped, wrapped_ir = _wrap(func_name, PARAM_VALUE, bits)
    return [*wrapped_ir, Return_(value_reg=wrapped)]


def build_to_signed_ir(func_name: str, bits: int) -> list[InstructionBase]:
    signed, signed_ir = _to_signed(func_name, PARAM_VALUE, bits)
    return [*signed_ir, Return_(value_reg=signed)]


def _signed_arithmetic_cc_ir(
    func_name: str, bits: int, operator: BinopKind
) -> list[InstructionBase]:
    left, left_ir = _to_signed(f"{func_name}.l", PARAM_LEFT, bits)
    right, right_ir = _to_signed(f"{func_name}.r", PARAM_RIGHT, bits)
    exact, exact_ir = _binop(func_name, "exact", operator, left, right)
    result, result_ir = _to_signed(f"{func_name}.s", exact, bits)
    lost, lost_ir = _binop(func_name, "lost", BinopKind.SUB, exact, result)
    overflow, overflow_ir = _nonzero_bit(f"{func_name}.o", lost, 2 * bits)
    cc, cc_ir = _signed_cc(func_name, result, overflow, bits)
    pair, pair_ir = _pair(func_name, result, cc)
    return [
        *left_ir,
        *right_ir,
        *exact_ir,
        *result_ir,
        *lost_ir,
        *overflow_ir,
        *cc_ir,
        *pair_ir,
        Return_(value_reg=pair),
    ]


def build_load_test_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    value, value_ir = _to_signed(f"{func_name}.v", PARAM_VALUE, bits)
    cc, cc_ir = _sign_cc(func_name, value, bits)
    pair, pair_ir = _pair(func_name, value, cc)
    return [*value_ir, *cc_ir, *pair_ir, Return_(value_reg=pair)]


def _fitted_signed_cc_ir(
    func_name: str, bits: int, derive: Callable[[str, Register], Fragment]
) -> list[InstructionBase]:
    value, value_ir = _to_signed(f"{func_name}.v", PARAM_VALUE, bits)
    exact, exact_ir = derive(func_name, value)
    result, result_ir = _to_signed(f"{func_name}.s", exact, bits)
    lost, lost_ir = _binop(func_name, "lost", BinopKind.SUB, exact, result)
    overflow, overflow_ir = _nonzero_bit(f"{func_name}.o", lost, 2 * bits)
    cc, cc_ir = _signed_cc(func_name, result, overflow, bits)
    pair, pair_ir = _pair(func_name, result, cc)
    return [
        *value_ir,
        *exact_ir,
        *result_ir,
        *lost_ir,
        *overflow_ir,
        *cc_ir,
        *pair_ir,
        Return_(value_reg=pair),
    ]


def _negated(prefix: str, value: Register) -> Fragment:
    return _binop_const(prefix, "exact", BinopKind.MUL, value, -1)


def _magnitude(prefix: str, value: Register) -> Fragment:
    factor, factor_ir = _sign_factor(f"{prefix}.f", value)
    exact, exact_ir = _binop(prefix, "exact", BinopKind.MUL, value, factor)
    return exact, (*factor_ir, *exact_ir)


def build_negate_signed_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    return _fitted_signed_cc_ir(func_name, bits, _negated)


def build_absolute_signed_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    return _fitted_signed_cc_ir(func_name, bits, _magnitude)


def build_negative_absolute_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    value, value_ir = _to_signed(f"{func_name}.v", PARAM_VALUE, bits)
    magnitude, magnitude_ir = _magnitude(f"{func_name}.m", value)
    result, result_ir = _negated(func_name, magnitude)
    cc, cc_ir = _sign_cc(func_name, result, bits)
    pair, pair_ir = _pair(func_name, result, cc)
    return [
        *value_ir,
        *magnitude_ir,
        *result_ir,
        *cc_ir,
        *pair_ir,
        Return_(value_reg=pair),
    ]


def build_add_signed_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    return _signed_arithmetic_cc_ir(func_name, bits, BinopKind.ADD)


def build_sub_signed_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    return _signed_arithmetic_cc_ir(func_name, bits, BinopKind.SUB)


def build_multiply_signed_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    return _signed_arithmetic_cc_ir(func_name, bits, BinopKind.MUL)


def _sign_factor(prefix: str, value: Register) -> Fragment:
    negative, negative_ir = _sign_bit(prefix, value, MAXIMUM_DIVIDEND_BITS + 1)
    doubled, doubled_ir = _binop_const(prefix, "negative2", BinopKind.MUL, negative, 2)
    one, one_ir = _const(prefix, "one", 1)
    factor, factor_ir = _binop(prefix, "factor", BinopKind.SUB, one, doubled)
    return factor, (*negative_ir, *doubled_ir, *one_ir, *factor_ir)


def build_divide_truncating_ir(func_name: str) -> list[InstructionBase]:
    left_sign, left_sign_ir = _sign_factor(f"{func_name}.l", PARAM_LEFT)
    right_sign, right_sign_ir = _sign_factor(f"{func_name}.r", PARAM_RIGHT)
    dividend, dividend_ir = _binop(
        func_name, "dividend", BinopKind.MUL, PARAM_LEFT, left_sign
    )
    divisor, divisor_ir = _binop(
        func_name, "divisor", BinopKind.MUL, PARAM_RIGHT, right_sign
    )
    magnitude, magnitude_ir = _binop(
        func_name, "magnitude", BinopKind.FLOOR_DIV, dividend, divisor
    )
    left_over, left_over_ir = _binop(
        func_name, "left_over", BinopKind.MOD, dividend, divisor
    )
    sign, sign_ir = _binop(func_name, "sign", BinopKind.MUL, left_sign, right_sign)
    quotient, quotient_ir = _binop(
        func_name, "quotient", BinopKind.MUL, magnitude, sign
    )
    remainder, remainder_ir = _binop(
        func_name, "remainder", BinopKind.MUL, left_over, left_sign
    )
    pair, pair_ir = _pair(func_name, quotient, remainder)
    return [
        *left_sign_ir,
        *right_sign_ir,
        *dividend_ir,
        *divisor_ir,
        *magnitude_ir,
        *left_over_ir,
        *sign_ir,
        *quotient_ir,
        *remainder_ir,
        *pair_ir,
        Return_(value_reg=pair),
    ]


def _logical_cc_ir(func_name: str, bits: int, exact: Fragment) -> list[InstructionBase]:
    total, total_ir = exact
    result, result_ir = _wrap(f"{func_name}.s", total, bits)
    carry, carry_ir = _binop_const(func_name, "carry", BinopKind.RSHIFT, total, bits)
    nonzero, nonzero_ir = _nonzero_bit(func_name, result, bits)
    carry2, carry2_ir = _binop_const(func_name, "carry2", BinopKind.MUL, carry, 2)
    cc, cc_ir = _binop(func_name, "cc", BinopKind.ADD, carry2, nonzero)
    pair, pair_ir = _pair(func_name, result, cc)
    return [
        *total_ir,
        *result_ir,
        *carry_ir,
        *nonzero_ir,
        *carry2_ir,
        *cc_ir,
        *pair_ir,
        Return_(value_reg=pair),
    ]


def _logical_sum(func_name: str, bits: int, right: Fragment) -> Fragment:
    addend, addend_ir = right
    left, left_ir = _wrap(f"{func_name}.l", PARAM_LEFT, bits)
    exact, exact_ir = _binop(func_name, "exact", BinopKind.ADD, left, addend)
    return exact, (*addend_ir, *left_ir, *exact_ir)


def _with_carry_in(func_name: str, partial: Fragment) -> Fragment:
    total, total_ir = partial
    exact, exact_ir = _binop(func_name, "carried", BinopKind.ADD, total, PARAM_CARRY)
    return exact, (*total_ir, *exact_ir)


def _complement(prefix: str, value: Register, bits: int) -> Fragment:
    wrapped, wrapped_ir = _wrap(prefix, value, bits)
    flipped, flipped_ir = _binop_const(
        prefix, "complement", BinopKind.BIT_XOR, wrapped, (1 << bits) - 1
    )
    return flipped, (*wrapped_ir, *flipped_ir)


def build_add_logical_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    right = _wrap(f"{func_name}.r", PARAM_RIGHT, bits)
    return _logical_cc_ir(func_name, bits, _logical_sum(func_name, bits, right))


def build_add_logical_carry_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    right = _wrap(f"{func_name}.r", PARAM_RIGHT, bits)
    partial = _logical_sum(func_name, bits, right)
    return _logical_cc_ir(func_name, bits, _with_carry_in(func_name, partial))


def build_sub_logical_borrow_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    right = _complement(f"{func_name}.r", PARAM_RIGHT, bits)
    partial = _logical_sum(func_name, bits, right)
    return _logical_cc_ir(func_name, bits, _with_carry_in(func_name, partial))


def _compare_cc_ir(
    func_name: str, bits: int, operands: tuple[Fragment, Fragment]
) -> list[InstructionBase]:
    (left, left_ir), (right, right_ir) = operands
    difference, difference_ir = _binop(
        func_name, "difference", BinopKind.SUB, left, right
    )
    cc, cc_ir = _sign_cc(func_name, difference, bits + 1)
    return [*left_ir, *right_ir, *difference_ir, *cc_ir, Return_(value_reg=cc)]


def build_compare_signed_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    return _compare_cc_ir(
        func_name,
        bits,
        (
            _to_signed(f"{func_name}.l", PARAM_LEFT, bits),
            _to_signed(f"{func_name}.r", PARAM_RIGHT, bits),
        ),
    )


def build_compare_logical_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    return _compare_cc_ir(
        func_name,
        bits,
        (
            _wrap(f"{func_name}.l", PARAM_LEFT, bits),
            _wrap(f"{func_name}.r", PARAM_RIGHT, bits),
        ),
    )


def _complemented_if(
    prefix: str, value: Register, bits: int, complemented: bool
) -> Fragment:
    if complemented:
        return _complement(prefix, value, bits)
    return _wrap(prefix, value, bits)


def build_boolean_cc_ir(
    func_name: str, bits: int, connective: BooleanConnective
) -> list[InstructionBase]:
    left, left_ir = _wrap(f"{func_name}.l", PARAM_LEFT, bits)
    right, right_ir = _complemented_if(
        f"{func_name}.r", PARAM_RIGHT, bits, connective.complements_right
    )
    combined, combined_ir = _binop(
        func_name, "combined", connective.operator, left, right
    )
    result, result_ir = _complemented_if(
        f"{func_name}.s", combined, bits, connective.complements_result
    )
    nonzero, nonzero_ir = _nonzero_bit(func_name, result, bits)
    pair, pair_ir = _pair(func_name, result, nonzero)
    return [
        *left_ir,
        *right_ir,
        *combined_ir,
        *result_ir,
        *nonzero_ir,
        *pair_ir,
        Return_(value_reg=pair),
    ]


type DropWeight = Callable[[str, Register, Register], Fragment]


def _plain_drop_weight(prefix: str, selected: Register, mask: Register) -> Fragment:
    return _const(prefix, "drop_weight", 2)


def _ranked_drop_weight(prefix: str, selected: Register, mask: Register) -> Fragment:
    doubled, doubled_ir = _binop_const(prefix, "sel2", BinopKind.MUL, selected, 2)
    surplus, surplus_ir = _binop(prefix, "surplus", BinopKind.SUB, doubled, mask)
    leftmost_zero, leftmost_zero_ir = _sign_bit(prefix, surplus, MAXIMUM_SHIFT_BITS)
    weight, weight_ir = _binop_const(
        prefix, "drop_weight", BinopKind.ADD, leftmost_zero, 1
    )
    return weight, (*doubled_ir, *surplus_ir, *leftmost_zero_ir, *weight_ir)


def _under_mask_cc_ir(
    func_name: str, bits: int, drop_weight: DropWeight
) -> list[InstructionBase]:
    selected, selected_ir = _binop(
        func_name, "selected", BinopKind.BIT_AND, PARAM_LEFT, PARAM_RIGHT
    )
    unselected, unselected_ir = _binop(
        func_name, "unselected", BinopKind.SUB, PARAM_RIGHT, selected
    )
    any_one, any_one_ir = _nonzero_bit(f"{func_name}.s", selected, bits)
    any_zero, any_zero_ir = _nonzero_bit(f"{func_name}.u", unselected, bits)
    weight, weight_ir = drop_weight(func_name, selected, PARAM_RIGHT)
    drop, drop_ir = _binop(func_name, "drop", BinopKind.MUL, any_zero, weight)
    from_ones, from_ones_ir = _binop_const(
        func_name, "from_ones", BinopKind.SUB, drop, 3
    )
    negated, negated_ir = _binop_const(
        func_name, "negated", BinopKind.MUL, from_ones, -1
    )
    cc, cc_ir = _binop(func_name, "cc", BinopKind.MUL, any_one, negated)
    return [
        *selected_ir,
        *unselected_ir,
        *any_one_ir,
        *any_zero_ir,
        *weight_ir,
        *drop_ir,
        *from_ones_ir,
        *negated_ir,
        *cc_ir,
        Return_(value_reg=cc),
    ]


def build_test_under_mask_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    return _under_mask_cc_ir(func_name, bits, _plain_drop_weight)


def build_test_under_mask_ranked_cc_ir(
    func_name: str, bits: int
) -> list[InstructionBase]:
    return _under_mask_cc_ir(func_name, bits, _ranked_drop_weight)


def _value_ir(value: Fragment) -> list[InstructionBase]:
    result, result_ir = value
    return [*result_ir, Return_(value_reg=result)]


def _shifted_left(prefix: str, value: Register, bits: int) -> Fragment:
    moved, moved_ir = _binop(prefix, "moved", BinopKind.LSHIFT, value, PARAM_RIGHT)
    result, result_ir = _wrap(prefix, moved, bits)
    return result, (*moved_ir, *result_ir)


def build_shift_left_logical_ir(func_name: str, bits: int) -> list[InstructionBase]:
    value, value_ir = _wrap(f"{func_name}.l", PARAM_LEFT, bits)
    result, result_ir = _shifted_left(func_name, value, bits)
    return _value_ir((result, (*value_ir, *result_ir)))


def build_shift_right_logical_ir(func_name: str, bits: int) -> list[InstructionBase]:
    value, value_ir = _wrap(f"{func_name}.l", PARAM_LEFT, bits)
    result, result_ir = _binop(func_name, "moved", BinopKind.RSHIFT, value, PARAM_RIGHT)
    return _value_ir((result, (*value_ir, *result_ir)))


def build_rotate_left_ir(func_name: str, bits: int) -> list[InstructionBase]:
    value, value_ir = _wrap(f"{func_name}.l", PARAM_LEFT, bits)
    count, count_ir = _binop_const(func_name, "count", BinopKind.MOD, PARAM_RIGHT, bits)
    width, width_ir = _const(func_name, "width", bits)
    back, back_ir = _binop(func_name, "back", BinopKind.SUB, width, count)
    up, up_ir = _binop(func_name, "up", BinopKind.LSHIFT, value, count)
    down, down_ir = _binop(func_name, "down", BinopKind.RSHIFT, value, back)
    joined, joined_ir = _binop(func_name, "joined", BinopKind.BIT_OR, up, down)
    result, result_ir = _wrap(f"{func_name}.s", joined, bits)
    return _value_ir(
        (
            result,
            (
                *value_ir,
                *count_ir,
                *width_ir,
                *back_ir,
                *up_ir,
                *down_ir,
                *joined_ir,
                *result_ir,
            ),
        ),
    )


def _with_cc(func_name: str, result: Fragment, cc: Fragment) -> list[InstructionBase]:
    (value, value_ir), (code, code_ir) = result, cc
    pair, pair_ir = _pair(func_name, value, code)
    return [*value_ir, *code_ir, *pair_ir, Return_(value_reg=pair)]


def _sign_kept_shift(prefix: str, image: Register, bits: int) -> Fragment:
    sign, sign_ir = _binop_const(
        prefix, "sign_kept", BinopKind.BIT_AND, image, 1 << (bits - 1)
    )
    moved, moved_ir = _binop(prefix, "moved", BinopKind.LSHIFT, image, PARAM_RIGHT)
    numeric, numeric_ir = _binop_const(
        prefix, "numeric", BinopKind.BIT_AND, moved, (1 << (bits - 1)) - 1
    )
    result, result_ir = _binop(prefix, "result", BinopKind.BIT_OR, sign, numeric)
    return result, (*sign_ir, *moved_ir, *numeric_ir, *result_ir)


def _shifted_out_unlike_sign(prefix: str, image: Register, bits: int) -> Fragment:
    signed, signed_ir = _to_signed(f"{prefix}.v", image, bits)
    exact, exact_ir = _binop(prefix, "exact", BinopKind.LSHIFT, signed, PARAM_RIGHT)
    fitted, fitted_ir = _to_signed(f"{prefix}.f", exact, bits)
    lost, lost_ir = _binop(prefix, "lost", BinopKind.SUB, exact, fitted)
    overflow, overflow_ir = _nonzero_bit(f"{prefix}.o", lost, bits + MAXIMUM_SHIFT_BITS)
    return overflow, (*signed_ir, *exact_ir, *fitted_ir, *lost_ir, *overflow_ir)


def build_shift_left_signed_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    image, image_ir = _wrap(f"{func_name}.l", PARAM_LEFT, bits)
    result, result_ir = _sign_kept_shift(func_name, image, bits)
    overflow, overflow_ir = _shifted_out_unlike_sign(func_name, image, bits)
    cc, cc_ir = _signed_cc(func_name, result, overflow, bits)
    return _with_cc(
        func_name,
        (result, (*image_ir, *result_ir)),
        (cc, (*overflow_ir, *cc_ir)),
    )


def build_shift_right_signed_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    signed, signed_ir = _to_signed(f"{func_name}.l", PARAM_LEFT, bits)
    moved, moved_ir = _binop(func_name, "moved", BinopKind.RSHIFT, signed, PARAM_RIGHT)
    result, result_ir = _wrap(f"{func_name}.s", moved, bits)
    cc, cc_ir = _sign_cc(func_name, result, bits)
    return _with_cc(
        func_name, (result, (*signed_ir, *moved_ir, *result_ir)), (cc, cc_ir)
    )
