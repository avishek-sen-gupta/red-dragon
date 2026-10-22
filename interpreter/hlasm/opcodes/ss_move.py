# pyright: standard
"""Storage moves: MVC and its inverse, numeric, zone, right-to-left and offset forms, the immediate stores, the long moves and MOVE STRING; the CC is unchanged except by the long moves and MOVE STRING."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_loop import copy_byte, emit_byte_loop, emit_counted_loop
from interpreter.hlasm.byte_one_layouts import (
    IMMEDIATE_BYTE,
    LENGTH_BYTE,
    LENGTH_NIBBLES,
)
from interpreter.hlasm.data_field import DataField, LowerWithField
from interpreter.hlasm.data_movement import (
    FIRST_OPERAND,
    SECOND_OPERAND,
    move,
    to_storage_at,
)
from interpreter.hlasm.effective_address import (
    effective_address,
    length_operand_address,
)
from interpreter.hlasm.field_lowering import (
    FieldLowering,
    with_field_source,
    written_lowerings,
)
from interpreter.hlasm.hlasm_constants import (
    BYTE_MASK,
    DOUBLEWORD_BYTES,
    HALFWORD_BYTES,
    MAKE_LIST,
    NIBBLE_BITS,
    NIBBLE_MASK,
    OFFSET_CARRY_VAR,
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
from interpreter.hlasm.operand_overlap import starts_inside_source
from interpreter.hlasm.operands import storage_length_operand, storage_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.unit_value import UnitReader, unit_reader
from interpreter.instructions import Branch, BranchIf, Label_, LoadIndex, StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Addresses = tuple[Register, Register]
type NibbleConstants = tuple[Register, Register, Register, Register]
type ByteSite = tuple[Register, Register, Register]
type NibbleShift = tuple[Register, Register]

LENGTH_REGISTER = 0
NUMERICS = 0x0F
FIRST_NIBBLE = (NIBBLE_BITS, NIBBLE_BITS)
SECOND_NIBBLE = (0, NIBBLE_BITS)
ZONES = 0xF0


def _field(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> tuple[Addresses, DataField]:
    first = storage_length_operand(statement, FIRST_OPERAND)
    target = length_operand_address(emitter, first)
    source = effective_address(emitter, storage_operand(statement, SECOND_OPERAND))
    return (target, source), field.length(emitter)


def _move_characters(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> None:
    addresses, length = _field(emitter, statement, field)
    bytewise, blockwise, done = (
        emitter.fresh_label(prefix)
        for prefix in ("hl_mvc_bytes", "hl_mvc_block", "hl_mvc_done")
    )
    inside = starts_inside_source(emitter, addresses, length.value(emitter))
    emitter.emit_inst(BranchIf(cond_reg=inside, branch_targets=(bytewise, blockwise)))
    emitter.emit_inst(Label_(label=bytewise))
    emit_byte_loop(
        emitter, length.value(emitter), lambda at: copy_byte(emitter, addresses, at)
    )
    emitter.emit_inst(Branch(label=done))
    emitter.emit_inst(Label_(label=blockwise))
    length.copied(emitter, addresses)
    emitter.emit_inst(Label_(label=done))


def _copy_inverted(
    emitter: HlasmEmitter, addresses: Addresses, no_offset: Register, at: Register
) -> None:
    target, source_right = addresses
    mirrored = emitter.binop(BinopKind.SUB, source_right, at)
    image = emitter.load_bytes(mirrored, no_offset, ONE_BYTE)
    emitter.write_bytes(target, at, ONE_BYTE, image)


def _move_inverse(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> None:
    addresses, length = _field(emitter, statement, field)
    no_offset = emitter.int_(0)
    emit_byte_loop(
        emitter,
        length.value(emitter),
        lambda at: _copy_inverted(emitter, addresses, no_offset, at),
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


def _nibbles(moved: int) -> LowerWithField:
    def lower(
        emitter: HlasmEmitter, statement: MachineStatement, field: DataField
    ) -> None:
        addresses, length = _field(emitter, statement, field)
        constants = (
            emitter.int_(0),
            emitter.int_(ONE_BYTE),
            emitter.int_(BYTE_MASK ^ moved),
            emitter.int_(moved),
        )
        emit_byte_loop(
            emitter,
            length.value(emitter),
            lambda at: _merge_byte(emitter, addresses, constants, at),
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


def _store_offset_byte(
    emitter: HlasmEmitter, site: ByteSite, at: Register, value: Register
) -> None:
    target, last, single = site
    image = emitter.call(MAKE_LIST, (single, value))
    emitter.write_bytes(target, emitter.binop(BinopKind.SUB, last, at), ONE_BYTE, image)


def _offset_byte(
    emitter: HlasmEmitter,
    site: ByteSite,
    nibble: NibbleShift,
    source: tuple[Register, Register, UnitReader],
    at: Register,
) -> None:
    address, source_last, read = source
    mask, bits = nibble
    fetched = read(address, emitter.binop(BinopKind.SUB, source_last, at))
    shifted = emitter.binop(
        BinopKind.LSHIFT, emitter.binop(BinopKind.BIT_AND, fetched, mask), bits
    )
    result = emitter.binop(
        BinopKind.BIT_OR, shifted, emitter.load_var(OFFSET_CARRY_VAR)
    )
    _store_offset_byte(emitter, site, at, result)
    carry = emitter.binop(BinopKind.RSHIFT, fetched, bits)
    emitter.emit_inst(StoreVar(name=OFFSET_CARRY_VAR, value_reg=carry))


def _zero_extended_byte(
    emitter: HlasmEmitter, site: ByteSite, no_carry: Register, at: Register
) -> None:
    _store_offset_byte(emitter, site, at, emitter.load_var(OFFSET_CARRY_VAR))
    emitter.emit_inst(StoreVar(name=OFFSET_CARRY_VAR, value_reg=no_carry))


def _zero_extend(
    emitter: HlasmEmitter, site: ByteSite, span: tuple[Register, Register]
) -> None:
    no_carry = emitter.int_(0)
    emit_counted_loop(
        emitter,
        span,
        ONE_BYTE,
        lambda at: _zero_extended_byte(emitter, site, no_carry, at),
    )


def _keep_sign(emitter: HlasmEmitter, last_byte: Register, mask: Register) -> None:
    kept = emitter.binop(BinopKind.BIT_AND, last_byte, mask)
    emitter.emit_inst(StoreVar(name=OFFSET_CARRY_VAR, value_reg=kept))


def _offset_addresses(emitter: HlasmEmitter, statement: MachineStatement) -> Addresses:
    return (
        length_operand_address(
            emitter, storage_length_operand(statement, FIRST_OPERAND)
        ),
        length_operand_address(
            emitter, storage_length_operand(statement, SECOND_OPERAND)
        ),
    )


def _move_with_offset(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> None:
    target, source = _offset_addresses(emitter, statement)
    first_code = field.part(emitter, NIBBLE_BITS, NIBBLE_BITS)
    site = (target, first_code.value(emitter), emitter.int_(ONE_BYTE))
    read = unit_reader(emitter, ONE_BYTE)
    nibble = (emitter.int_(NIBBLE_MASK), emitter.int_(NIBBLE_BITS))
    _keep_sign(emitter, read(target, site[1]), nibble[0])
    common = field.shorter(emitter, (FIRST_NIBBLE, SECOND_NIBBLE)).value(emitter)
    sourced = (source, field.part(emitter, *SECOND_NIBBLE).value(emitter), read)
    emit_byte_loop(
        emitter, common, lambda at: _offset_byte(emitter, site, nibble, sourced, at)
    )
    _zero_extend(emitter, site, (common, first_code.length(emitter).value(emitter)))


def _store_immediate(width: int) -> StatementLowering:
    return move(HALFWORD_IMMEDIATE, (), to_storage_at(FIRST_OPERAND, width))


STORE_IMMEDIATE_BYTE = FieldLowering(
    IMMEDIATE_BYTE,
    with_field_source(
        lambda immediate: move(immediate, (), to_storage_at(FIRST_OPERAND, ONE_BYTE))
    ),
)

SS_MOVE_FIELD_LOWERINGS: Mapping[str, FieldLowering] = {
    "MVI": STORE_IMMEDIATE_BYTE,
    "MVIY": STORE_IMMEDIATE_BYTE,
    "MVC": FieldLowering(LENGTH_BYTE, _move_characters),
    "MVCIN": FieldLowering(LENGTH_BYTE, _move_inverse),
    "MVN": FieldLowering(LENGTH_BYTE, _nibbles(NUMERICS)),
    "MVZ": FieldLowering(LENGTH_BYTE, _nibbles(ZONES)),
    "MVO": FieldLowering(LENGTH_NIBBLES, _move_with_offset),
}

SS_MOVE_LOWERINGS: Mapping[str, StatementLowering] = {
    **written_lowerings(SS_MOVE_FIELD_LOWERINGS),
    "MVHHI": _store_immediate(HALFWORD_BYTES),
    "MVHI": _store_immediate(WORD_BYTES),
    "MVGHI": _store_immediate(DOUBLEWORD_BYTES),
    "MVCRL": _move_right_to_left,
    "MVCL": MOVE_LONG,
    "MVCLE": MOVE_LONG_EXTENDED,
    "MVCLU": MOVE_LONG_UNICODE,
    "MVST": move_string,
}
