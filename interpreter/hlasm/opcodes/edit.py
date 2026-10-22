# pyright: standard
"""Edit: ED and EDMK replace a pattern left to right by zoned source digits, fill bytes and message bytes under a significance indicator; the source is walked once to check its digits before any store, and EDMK puts in GR1 the address of the first significant digit of the rightmost field."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_loop import emit_byte_loop
from interpreter.hlasm.byte_one_layouts import LENGTH_BYTE
from interpreter.hlasm.conditional import emit_either, emit_when
from interpreter.hlasm.data_field import DataField
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.decimal_exceptions import emit_data_check
from interpreter.hlasm.edit_operands import EditOperands
from interpreter.hlasm.effective_address import (
    effective_address,
    length_operand_address,
)
from interpreter.hlasm.field_lowering import FieldLowering, written_lowerings
from interpreter.hlasm.hlasm_constants import (
    DECIMAL_INVALID_VAR,
    EDIT_DIGIT_VAR,
    EDIT_MARK_VAR,
    EDIT_NONZERO_VAR,
    EDIT_PENDING_VAR,
    EDIT_PLUS_VAR,
    EDIT_SIGNIFICANCE_VAR,
    EDIT_SOURCE_AT_VAR,
    NIBBLE_BITS,
    NIBBLE_MASK,
    ONE_BYTE,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_registers import store_address
from interpreter.hlasm.operands import storage_length_operand, storage_operand
from interpreter.hlasm.packed_decimal import PLUS_SIGNS, table_bit
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.hlasm.unit_value import unit_reader
from interpreter.instructions import StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register
from interpreter.var_name import VarName

type Marker = Callable[[Register, Register], None]

DIGIT_SELECTOR = 0x20
SIGNIFICANCE_STARTER = 0x21
FIELD_SEPARATOR = 0x22
ZONE = 0xF0
LARGEST_DIGIT = 9
NO_DIGIT = -1
MARK_REGISTER = 1
SIGNIFICANCE_OFF_CC = 2


def _bin(
    emitter: HlasmEmitter, operator: BinopKind, left: Register, right: int
) -> Register:
    return emitter.binop(operator, left, emitter.int_(right))


def _set(emitter: HlasmEmitter, name: VarName, value: Register) -> None:
    emitter.emit_inst(StoreVar(name=name, value_reg=value))


def _not(emitter: HlasmEmitter, bit: Register) -> Register:
    return _bin(emitter, BinopKind.BIT_XOR, bit, 1)


def _chosen(
    emitter: HlasmEmitter, condition: Register, taken: Register, kept: Register
) -> Register:
    change = emitter.binop(BinopKind.SUB, taken, kept)
    return emitter.binop(
        BinopKind.ADD, kept, emitter.binop(BinopKind.MUL, condition, change)
    )


def _selects_digit(emitter: HlasmEmitter, pattern_byte: Register) -> Register:
    return emitter.binop(
        BinopKind.BIT_OR,
        _bin(emitter, BinopKind.EQ, pattern_byte, DIGIT_SELECTOR),
        _bin(emitter, BinopKind.EQ, pattern_byte, SIGNIFICANCE_STARTER),
    )


def _take_pending(emitter: HlasmEmitter, pending: Register) -> None:
    _set(emitter, EDIT_DIGIT_VAR, pending)
    _set(emitter, EDIT_PLUS_VAR, emitter.int_(0))
    _set(emitter, EDIT_PENDING_VAR, emitter.int_(NO_DIGIT))


def _fetch(emitter: HlasmEmitter, operands: EditOperands) -> None:
    at = emitter.load_var(EDIT_SOURCE_AT_VAR)
    byte = operands.read(operands.source, at)
    _set(emitter, EDIT_SOURCE_AT_VAR, _bin(emitter, BinopKind.ADD, at, ONE_BYTE))
    right = _bin(emitter, BinopKind.BIT_AND, byte, NIBBLE_MASK)
    is_digit = _bin(emitter, BinopKind.LE, right, LARGEST_DIGIT)
    pending = _chosen(emitter, is_digit, right, emitter.int_(NO_DIGIT))
    _set(emitter, EDIT_PENDING_VAR, pending)
    _set(emitter, EDIT_DIGIT_VAR, _bin(emitter, BinopKind.RSHIFT, byte, NIBBLE_BITS))
    _set(emitter, EDIT_PLUS_VAR, table_bit(emitter, emitter.int_(PLUS_SIGNS), right))


def _examine(
    emitter: HlasmEmitter, operands: EditOperands
) -> tuple[Register, Register]:
    pending = emitter.load_var(EDIT_PENDING_VAR)
    emit_either(
        emitter,
        _bin(emitter, BinopKind.GE, pending, 0),
        lambda: _take_pending(emitter, pending),
        lambda: _fetch(emitter, operands),
    )
    return emitter.load_var(EDIT_DIGIT_VAR), emitter.load_var(EDIT_PLUS_VAR)


def _start(emitter: HlasmEmitter) -> None:
    _set(emitter, EDIT_SOURCE_AT_VAR, emitter.int_(0))
    _set(emitter, EDIT_PENDING_VAR, emitter.int_(NO_DIGIT))


def _check_digit(emitter: HlasmEmitter, operands: EditOperands) -> None:
    digit, _ = _examine(emitter, operands)
    invalid = _bin(emitter, BinopKind.GT, digit, LARGEST_DIGIT)
    seen = emitter.load_var(DECIMAL_INVALID_VAR)
    _set(emitter, DECIMAL_INVALID_VAR, emitter.binop(BinopKind.BIT_OR, seen, invalid))


def _check_byte(emitter: HlasmEmitter, operands: EditOperands, at: Register) -> None:
    emit_when(
        emitter,
        _selects_digit(emitter, operands.read(operands.pattern, at)),
        lambda: _check_digit(emitter, operands),
    )


def _write(
    emitter: HlasmEmitter, operands: EditOperands, at: Register, value: Register
) -> None:
    emitter.write_bytes(operands.pattern, at, ONE_BYTE, emitter.image(value, ONE_BYTE))


def _combine(emitter: HlasmEmitter, operator: BinopKind, bit: Register) -> None:
    seen = emitter.load_var(EDIT_NONZERO_VAR)
    _set(emitter, EDIT_NONZERO_VAR, emitter.binop(operator, seen, bit))


def _turn_significance(
    emitter: HlasmEmitter, significant: Register, pattern_byte: Register, plus: Register
) -> None:
    starter = _bin(emitter, BinopKind.EQ, pattern_byte, SIGNIFICANCE_STARTER)
    on = emitter.binop(BinopKind.BIT_OR, significant, starter)
    _set(
        emitter,
        EDIT_SIGNIFICANCE_VAR,
        emitter.binop(BinopKind.BIT_AND, on, _not(emitter, plus)),
    )


def _edit_digit(
    emitter: HlasmEmitter,
    operands: EditOperands,
    place: tuple[Register, Register],
    mark: Marker,
) -> None:
    at, pattern_byte = place
    digit, plus = _examine(emitter, operands)
    was_on = emitter.load_var(EDIT_SIGNIFICANCE_VAR)
    nonzero = _bin(emitter, BinopKind.NE, digit, 0)
    significant = emitter.binop(BinopKind.BIT_OR, was_on, nonzero)
    zoned = _chosen(
        emitter,
        significant,
        _bin(emitter, BinopKind.BIT_OR, digit, ZONE),
        operands.fill,
    )
    _write(emitter, operands, at, zoned)
    _turn_significance(emitter, significant, pattern_byte, plus)
    _combine(emitter, BinopKind.BIT_OR, nonzero)
    mark(
        emitter.binop(BinopKind.BIT_AND, nonzero, _not(emitter, was_on)),
        emitter.binop(BinopKind.ADD, operands.pattern, at),
    )


def _edit_other(
    emitter: HlasmEmitter, operands: EditOperands, place: tuple[Register, Register]
) -> None:
    at, pattern_byte = place
    within = _not(emitter, _bin(emitter, BinopKind.EQ, pattern_byte, FIELD_SEPARATOR))
    on = emitter.binop(
        BinopKind.BIT_AND, emitter.load_var(EDIT_SIGNIFICANCE_VAR), within
    )
    _write(emitter, operands, at, _chosen(emitter, on, pattern_byte, operands.fill))
    _set(emitter, EDIT_SIGNIFICANCE_VAR, on)
    _combine(emitter, BinopKind.BIT_AND, within)


def _edit_byte(
    emitter: HlasmEmitter, operands: EditOperands, at: Register, mark: Marker
) -> None:
    place = (at, operands.read(operands.pattern, at))
    emit_either(
        emitter,
        _selects_digit(emitter, place[1]),
        lambda: _edit_digit(emitter, operands, place, mark),
        lambda: _edit_other(emitter, operands, place),
    )


def _edit_cc(emitter: HlasmEmitter) -> Register:
    off_cc = emitter.binop(
        BinopKind.SUB,
        emitter.int_(SIGNIFICANCE_OFF_CC),
        emitter.load_var(EDIT_SIGNIFICANCE_VAR),
    )
    return emitter.binop(BinopKind.MUL, emitter.load_var(EDIT_NONZERO_VAR), off_cc)


def _operands(emitter: HlasmEmitter, statement: MachineStatement) -> EditOperands:
    pattern = length_operand_address(
        emitter, storage_length_operand(statement, FIRST_OPERAND)
    )
    source = effective_address(emitter, storage_operand(statement, SECOND_OPERAND))
    read = unit_reader(emitter, ONE_BYTE)
    return EditOperands(pattern, source, read, read(pattern, emitter.int_(0)))


def _check_source(
    emitter: HlasmEmitter, operands: EditOperands, length: Register
) -> None:
    _start(emitter)
    _set(emitter, DECIMAL_INVALID_VAR, emitter.int_(0))
    emit_byte_loop(emitter, length, lambda at: _check_byte(emitter, operands, at))
    emit_data_check(emitter, emitter.load_var(DECIMAL_INVALID_VAR))


def _emit_edit(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField, mark: Marker
) -> None:
    length = field.length(emitter).value(emitter)
    operands = _operands(emitter, statement)
    _check_source(emitter, operands, length)
    _start(emitter)
    _set(emitter, EDIT_SIGNIFICANCE_VAR, emitter.int_(0))
    _set(emitter, EDIT_NONZERO_VAR, emitter.int_(0))
    emit_byte_loop(emitter, length, lambda at: _edit_byte(emitter, operands, at, mark))
    emitter.set_cc(_edit_cc(emitter))


def _edit(emitter: HlasmEmitter, statement: MachineStatement, field: DataField) -> None:
    _emit_edit(emitter, statement, field, lambda _, __: None)


def _remember(emitter: HlasmEmitter, first: Register, address: Register) -> None:
    kept = emitter.load_var(EDIT_MARK_VAR)
    _set(emitter, EDIT_MARK_VAR, _chosen(emitter, first, address, kept))


def _edit_and_mark(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> None:
    _set(emitter, EDIT_MARK_VAR, emitter.int_(NO_DIGIT))
    _emit_edit(
        emitter,
        statement,
        field,
        lambda first, address: _remember(emitter, first, address),
    )
    marked = emitter.load_var(EDIT_MARK_VAR)
    emit_when(
        emitter,
        _bin(emitter, BinopKind.GE, marked, 0),
        lambda: store_address(emitter, MARK_REGISTER, marked),
    )


EDIT_FIELD_LOWERINGS: Mapping[str, FieldLowering] = {
    "ED": FieldLowering(LENGTH_BYTE, _edit),
    "EDMK": FieldLowering(LENGTH_BYTE, _edit_and_mark),
}

EDIT_LOWERINGS: Mapping[str, StatementLowering] = written_lowerings(
    EDIT_FIELD_LOWERINGS
)
