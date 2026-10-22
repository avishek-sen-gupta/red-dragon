# pyright: standard
"""Storage moves: MVC and its inverse, numeric, zone, right-to-left and offset forms, the immediate stores, the long moves and MOVE STRING; the CC is unchanged except by the long moves and MOVE STRING."""

from collections.abc import Mapping
from functools import reduce

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_loop import copy_byte, emit_byte_loop, emit_counted_loop
from interpreter.hlasm.data_movement import (
    FIRST_OPERAND,
    SECOND_OPERAND,
    immediate,
    move,
    to_storage_at,
)
from interpreter.hlasm.effective_address import (
    effective_address,
    length_operand_address,
)
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    BYTE_MASK,
    DOUBLEWORD_BYTES,
    HALFWORD_BYTES,
    MAKE_LIST,
    NIBBLE_BITS,
    NIBBLE_MASK,
    ONE_BYTE,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_move import (
    MOVE_LONG,
    MOVE_LONG_EXTENDED,
    MOVE_LONG_UNICODE,
)
from interpreter.hlasm.move_string import move_string
from interpreter.hlasm.opcodes.operand_sources import HALFWORD_IMMEDIATE
from interpreter.hlasm.operands import storage_length_operand, storage_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.instructions import Branch, BranchIf, Label_, LoadIndex
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Addresses = tuple[Register, Register]
type NibbleConstants = tuple[Register, Register, Register, Register]

LENGTH_REGISTER = 0
NUMERICS = 0x0F
ZONES = 0xF0


def _field(emitter: HlasmEmitter, statement: MachineStatement) -> tuple[Addresses, int]:
    first = storage_length_operand(statement, FIRST_OPERAND)
    target = length_operand_address(emitter, first)
    source = effective_address(emitter, storage_operand(statement, SECOND_OPERAND))
    return (target, source), max(first.length, ONE_BYTE)


def _starts_inside(
    emitter: HlasmEmitter, addresses: Addresses, length: int
) -> Register:
    target, source = addresses
    source_end = emitter.binop(BinopKind.ADD, source, emitter.int_(length))
    return emitter.binop(
        BinopKind.AND,
        emitter.binop(BinopKind.LT, source, target),
        emitter.binop(BinopKind.LT, target, source_end),
    )


def _block_copy(emitter: HlasmEmitter, addresses: Addresses, length: int) -> None:
    target, source = addresses
    start = emitter.int_(0)
    emitter.write_bytes(
        target, start, length, emitter.load_bytes(source, start, length)
    )


def _move_characters(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    addresses, length = _field(emitter, statement)
    bytewise, blockwise, done = (
        emitter.fresh_label(prefix)
        for prefix in ("hl_mvc_bytes", "hl_mvc_block", "hl_mvc_done")
    )
    inside = _starts_inside(emitter, addresses, length)
    emitter.emit_inst(BranchIf(cond_reg=inside, branch_targets=(bytewise, blockwise)))
    emitter.emit_inst(Label_(label=bytewise))
    emit_byte_loop(emitter, length, lambda at: copy_byte(emitter, addresses, at))
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=blockwise))
    _block_copy(emitter, addresses, length)
    emitter.emit_inst(Label_(label=done))


def _copy_inverted(
    emitter: HlasmEmitter, addresses: Addresses, start: Register, at: Register
) -> None:
    target, source_right = addresses
    back = emitter.binop(BinopKind.SUB, start, at)
    image = emitter.load_bytes(source_right, back, ONE_BYTE)
    emitter.write_bytes(target, at, ONE_BYTE, image)


