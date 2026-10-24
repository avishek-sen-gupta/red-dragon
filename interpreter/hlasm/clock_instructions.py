# pyright: standard
"""STCK, STCKF, STCKE and ECTG over the clock builtins (ruling R36): STCK and STCKE values are unique and in execution order, compared as 104-bit TOD values against the last one stored; the clock is always in the set state."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import FIRST_OPERAND, SECOND_OPERAND
from interpreter.hlasm.effective_address import effective_address, register_address
from interpreter.hlasm.hlasm_constants import (
    DOUBLEWORD_BYTES,
    QUADWORD_BYTES,
    TOD_LAST_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import reg_operand, storage_operand
from interpreter.hlasm_run_inputs.run_input_names import (
    CPU_TIMER_BUILTIN,
    TOD_CLOCK_BUILTIN,
)
from interpreter.instructions import StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

TOD_EXTENSION_BITS = 40
TOD_ORDER_BITS = 128
PROGRAMMABLE_FIELD_BITS = 16
RUNNING_CLOCK_BIT = 1
SET_STATE_CC = 0
THIRD_OPERAND = 2
CPU_TIME_REGISTER = 0
SECOND_OPERAND_REGISTER = 1


def _clock(emitter: HlasmEmitter) -> Register:
    return emitter.call(TOD_CLOCK_BUILTIN, ())


def _store_clock(
    emitter: HlasmEmitter, statement: MachineStatement, value: Register, width: int
) -> None:
    address = effective_address(emitter, storage_operand(statement, FIRST_OPERAND))
    emitter.store_storage(address, 0, width, value)
    emitter.set_cc(emitter.int_(SET_STATE_CC))


def _later(emitter: HlasmEmitter, value: Register, floor: Register) -> Register:
    difference = emitter.binop(BinopKind.SUB, value, floor)
    borrow = emitter.binop(BinopKind.RSHIFT, difference, emitter.int_(TOD_ORDER_BITS))
    shortfall = emitter.binop(BinopKind.BIT_AND, difference, borrow)
    return emitter.binop(BinopKind.SUB, value, shortfall)


def _clock_bits(emitter: HlasmEmitter) -> Register:
    return emitter.binop(
        BinopKind.RSHIFT, _clock(emitter), emitter.int_(TOD_EXTENSION_BITS)
    )


def _shifted(emitter: HlasmEmitter, value: Register, kind: BinopKind) -> Register:
    return emitter.binop(kind, value, emitter.int_(TOD_EXTENSION_BITS))


def _after_last(emitter: HlasmEmitter) -> Register:
    return emitter.binop(BinopKind.ADD, emitter.load_var(TOD_LAST_VAR), emitter.int_(1))


def lower_store_clock(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    floor = emitter.binop(
        BinopKind.ADD,
        _shifted(emitter, emitter.load_var(TOD_LAST_VAR), BinopKind.RSHIFT),
        emitter.int_(1),
    )
    unique = _later(emitter, _clock_bits(emitter), floor)
    extended = _shifted(emitter, unique, BinopKind.LSHIFT)
    emitter.emit_inst(StoreVar(name=TOD_LAST_VAR, value_reg=extended))
    _store_clock(emitter, statement, unique, DOUBLEWORD_BYTES)


def lower_store_clock_fast(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    _store_clock(emitter, statement, _clock_bits(emitter), DOUBLEWORD_BYTES)


def lower_store_clock_extended(
    emitter: HlasmEmitter, statement: MachineStatement
) -> None:
    running_bit = emitter.int_(RUNNING_CLOCK_BIT)
    running = _later(
        emitter,
        emitter.binop(BinopKind.BIT_OR, _clock(emitter), running_bit),
        emitter.binop(BinopKind.BIT_OR, _after_last(emitter), running_bit),
    )
    emitter.emit_inst(StoreVar(name=TOD_LAST_VAR, value_reg=running))
    value = emitter.binop(
        BinopKind.LSHIFT, running, emitter.int_(PROGRAMMABLE_FIELD_BITS)
    )
    _store_clock(emitter, statement, value, QUADWORD_BYTES)


def _doubleword_at(emitter: HlasmEmitter, address: Register) -> Register:
    return emitter.load_storage(address, 0, DOUBLEWORD_BYTES)


def lower_extract_cpu_time(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    first = _doubleword_at(
        emitter, effective_address(emitter, storage_operand(statement, FIRST_OPERAND))
    )
    second = _doubleword_at(
        emitter,
        effective_address(emitter, storage_operand(statement, SECOND_OPERAND)),
    )
    r3 = reg_operand(statement, THIRD_OPERAND)
    third = _doubleword_at(emitter, register_address(emitter, r3))
    timer = emitter.call(CPU_TIMER_BUILTIN, ())
    emitter.store_gr64(CPU_TIME_REGISTER, emitter.binop(BinopKind.SUB, first, timer))
    emitter.store_gr64(SECOND_OPERAND_REGISTER, second)
    emitter.store_gr64(r3, third)
