# pyright: standard
"""CSST: the GR0 function code sizes the compare and swap, the store characteristic sizes the store; the GR1 parameter list holds the replacement and store values."""

from collections.abc import Mapping
from functools import partial

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.alignment_check import emit_alignment_check
from interpreter.hlasm.compare_chain import emit_compare_or_refresh
from interpreter.hlasm.comparison import Comparison
from interpreter.hlasm.data_movement import storage_address_at
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    BYTE_MASK,
    DOUBLEWORD_BYTES,
    QUADWORD_BYTES,
    SPECIFICATION_EXCEPTION_ABEND,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import reg_operand
from interpreter.hlasm.place import Place
from interpreter.hlasm.places import in_storage, low_word, register_pair, whole_register
from interpreter.hlasm.specification_check import emit_specification_check
from interpreter.hlasm.value_tree import emit_value_switch
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

FIRST_OPERAND = 0
SECOND_OPERAND = 1
THIRD_REGISTER = 2
FUNCTION_REGISTER = 0
PARAMETER_REGISTER = 1
STORE_CHARACTERISTIC_SHIFT = 8
STORE_VALUE_OFFSET = 16
STORE_VALUE_BYTES = 16
PARAMETER_LIST_MASK = 0x7FFFFFF0
QUADWORD_FUNCTION = 2
FUNCTION_WIDTHS: Mapping[int, int] = {
    0: WORD_BYTES,
    1: DOUBLEWORD_BYTES,
    QUADWORD_FUNCTION: QUADWORD_BYTES,
}
STORE_CHARACTERISTICS = (0, 1, 2, 3, 4)
THIRD_OPERAND_PLACES = {
    0: low_word,
    1: whole_register,
    QUADWORD_FUNCTION: register_pair,
}


def _assigned_field(
    emitter: HlasmEmitter, gr0: Register, shift: int, highest: int
) -> Register:
    shifted = emitter.binop(BinopKind.RSHIFT, gr0, emitter.int_(shift))
    field = emitter.binop(BinopKind.BIT_AND, shifted, emitter.int_(BYTE_MASK))
    emit_specification_check(
        emitter, emitter.binop(BinopKind.GT, field, emitter.int_(highest))
    )
    return field


def _store_boundary_check(
    emitter: HlasmEmitter, address: Register, characteristic: Register
) -> None:
    size = emitter.binop(BinopKind.LSHIFT, emitter.int_(1), characteristic)
    boundary = emitter.binop(BinopKind.SUB, size, emitter.int_(1))
    offset = emitter.binop(BinopKind.BIT_AND, address, boundary)
    emit_specification_check(
        emitter, emitter.binop(BinopKind.NE, offset, emitter.int_(0))
    )


def _store_value(
    emitter: HlasmEmitter, address: Register, stored: Register, characteristic: int
) -> None:
    width = 1 << characteristic
    shift = BITS_PER_BYTE * (STORE_VALUE_BYTES - width)
    value = emitter.binop(BinopKind.RSHIFT, stored, emitter.int_(shift))
    emitter.store_storage(address, 0, width, value)


def _replace_and_store(
    emitter: HlasmEmitter,
    operand: Place,
    addresses: tuple[Register, Register],
    widths: tuple[int, Register],
) -> None:
    second, parameters = addresses
    width, characteristic = widths
    replacement = emitter.load_storage(parameters, 0, width)
    stored = emitter.load_storage(parameters, STORE_VALUE_OFFSET, STORE_VALUE_BYTES)
    operand.write(replacement)
    emit_value_switch(
        emitter,
        characteristic,
        STORE_CHARACTERISTICS,
        lambda sc: _store_value(emitter, second, stored, sc),
    )


def _swap_and_store(
    emitter: HlasmEmitter,
    statement: MachineStatement,
    addresses: tuple[Register, Register, Register],
    characteristic: Register,
    code: int,
) -> None:
    r3 = reg_operand(statement, THIRD_REGISTER)
    if code == QUADWORD_FUNCTION and r3 % 2:
        emit_abend(emitter, SPECIFICATION_EXCEPTION_ABEND)
        return
    first, second, parameters = addresses
    width = FUNCTION_WIDTHS[code]
    emit_alignment_check(emitter, first, width)
    operand = in_storage(emitter, first, width)
    third = THIRD_OPERAND_PLACES[code](emitter, r3)
    emit_compare_or_refresh(
        emitter,
        Comparison(third, operand, third),
        lambda: _replace_and_store(
            emitter, operand, (second, parameters), (width, characteristic)
        ),
    )


def lower_compare_and_swap_and_store(
    emitter: HlasmEmitter, statement: MachineStatement
) -> None:
    gr0 = emitter.load_gr32(FUNCTION_REGISTER)
    function = _assigned_field(emitter, gr0, 0, max(FUNCTION_WIDTHS))
    characteristic = _assigned_field(
        emitter, gr0, STORE_CHARACTERISTIC_SHIFT, max(STORE_CHARACTERISTICS)
    )
    first = storage_address_at(FIRST_OPERAND)(emitter, statement)
    second = storage_address_at(SECOND_OPERAND)(emitter, statement)
    _store_boundary_check(emitter, second, characteristic)
    parameters = emitter.binop(
        BinopKind.BIT_AND,
        emitter.load_gr32(PARAMETER_REGISTER),
        emitter.int_(PARAMETER_LIST_MASK),
    )
    emit_value_switch(
        emitter,
        function,
        tuple(FUNCTION_WIDTHS),
        partial(
            _swap_and_store,
            emitter,
            statement,
            (first, second, parameters),
            characteristic,
        ),
    )
