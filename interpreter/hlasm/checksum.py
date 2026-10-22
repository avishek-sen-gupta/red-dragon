# pyright: standard
"""CKSM: the words at R2 for R2+1's length, the last padded with zeros, added into R1's low word with an end-around carry, in one execution (ruling R28)."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_loop import emit_counted_loop
from interpreter.hlasm.effective_address import register_address
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    CHECKSUM_TAIL_VAR,
    CHECKSUM_VAR,
    LOW_WORD_MASK,
    ONE_BYTE,
    WORD_BITS,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_registers import store_progress
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.unit_value import unit_reader
from interpreter.instructions import StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

SECOND_OPERAND = 1
WHOLE_WORDS = LOW_WORD_MASK & ~(WORD_BYTES - 1)
COMPLETE_CC = 0
BYTE_SCALE = 1 << BITS_PER_BYTE


def _accumulate(emitter: HlasmEmitter, element: Register) -> None:
    total = emitter.binop(BinopKind.ADD, emitter.load_var(CHECKSUM_VAR), element)
    low = emitter.binop(BinopKind.BIT_AND, total, emitter.int_(LOW_WORD_MASK))
    carry = emitter.binop(BinopKind.RSHIFT, total, emitter.int_(WORD_BITS))
    folded = emitter.binop(BinopKind.ADD, low, carry)
    emitter.emit_inst(StoreVar(name=CHECKSUM_VAR, value_reg=folded))


def _append_byte(emitter: HlasmEmitter, byte: Register) -> None:
    shifted = emitter.binop(
        BinopKind.MUL, emitter.load_var(CHECKSUM_TAIL_VAR), emitter.int_(BYTE_SCALE)
    )
    appended = emitter.binop(BinopKind.ADD, shifted, byte)
    emitter.emit_inst(StoreVar(name=CHECKSUM_TAIL_VAR, value_reg=appended))


def _padded_tail(emitter: HlasmEmitter, whole: Register, length: Register) -> Register:
    missing = emitter.binop(
        BinopKind.SUB,
        emitter.binop(BinopKind.ADD, whole, emitter.int_(WORD_BYTES)),
        length,
    )
    bits = emitter.binop(BinopKind.MUL, missing, emitter.int_(BITS_PER_BYTE))
    return emitter.binop(BinopKind.LSHIFT, emitter.load_var(CHECKSUM_TAIL_VAR), bits)


def _sum_words(emitter: HlasmEmitter, address: Register, whole: Register) -> None:
    word = unit_reader(emitter, WORD_BYTES)
    emit_counted_loop(
        emitter,
        (emitter.int_(0), whole),
        WORD_BYTES,
        lambda at: _accumulate(emitter, word(address, at)),
    )


def _sum_tail(
    emitter: HlasmEmitter, address: Register, span: tuple[Register, Register]
) -> None:
    byte = unit_reader(emitter, ONE_BYTE)
    emitter.emit_inst(StoreVar(name=CHECKSUM_TAIL_VAR, value_reg=emitter.int_(0)))
    emit_counted_loop(
        emitter, span, ONE_BYTE, lambda at: _append_byte(emitter, byte(address, at))
    )
    _accumulate(emitter, _padded_tail(emitter, *span))


def lower_checksum(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    r1, r2 = reg_operand(statement, 0), reg_operand(statement, SECOND_OPERAND)
    address = register_address(emitter, r2)
    length = emitter.load_gr32(r2 + 1)
    whole = emitter.binop(BinopKind.BIT_AND, length, emitter.int_(WHOLE_WORDS))
    emitter.emit_inst(StoreVar(name=CHECKSUM_VAR, value_reg=emitter.load_gr32(r1)))
    _sum_words(emitter, address, whole)
    _sum_tail(emitter, address, (whole, length))
    emitter.store_gr32(r1, emitter.load_var(CHECKSUM_VAR))
    store_progress(
        emitter, r2, emitter.binop(BinopKind.ADD, address, length), emitter.int_(0)
    )
    emitter.set_cc(emitter.int_(COMPLETE_CC))
