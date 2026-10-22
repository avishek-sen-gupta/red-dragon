# pyright: standard
"""PLO: GR0's test bit and function code select a row of the function-code table at run time; the row's compares and stores run in the Principles of Operation order."""

from collections.abc import Mapping
from dataclasses import replace
from functools import partial

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.alignment_check import emit_alignment_check
from interpreter.hlasm.compare_chain import EQUAL_CC, emit_cc, emit_compare_chain
from interpreter.hlasm.comparison import Comparison
from interpreter.hlasm.conditional import emit_either
from interpreter.hlasm.data_field import DataField
from interpreter.hlasm.data_movement import storage_address_at
from interpreter.hlasm.hlasm_constants import BYTE_MASK, NIBBLE_BITS
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.locked_operation import LockedOperation, Spot
from interpreter.hlasm.locked_operations import LOCKED_OPERATIONS
from interpreter.hlasm.places import held_address
from interpreter.hlasm.plo_frame import PloFrame
from interpreter.hlasm.specification_check import emit_specification_check
from interpreter.hlasm.value_tree import emit_value_switch
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

FUNCTION_REGISTER = 0
SECOND_OPERAND = 1
FOURTH_OPERAND = 3
FIRST_REGISTER = 0
THIRD_REGISTER = 2
HIGH_NIBBLE = 4
RESERVED_SHIFT = 9
TEST_BIT_SHIFT = 8
VALID_CC = 0
INVALID_CC = 3
HIGHEST_FUNCTION_CODE = max(LOCKED_OPERATIONS)


def _stored(frame: PloFrame, row: LockedOperation) -> None:
    _ = [target(frame).write(source(frame).read()) for source, target in row.stores]


def _swapped(frame: PloFrame, row: LockedOperation) -> None:
    _stored(frame, row)
    emit_cc(frame.emitter, EQUAL_CC)


def _comparison(frame: PloFrame, spots: tuple[Spot, Spot]) -> Comparison:
    value, operand = (spot(frame) for spot in spots)
    return Comparison(value, operand, value)


def _compared(frame: PloFrame, row: LockedOperation) -> None:
    comparisons = tuple(_comparison(frame, spots) for spots in row.compares)
    emit_compare_chain(
        frame.emitter,
        comparisons,
        partial(row.unequal, frame),
        partial(_swapped, frame, row),
    )


def _odd(emitter: HlasmEmitter, r: Register) -> Register:
    low = emitter.binop(BinopKind.BIT_AND, r, emitter.int_(1))
    return emitter.binop(BinopKind.NE, low, emitter.int_(0))


def _checked(frame: PloFrame, row: LockedOperation) -> PloFrame:
    emitter = frame.emitter
    _ = [
        *(
            emit_specification_check(emitter, _odd(emitter, frame.registers[index]))
            for index in row.even_registers
        ),
        *(
            emit_alignment_check(emitter, address(frame), boundary)
            for address, boundary in row.checks
        ),
    ]
    listed = {
        at: held_address(emitter, frame.fourth, at, row.width) for at in row.listed
    }
    return replace(frame, listed=listed)


def _perform(frame: PloFrame, function_code: int) -> None:
    row = LOCKED_OPERATIONS[function_code]
    checked = _checked(frame, row)
    if row.compares:
        _compared(checked, row)
        return
    _stored(checked, row)


def _emit_test(emitter: HlasmEmitter, function_code: Register) -> None:
    valid = emitter.binop(
        BinopKind.LE, function_code, emitter.int_(HIGHEST_FUNCTION_CODE)
    )
    emit_either(
        emitter,
        valid,
        lambda: emit_cc(emitter, VALID_CC),
        lambda: emit_cc(emitter, INVALID_CC),
    )


def _emit_operation(
    emitter: HlasmEmitter,
    statement: MachineStatement,
    function_code: Register,
    registers: Mapping[int, Register],
) -> None:
    emit_specification_check(
        emitter,
        emitter.binop(BinopKind.GT, function_code, emitter.int_(HIGHEST_FUNCTION_CODE)),
    )
    frame = PloFrame(
        emitter,
        registers,
        storage_address_at(SECOND_OPERAND)(emitter, statement),
        storage_address_at(FOURTH_OPERAND)(emitter, statement),
        {},
    )
    emit_value_switch(
        emitter, function_code, tuple(LOCKED_OPERATIONS), partial(_perform, frame)
    )


def _bits_from(emitter: HlasmEmitter, gr0: Register, shift: int) -> Register:
    shifted = emitter.binop(BinopKind.RSHIFT, gr0, emitter.int_(shift))
    return emitter.binop(BinopKind.NE, shifted, emitter.int_(0))


def _register_numbers(
    emitter: HlasmEmitter, field: DataField
) -> Mapping[int, Register]:
    return {
        FIRST_REGISTER: field.part(emitter, HIGH_NIBBLE, NIBBLE_BITS).value(emitter),
        THIRD_REGISTER: field.part(emitter, 0, NIBBLE_BITS).value(emitter),
    }


def lower_perform_locked_operation(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> None:
    registers = _register_numbers(emitter, field)
    gr0 = emitter.load_gr32(FUNCTION_REGISTER)
    emit_specification_check(emitter, _bits_from(emitter, gr0, RESERVED_SHIFT))
    function_code = emitter.binop(BinopKind.BIT_AND, gr0, emitter.int_(BYTE_MASK))
    emit_either(
        emitter,
        _bits_from(emitter, gr0, TEST_BIT_SHIFT),
        lambda: _emit_test(emitter, function_code),
        lambda: _emit_operation(emitter, statement, function_code, registers),
    )
