# pyright: standard
"""Signed add and subtract opcodes: register, storage, halfword and immediate operands, 32 and 64 bits, CC and overflow."""

from collections.abc import Callable, Mapping, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import (
    Sink,
    Source,
    from_gr32,
    from_gr64,
    storage_immediate,
    to_gr32,
    to_gr64,
)
from interpreter.hlasm.fixed_point_overflow import emit_fixed_point_overflow_check
from interpreter.hlasm.fixed_width_ir import (
    build_add_signed_cc_ir,
    build_sub_signed_cc_ir,
)
from interpreter.hlasm.hlasm_constants import (
    DOUBLEWORD_BITS,
    DOUBLEWORD_BYTES,
    PARAM_LEFT,
    PARAM_RIGHT,
    WORD_BITS,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_pair
from interpreter.hlasm.opcodes.operand_sources import (
    DOUBLEWORD_STORAGE,
    HALFWORD_IMMEDIATE,
    SIGNED_HALFWORD_STORAGE,
    SIGNED_LOW_WORD,
    SIGNED_WORD_STORAGE,
    THIRD_HALFWORD_IMMEDIATE,
    WORD_IMMEDIATE,
    WORD_STORAGE,
)
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import InstructionBase
from interpreter.register import Register

type Operation = Sequence[InstructionBase]


ADD_32 = build_add_signed_cc_ir("hlasm.add32", WORD_BITS)
ADD_64 = build_add_signed_cc_ir("hlasm.add64", DOUBLEWORD_BITS)
SUB_32 = build_sub_signed_cc_ir("hlasm.sub32", WORD_BITS)
SUB_64 = build_sub_signed_cc_ir("hlasm.sub64", DOUBLEWORD_BITS)


def _apply(
    emitter: HlasmEmitter,
    operation: Operation,
    operands: tuple[Register, Register],
    store: Callable[[Register], None],
) -> None:
    left, right = operands
    result, cc = inline_pair(emitter, operation, {PARAM_LEFT: left, PARAM_RIGHT: right})
    store(result)
    emitter.set_cc(cc)
    emit_fixed_point_overflow_check(emitter, cc)


def signed_arithmetic(
    operation: Operation, left: Source, right: Source, sink: Sink
) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        _apply(
            emitter,
            operation,
            (left(emitter, statement), right(emitter, statement)),
            lambda value: sink(emitter, statement, value),
        )

    return lower


def to_storage_immediate(operation: Operation, width: int) -> StatementLowering:
    return storage_immediate(
        width,
        lambda emitter, operands, store: _apply(emitter, operation, operands, store),
    )


def _word(operation: Operation, left: Source, right: Source) -> StatementLowering:
    return signed_arithmetic(operation, left, right, to_gr32)


def _doubleword(operation: Operation, left: Source, right: Source) -> StatementLowering:
    return signed_arithmetic(operation, left, right, to_gr64)


ADDS: Mapping[str, StatementLowering] = {
    "A": _word(ADD_32, from_gr32(0), WORD_STORAGE),
    "AY": _word(ADD_32, from_gr32(0), WORD_STORAGE),
    "AR": _word(ADD_32, from_gr32(0), from_gr32(1)),
    "ARK": _word(ADD_32, from_gr32(1), from_gr32(2)),
    "AH": _word(ADD_32, from_gr32(0), SIGNED_HALFWORD_STORAGE),
    "AHY": _word(ADD_32, from_gr32(0), SIGNED_HALFWORD_STORAGE),
    "AHI": _word(ADD_32, from_gr32(0), HALFWORD_IMMEDIATE),
    "AFI": _word(ADD_32, from_gr32(0), WORD_IMMEDIATE),
    "AHIK": _word(ADD_32, from_gr32(1), THIRD_HALFWORD_IMMEDIATE),
    "ASI": to_storage_immediate(ADD_32, WORD_BYTES),
    "AG": _doubleword(ADD_64, from_gr64(0), DOUBLEWORD_STORAGE),
    "AGR": _doubleword(ADD_64, from_gr64(0), from_gr64(1)),
    "AGRK": _doubleword(ADD_64, from_gr64(1), from_gr64(2)),
    "AGF": _doubleword(ADD_64, from_gr64(0), SIGNED_WORD_STORAGE),
    "AGFR": _doubleword(ADD_64, from_gr64(0), SIGNED_LOW_WORD),
    "AGH": _doubleword(ADD_64, from_gr64(0), SIGNED_HALFWORD_STORAGE),
    "AGHI": _doubleword(ADD_64, from_gr64(0), HALFWORD_IMMEDIATE),
    "AGFI": _doubleword(ADD_64, from_gr64(0), WORD_IMMEDIATE),
    "AGHIK": _doubleword(ADD_64, from_gr64(1), THIRD_HALFWORD_IMMEDIATE),
    "AGSI": to_storage_immediate(ADD_64, DOUBLEWORD_BYTES),
}

SUBTRACTS: Mapping[str, StatementLowering] = {
    "S": _word(SUB_32, from_gr32(0), WORD_STORAGE),
    "SY": _word(SUB_32, from_gr32(0), WORD_STORAGE),
    "SR": _word(SUB_32, from_gr32(0), from_gr32(1)),
    "SRK": _word(SUB_32, from_gr32(1), from_gr32(2)),
    "SH": _word(SUB_32, from_gr32(0), SIGNED_HALFWORD_STORAGE),
    "SHY": _word(SUB_32, from_gr32(0), SIGNED_HALFWORD_STORAGE),
    "SG": _doubleword(SUB_64, from_gr64(0), DOUBLEWORD_STORAGE),
    "SGR": _doubleword(SUB_64, from_gr64(0), from_gr64(1)),
    "SGRK": _doubleword(SUB_64, from_gr64(1), from_gr64(2)),
    "SGF": _doubleword(SUB_64, from_gr64(0), SIGNED_WORD_STORAGE),
    "SGFR": _doubleword(SUB_64, from_gr64(0), SIGNED_LOW_WORD),
    "SGH": _doubleword(SUB_64, from_gr64(0), SIGNED_HALFWORD_STORAGE),
}

SIGNED_ADD_SUBTRACT_LOWERINGS: Mapping[str, StatementLowering] = {
    **ADDS,
    **SUBTRACTS,
}