def _move_inverse(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    addresses, length = _field(emitter, statement)
    start = emitter.int_(0)
    emit_byte_loop(
        emitter, length, lambda at: _copy_inverted(emitter, addresses, start, at)
    )


def _byte_value(emitter: HlasmEmitter, image: Register, index: Register) -> Register:
    value = emitter.fresh_reg()
    emitter.emit_inst(LoadIndex(result_reg=value, arr_reg=image, index_reg=index))
    return value


def _merge_byte(
    emitter: HlasmEmitter,
    addresses: Addresses,
    constants: NibbleConstants,
    at: Register,
) -> None:
    target, source = addresses
    index, single, kept, moved = constants
    old = _byte_value(emitter, emitter.load_bytes(target, at, ONE_BYTE), index)
    new = _byte_value(emitter, emitter.load_bytes(source, at, ONE_BYTE), index)
    merged = emitter.binop(
        BinopKind.BIT_OR,
        emitter.binop(BinopKind.BIT_AND, old, kept),
        emitter.binop(BinopKind.BIT_AND, new, moved),
    )
    emitter.write_bytes(target, at, ONE_BYTE, emitter.call(MAKE_LIST, (single, merged)))


def _nibbles(moved: int) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        addresses, length = _field(emitter, statement)
        constants = (
            emitter.int_(0),
            emitter.int_(ONE_BYTE),
            emitter.int_(BYTE_MASK ^ moved),
            emitter.int_(moved),
        )
        emit_byte_loop(
            emitter, length, lambda at: _merge_byte(emitter, addresses, constants, at)
        )

    return lower


def _move_right_to_left(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    addresses = (
        effective_address(emitter, storage_operand(statement, FIRST_OPERAND)),
        effective_address(emitter, storage_operand(statement, SECOND_OPERAND)),
    )
    last = emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_gr32(LENGTH_REGISTER),
        emitter.int_(BYTE_MASK),
    )
    count = emitter.binop(BinopKind.ADD, last, emitter.int_(ONE_BYTE))
    emit_counted_loop(
        emitter,
        (emitter.int_(0), count),
        ONE_BYTE,
        lambda at: copy_byte(
            emitter, addresses, emitter.binop(BinopKind.SUB, last, at)
        ),
    )


def _source_byte(emitter: HlasmEmitter, source: Register, offset: int) -> Register:
    if offset < 0:
        return emitter.int_(0)
    return emitter.load_storage(source, offset, ONE_BYTE)


def _offset_byte(
    emitter: HlasmEmitter,
    addresses: Addresses,
    rightmost: tuple[int, int],
    carry: Register,
) -> Register:
    target, source = addresses
    target_at, source_at = rightmost
    fetched = _source_byte(emitter, source, source_at)
    digit = emitter.binop(BinopKind.BIT_AND, fetched, emitter.int_(NIBBLE_MASK))
    shifted = emitter.binop(BinopKind.LSHIFT, digit, emitter.int_(NIBBLE_BITS))
    result = emitter.binop(BinopKind.BIT_OR, shifted, carry)
    emitter.store_storage(target, target_at, ONE_BYTE, result)
    return emitter.binop(BinopKind.RSHIFT, fetched, emitter.int_(NIBBLE_BITS))


def _move_with_offset(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    first = storage_length_operand(statement, FIRST_OPERAND)
    second = storage_length_operand(statement, SECOND_OPERAND)
    addresses = (
        length_operand_address(emitter, first),
        length_operand_address(emitter, second),
    )
    last, source_last = (
        max(first.length, ONE_BYTE) - 1,
        max(second.length, ONE_BYTE) - 1,
    )
    kept = emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_storage(addresses[0], last, ONE_BYTE),
        emitter.int_(NIBBLE_MASK),
    )
    reduce(
        lambda carry, step: _offset_byte(
            emitter, addresses, (last - step, source_last - step), carry
        ),
        range(last + 1),
        kept,
    )


def _store_immediate(width: int) -> StatementLowering:
    return move(HALFWORD_IMMEDIATE, (), to_storage_at(FIRST_OPERAND, width))


SS_MOVE_LOWERINGS: Mapping[str, StatementLowering] = {
    "MVI": move(immediate(BITS_PER_BYTE), (), to_storage_at(FIRST_OPERAND, ONE_BYTE)),
    "MVIY": move(immediate(BITS_PER_BYTE), (), to_storage_at(FIRST_OPERAND, ONE_BYTE)),
    "MVHHI": _store_immediate(HALFWORD_BYTES),
    "MVHI": _store_immediate(WORD_BYTES),
    "MVGHI": _store_immediate(DOUBLEWORD_BYTES),
    "MVC": _move_characters,
    "MVCIN": _move_inverse,
    "MVN": _nibbles(NUMERICS),
    "MVZ": _nibbles(ZONES),
    "MVCRL": _move_right_to_left,
    "MVO": _move_with_offset,
    "MVCL": MOVE_LONG,
    "MVCLE": MOVE_LONG_EXTENDED,
    "MVCLU": MOVE_LONG_UNICODE,
    "MVST": move_string,
}
