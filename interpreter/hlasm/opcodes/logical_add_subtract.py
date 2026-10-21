# pyright: standard
"""Logical add and subtract opcodes: unsigned register, storage and immediate operands, 32 and 64 bits, carry and borrow."""

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
from interpreter.hlasm.fixed_width_ir import (
    build_add_logical_carry_cc_ir,
    build_add_logical_cc_ir,
    build_sub_logical_borrow_cc_ir,
)
from interpreter.hlasm.hlasm_constants import (
    CC_VAR,
    DOUBLEWORD_BITS,
    DOUBLEWORD_BYTES,
    PARAM_CARRY,
    PARAM_LEFT,
    PARAM_RIGHT,
    WORD_BITS,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.inline_ir import inline_result_and_cc
from interpreter.hlasm.opcodes.operand_sources import (
    DOUBLEWORD_STORAGE,
    LOGICAL_WORD_IMMEDIATE,
    THIRD_HALFWORD_IMMEDIATE,
    WORD_STORAGE,
)
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import InstructionBase
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Operation = Sequence[InstructionBase]

CARRY_CC_SHIFT = 1
NO_BORROW = 1

ADD_32 = build_add_logical_cc_ir("hlasm.addl32", WORD_BITS)
ADD_64 = build_add_logical_cc_ir("hlasm.addl64", DOUBLEWORD_BITS)
ADD_CARRY_32 = build_add_logical_carry_cc_ir("hlasm.addlc32", WORD_BITS)
ADD_CARRY_64 = build_add_logical_carry_cc_ir("hlasm.addlc64", DOUBLEWORD_BITS)
SUB_BORROW_32 = build_sub_logical_borrow_cc_ir("hlasm.sublb32", WORD_BITS)
SUB_BORROW_64 = build_sub_logical_borrow_cc_ir("hlasm.sublb64", DOUBLEWORD_BITS)


def carry_in(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    return emitter.binop(
        BinopKind.RSHIFT, emitter.load_var(CC_VAR), emitter.int_(CARRY_CC_SHIFT)
    )


def no_borrow(emitter: HlasmEmitter, statement: MachineStatement) -> Register:
    return emitter.int_(NO_BORROW)


def _apply(
    emitter: HlasmEmitter,
    operation: Operation,
    arguments: Mapping[Register, Register],
    store: Callable[[Register], None],
) -> None:
    result, cc = inline_result_and_cc(emitter, operation, arguments)
    store(result)
    emitter.set_cc(cc)


def logical_arithmetic(
    operation: Operation, operands: Sequence[tuple[Register, Source]], sink: Sink
) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        arguments = {param: source(emitter, statement) for param, source in operands}
        _apply(
            emitter,
            operation,
            arguments,
            lambda value: sink(emitter, statement, value),
        )

    return lower


def to_storage_immediate(operation: Operation, width: int) -> StatementLowering:
    return storage_immediate(
        width,
        lambda emitter, operands, store: _apply(
            emitter,
            operation,
            {PARAM_LEFT: operands[0], PARAM_RIGHT: operands[1]},
            store,
        ),
    )


def _sum(
    operation: Operation, sink: Sink
) -> Callable[[Source, Source], StatementLowering]:
    return lambda left, right: logical_arithmetic(
        operation, ((PARAM_LEFT, left), (PARAM_RIGHT, right)), sink
    )


def _carried(
    operation: Operation, sink: Sink, carry: Source
) -> Callable[[Source, Source], StatementLowering]:
    return lambda left, right: logical_arithmetic(
        operation,
        ((PARAM_LEFT, left), (PARAM_RIGHT, right), (PARAM_CARRY, carry)),
        sink,
    )


ADD_WORD = _sum(ADD_32, to_gr32)
ADD_DOUBLEWORD = _sum(ADD_64, to_gr64)
ADD_CARRY_WORD = _carried(ADD_CARRY_32, to_gr32, carry_in)
ADD_CARRY_DOUBLEWORD = _carried(ADD_CARRY_64, to_gr64, carry_in)
SUB_WORD = _carried(SUB_BORROW_32, to_gr32, no_borrow)
SUB_DOUBLEWORD = _carried(SUB_BORROW_64, to_gr64, no_borrow)
SUB_BORROW_WORD = _carried(SUB_BORROW_32, to_gr32, carry_in)
SUB_BORROW_DOUBLEWORD = _carried(SUB_BORROW_64, to_gr64, carry_in)

ADDS: Mapping[str, StatementLowering] = {
    "AL": ADD_WORD(from_gr32(0), WORD_STORAGE),
    "ALY": ADD_WORD(from_gr32(0), WORD_STORAGE),
    "ALR": ADD_WORD(from_gr32(0), from_gr32(1)),
    "ALRK": ADD_WORD(from_gr32(1), from_gr32(2)),
    "ALFI": ADD_WORD(from_gr32(0), LOGICAL_WORD_IMMEDIATE),
    "ALHSIK": ADD_WORD(from_gr32(1), THIRD_HALFWORD_IMMEDIATE),
    "ALSI": to_storage_immediate(ADD_32, WORD_BYTES),
    "ALG": ADD_DOUBLEWORD(from_gr64(0), DOUBLEWORD_STORAGE),
    "ALGR": ADD_DOUBLEWORD(from_gr64(0), from_gr64(1)),
    "ALGRK": ADD_DOUBLEWORD(from_gr64(1), from_gr64(2)),
    "ALGF": ADD_DOUBLEWORD(from_gr64(0), WORD_STORAGE),
    "ALGFR": ADD_DOUBLEWORD(from_gr64(0), from_gr32(1)),
    "ALGFI": ADD_DOUBLEWORD(from_gr64(0), LOGICAL_WORD_IMMEDIATE),
    "ALGHSIK": ADD_DOUBLEWORD(from_gr64(1), THIRD_HALFWORD_IMMEDIATE),
    "ALGSI": to_storage_immediate(ADD_64, DOUBLEWORD_BYTES),
    "ALC": ADD_CARRY_WORD(from_gr32(0), WORD_STORAGE),
    "ALCR": ADD_CARRY_WORD(from_gr32(0), from_gr32(1)),
    "ALCG": ADD_CARRY_DOUBLEWORD(from_gr64(0), DOUBLEWORD_STORAGE),
    "ALCGR": ADD_CARRY_DOUBLEWORD(from_gr64(0), from_gr64(1)),
}

SUBTRACTS: Mapping[str, StatementLowering] = {
    "SL": SUB_WORD(from_gr32(0), WORD_STORAGE),
    "SLY": SUB_WORD(from_gr32(0), WORD_STORAGE),
    "SLR": SUB_WORD(from_gr32(0), from_gr32(1)),
    "SLRK": SUB_WORD(from_gr32(1), from_gr32(2)),
    "SLFI": SUB_WORD(from_gr32(0), LOGICAL_WORD_IMMEDIATE),
    "SLG": SUB_DOUBLEWORD(from_gr64(0), DOUBLEWORD_STORAGE),
    "SLGR": SUB_DOUBLEWORD(from_gr64(0), from_gr64(1)),
    "SLGRK": SUB_DOUBLEWORD(from_gr64(1), from_gr64(2)),
    "SLGF": SUB_DOUBLEWORD(from_gr64(0), WORD_STORAGE),
    "SLGFR": SUB_DOUBLEWORD(from_gr64(0), from_gr32(1)),
    "SLGFI": SUB_DOUBLEWORD(from_gr64(0), LOGICAL_WORD_IMMEDIATE),
    "SLB": SUB_BORROW_WORD(from_gr32(0), WORD_STORAGE),
    "SLBR": SUB_BORROW_WORD(from_gr32(0), from_gr32(1)),
    "SLBG": SUB_BORROW_DOUBLEWORD(from_gr64(0), DOUBLEWORD_STORAGE),
    "SLBGR": SUB_BORROW_DOUBLEWORD(from_gr64(0), from_gr64(1)),
}

LOGICAL_ADD_SUBTRACT_LOWERINGS: Mapping[str, StatementLowering] = {
    **ADDS,
    **SUBTRACTS,
}
