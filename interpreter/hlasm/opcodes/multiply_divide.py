# pyright: standard
"""Multiply and divide opcodes: truncated and checked products, products into an even-odd pair, and signed and logical divides with their divide exceptions."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import (
    REGISTER_OPERAND,
    Sink,
    Source,
    Transform,
    from_doubleword_pair,
    from_even_odd_pair,
    from_gr32,
    from_gr64,
    from_odd_gr32,
    from_odd_gr64,
    keep,
    sign_extended,
    signed,
    to_doubleword_pair,
    to_even_odd_pair,
    to_gr32,
    to_gr64,
)
from interpreter.hlasm.fixed_point_divide import emit_fixed_point_divide_check
from interpreter.hlasm.fixed_width_ir import (
    build_divide_truncating_ir,
    build_multiply_signed_cc_ir,
)
from interpreter.hlasm.hlasm_constants import (
    DOUBLEWORD_BITS,
    LOW_WORD_MASK,
    PARAM_LEFT,
    PARAM_RIGHT,
    REGISTER_MASK,
    WORD_BITS,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_pair
from interpreter.hlasm.opcodes.even_odd import even_odd
from interpreter.hlasm.opcodes.operand_sources import (
    DOUBLEWORD_STORAGE,
    HALFWORD_IMMEDIATE,
    SIGNED_HALFWORD_STORAGE,
    SIGNED_LOW_WORD,
    SIGNED_WORD_STORAGE,
    WORD_IMMEDIATE,
    WORD_STORAGE,
)
from interpreter.hlasm.opcodes.signed_add_subtract import signed_arithmetic
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type RegisterStore = Callable[[HlasmEmitter, int, Register], None]

MULTIPLY_32 = build_multiply_signed_cc_ir("hlasm.mul32", WORD_BITS)
MULTIPLY_64 = build_multiply_signed_cc_ir("hlasm.mul64", DOUBLEWORD_BITS)
DIVIDE = build_divide_truncating_ir("hlasm.div")

SIGNED_PAIR = sign_extended(from_even_odd_pair, DOUBLEWORD_BITS)
SIGNED_ODD_WORD = sign_extended(from_odd_gr32, WORD_BITS)
SIGNED_ODD_DOUBLEWORD = sign_extended(from_odd_gr64, DOUBLEWORD_BITS)
SIGNED_DOUBLEWORD_STORAGE = sign_extended(DOUBLEWORD_STORAGE, DOUBLEWORD_BITS)
SIGNED_SECOND_DOUBLEWORD = sign_extended(from_gr64(1), DOUBLEWORD_BITS)
SIGNED_THIRD_DOUBLEWORD = sign_extended(from_gr64(2), DOUBLEWORD_BITS)
SIGNED_WORD_QUOTIENT = signed(WORD_BITS)
SIGNED_DOUBLEWORD_QUOTIENT = signed(DOUBLEWORD_BITS)
LOGICAL_WORD_QUOTIENT = keep(LOW_WORD_MASK)
LOGICAL_DOUBLEWORD_QUOTIENT = keep(REGISTER_MASK)


def _product(multiplicand: Source, multiplier: Source, sink: Sink) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        product = emitter.binop(
            BinopKind.MUL,
            multiplicand(emitter, statement),
            multiplier(emitter, statement),
        )
        sink(emitter, statement, product)

    return lower


def _pair_product(
    multiplicand: Source, multiplier: Source, sink: Sink
) -> StatementLowering:
    return even_odd(_product(multiplicand, multiplier, sink))


def _store_word(emitter: HlasmEmitter, r: int, value: Register) -> None:
    emitter.store_gr32(r, value)


def _store_doubleword(emitter: HlasmEmitter, r: int, value: Register) -> None:
    emitter.store_gr64(r, value)


def _divide(
    dividend: Source, divisor: Source, fit: Transform, store: RegisterStore
) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        left, right = dividend(emitter, statement), divisor(emitter, statement)
        emit_fixed_point_divide_check(
            emitter, emitter.binop(BinopKind.EQ, right, emitter.int_(0))
        )
        quotient, remainder = inline_pair(
            emitter, DIVIDE, {PARAM_LEFT: left, PARAM_RIGHT: right}
        )
        emit_fixed_point_divide_check(
            emitter, emitter.binop(BinopKind.NE, fit(emitter, quotient), quotient)
        )
        r1 = reg_operand(statement, REGISTER_OPERAND)
        store(emitter, r1, remainder)
        store(emitter, r1 + 1, quotient)

    return even_odd(lower)


TRUNCATED_PRODUCTS: Mapping[str, StatementLowering] = {
    "MS": _product(from_gr32(0), WORD_STORAGE, to_gr32),
    "MSY": _product(from_gr32(0), WORD_STORAGE, to_gr32),
    "MSR": _product(from_gr32(0), from_gr32(1), to_gr32),
    "MSFI": _product(from_gr32(0), WORD_IMMEDIATE, to_gr32),
    "MH": _product(from_gr32(0), SIGNED_HALFWORD_STORAGE, to_gr32),
    "MHY": _product(from_gr32(0), SIGNED_HALFWORD_STORAGE, to_gr32),
    "MHI": _product(from_gr32(0), HALFWORD_IMMEDIATE, to_gr32),
    "MSG": _product(from_gr64(0), DOUBLEWORD_STORAGE, to_gr64),
    "MSGR": _product(from_gr64(0), from_gr64(1), to_gr64),
    "MSGF": _product(from_gr64(0), SIGNED_WORD_STORAGE, to_gr64),
    "MSGFR": _product(from_gr64(0), SIGNED_LOW_WORD, to_gr64),
    "MSGFI": _product(from_gr64(0), WORD_IMMEDIATE, to_gr64),
    "MGH": _product(from_gr64(0), SIGNED_HALFWORD_STORAGE, to_gr64),
    "MGHI": _product(from_gr64(0), HALFWORD_IMMEDIATE, to_gr64),
}

CHECKED_PRODUCTS: Mapping[str, StatementLowering] = {
    "MSC": signed_arithmetic(MULTIPLY_32, from_gr32(0), WORD_STORAGE, to_gr32),
    "MSRKC": signed_arithmetic(MULTIPLY_32, from_gr32(2), from_gr32(1), to_gr32),
    "MSGC": signed_arithmetic(MULTIPLY_64, from_gr64(0), DOUBLEWORD_STORAGE, to_gr64),
    "MSGRKC": signed_arithmetic(MULTIPLY_64, from_gr64(2), from_gr64(1), to_gr64),
}

PAIR_PRODUCTS: Mapping[str, StatementLowering] = {
    "M": _pair_product(SIGNED_ODD_WORD, SIGNED_WORD_STORAGE, to_even_odd_pair),
    "MFY": _pair_product(SIGNED_ODD_WORD, SIGNED_WORD_STORAGE, to_even_odd_pair),
    "MR": _pair_product(SIGNED_ODD_WORD, SIGNED_LOW_WORD, to_even_odd_pair),
    "ML": _pair_product(from_odd_gr32, WORD_STORAGE, to_even_odd_pair),
    "MLR": _pair_product(from_odd_gr32, from_gr32(1), to_even_odd_pair),
    "MG": _pair_product(
        SIGNED_ODD_DOUBLEWORD, SIGNED_DOUBLEWORD_STORAGE, to_doubleword_pair
    ),
    "MGRK": _pair_product(
        SIGNED_THIRD_DOUBLEWORD, SIGNED_SECOND_DOUBLEWORD, to_doubleword_pair
    ),
    "MLG": _pair_product(from_odd_gr64, DOUBLEWORD_STORAGE, to_doubleword_pair),
    "MLGR": _pair_product(from_odd_gr64, from_gr64(1), to_doubleword_pair),
}

DIVIDES: Mapping[str, StatementLowering] = {
    "D": _divide(SIGNED_PAIR, SIGNED_WORD_STORAGE, SIGNED_WORD_QUOTIENT, _store_word),
    "DR": _divide(SIGNED_PAIR, SIGNED_LOW_WORD, SIGNED_WORD_QUOTIENT, _store_word),
    "DL": _divide(from_even_odd_pair, WORD_STORAGE, LOGICAL_WORD_QUOTIENT, _store_word),
    "DLR": _divide(
        from_even_odd_pair, from_gr32(1), LOGICAL_WORD_QUOTIENT, _store_word
    ),
    "DLG": _divide(
        from_doubleword_pair,
        DOUBLEWORD_STORAGE,
        LOGICAL_DOUBLEWORD_QUOTIENT,
        _store_doubleword,
    ),
    "DLGR": _divide(
        from_doubleword_pair,
        from_gr64(1),
        LOGICAL_DOUBLEWORD_QUOTIENT,
        _store_doubleword,
    ),
    "DSG": _divide(
        SIGNED_ODD_DOUBLEWORD,
        SIGNED_DOUBLEWORD_STORAGE,
        SIGNED_DOUBLEWORD_QUOTIENT,
        _store_doubleword,
    ),
    "DSGR": _divide(
        SIGNED_ODD_DOUBLEWORD,
        SIGNED_SECOND_DOUBLEWORD,
        SIGNED_DOUBLEWORD_QUOTIENT,
        _store_doubleword,
    ),
    "DSGF": _divide(
        SIGNED_ODD_DOUBLEWORD,
        SIGNED_WORD_STORAGE,
        SIGNED_DOUBLEWORD_QUOTIENT,
        _store_doubleword,
    ),
    "DSGFR": _divide(
        SIGNED_ODD_DOUBLEWORD,
        SIGNED_LOW_WORD,
        SIGNED_DOUBLEWORD_QUOTIENT,
        _store_doubleword,
    ),
}

MULTIPLY_DIVIDE_LOWERINGS: Mapping[str, StatementLowering] = {
    **TRUNCATED_PRODUCTS,
    **CHECKED_PRODUCTS,
    **PAIR_PRODUCTS,
    **DIVIDES,
}
