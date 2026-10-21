# pyright: standard
"""IR builders for fixed-width two's-complement arithmetic and its condition codes."""

from interpreter.hlasm.hlasm_constants import (
    LIST_SET,
    MAKE_LIST,
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


def _signed_cc(
    prefix: str, result: Register, overflow: Register, bits: int
) -> Fragment:
    nonzero, nonzero_ir = _nonzero_bit(f"{prefix}.res", result, bits)
    negative, negative_ir = _sign_bit(prefix, result, bits)
    doubled, doubled_ir = _binop_const(prefix, "nz2", BinopKind.MUL, nonzero, 2)
    base, base_ir = _binop(prefix, "cc_base", BinopKind.SUB, doubled, negative)
    cc, cc_ir = _overflow_cc(prefix, base, overflow)
    return cc, (*nonzero_ir, *negative_ir, *doubled_ir, *base_ir, *cc_ir)


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
    overflow, overflow_ir = _nonzero_bit(f"{func_name}.o", lost, bits)
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


def build_add_signed_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    return _signed_arithmetic_cc_ir(func_name, bits, BinopKind.ADD)


def build_sub_signed_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    return _signed_arithmetic_cc_ir(func_name, bits, BinopKind.SUB)


def build_add_logical_cc_ir(func_name: str, bits: int) -> list[InstructionBase]:
    left, left_ir = _wrap(f"{func_name}.l", PARAM_LEFT, bits)
    right, right_ir = _wrap(f"{func_name}.r", PARAM_RIGHT, bits)
    exact, exact_ir = _binop(func_name, "exact", BinopKind.ADD, left, right)
    result, result_ir = _wrap(f"{func_name}.s", exact, bits)
    carry, carry_ir = _binop_const(func_name, "carry", BinopKind.RSHIFT, exact, bits)
    nonzero, nonzero_ir = _nonzero_bit(func_name, result, bits)
    carry2, carry2_ir = _binop_const(func_name, "carry2", BinopKind.MUL, carry, 2)
    cc, cc_ir = _binop(func_name, "cc", BinopKind.ADD, carry2, nonzero)
    pair, pair_ir = _pair(func_name, result, cc)
    return [
        *left_ir,
        *right_ir,
        *exact_ir,
        *result_ir,
        *carry_ir,
        *nonzero_ir,
        *carry2_ir,
        *cc_ir,
        *pair_ir,
        Return_(value_reg=pair),
    ]
