# pyright: standard
"""Miscellaneous opcodes: the program mask and PSW, access registers, the checksum, clocks, CPU attributes and the facility list, block counts, and the hints, monitor call and traps that do nothing or abend."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.byte_one_layouts import IMMEDIATE_BYTE
from interpreter.hlasm.checksum import lower_checksum
from interpreter.hlasm.clock_instructions import (
    lower_extract_cpu_time,
    lower_store_clock,
    lower_store_clock_extended,
    lower_store_clock_fast,
)
from interpreter.hlasm.conditional import emit_either
from interpreter.hlasm.cpu_attributes import lower_extract_cpu_attribute
from interpreter.hlasm.data_field import DataField
from interpreter.hlasm.data_movement import (
    SECOND_OPERAND,
    Source,
    aligned_storage_address_at,
    from_gr32,
    move,
    storage_address,
    to_gr32,
)
from interpreter.hlasm.facility_list import lower_store_facility_list
from interpreter.hlasm.field_lowering import FieldLowering, written_lowerings
from interpreter.hlasm.hlasm_constants import (
    SPECIAL_OPERATION_ABEND,
    SPECIFICATION_EXCEPTION_ABEND,
    WORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.long_registers import smaller
from interpreter.hlasm.opcodes.even_odd import even_odd_pairs
from interpreter.hlasm.opcodes.load_store import load_multiple, store_multiple
from interpreter.hlasm.operands import mask_operand, reg_operand
from interpreter.hlasm.program_status import lower_epsw, lower_ipm, lower_spm
from interpreter.hlasm.register_parts import ACCESS_REGISTER_PART
from interpreter.hlasm.specification_check import emit_specification_check
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

MULTIPLE_OPERAND = 2
SMALLEST_BLOCK = 64
LARGEST_BOUNDARY_CODE = 6
BLOCK_COUNT_LIMIT = 16
FULL_BLOCK_CC = 0
SHORT_BLOCK_CC = 3
MONITOR_CLASS_LIMIT = 0xF0


def _from_access_register(index: int) -> Source:
    return lambda emitter, statement: emitter.load_ar(reg_operand(statement, index))


def _to_access_register(
    emitter: HlasmEmitter, statement: MachineStatement, value: Register
) -> None:
    emitter.store_ar(reg_operand(statement, 0), value)


ACCESS_MULTIPLE_ADDRESS = aligned_storage_address_at(MULTIPLE_OPERAND, WORD_BYTES)

ACCESS_REGISTERS: Mapping[str, StatementLowering] = {
    "CPYA": move(_from_access_register(1), (), _to_access_register),
    "EAR": move(_from_access_register(1), (), to_gr32),
    "SAR": move(from_gr32(1), (), _to_access_register),
    "LAM": load_multiple(ACCESS_REGISTER_PART, ACCESS_MULTIPLE_ADDRESS),
    "LAMY": load_multiple(ACCESS_REGISTER_PART, ACCESS_MULTIPLE_ADDRESS),
    "STAM": store_multiple(ACCESS_REGISTER_PART, ACCESS_MULTIPLE_ADDRESS),
    "STAMY": store_multiple(ACCESS_REGISTER_PART, ACCESS_MULTIPLE_ADDRESS),
}


def _block_count(emitter: HlasmEmitter, address: Register, block: int) -> Register:
    offset = emitter.binop(BinopKind.BIT_AND, address, emitter.int_(block - 1))
    remaining = emitter.binop(BinopKind.SUB, emitter.int_(block), offset)
    return smaller(emitter, remaining, emitter.int_(BLOCK_COUNT_LIMIT))


def lower_load_count_to_block_boundary(
    emitter: HlasmEmitter, statement: MachineStatement
) -> None:
    boundary_code = mask_operand(statement, 2)
    if boundary_code > LARGEST_BOUNDARY_CODE:
        emit_abend(emitter, SPECIFICATION_EXCEPTION_ABEND)
        return
    count = _block_count(
        emitter, storage_address(emitter, statement), SMALLEST_BLOCK << boundary_code
    )
    emitter.store_gr32(reg_operand(statement, 0), count)
    emit_either(
        emitter,
        emitter.binop(BinopKind.EQ, count, emitter.int_(BLOCK_COUNT_LIMIT)),
        lambda: emitter.set_cc(emitter.int_(FULL_BLOCK_CC)),
        lambda: emitter.set_cc(emitter.int_(SHORT_BLOCK_CC)),
    )


def lower_monitor_call(
    emitter: HlasmEmitter, statement: MachineStatement, monitor_class: DataField
) -> None:
    beyond = emitter.binop(
        BinopKind.BIT_AND,
        monitor_class.value(emitter),
        emitter.int_(MONITOR_CLASS_LIMIT),
    )
    emit_specification_check(
        emitter, emitter.binop(BinopKind.NE, beyond, emitter.int_(0))
    )


def lower_hint(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    return


def lower_trap(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    emit_abend(emitter, SPECIAL_OPERATION_ABEND)


MISCELLANEOUS_FIELD_LOWERINGS: Mapping[str, FieldLowering] = {
    "MC": FieldLowering(IMMEDIATE_BYTE, lower_monitor_call),
}

MISCELLANEOUS_LOWERINGS: Mapping[str, StatementLowering] = {
    **written_lowerings(MISCELLANEOUS_FIELD_LOWERINGS),
    **ACCESS_REGISTERS,
    "SPM": lower_spm,
    "IPM": lower_ipm,
    "EPSW": lower_epsw,
    "CKSM": even_odd_pairs((SECOND_OPERAND,), lower_checksum),
    "STCK": lower_store_clock,
    "STCKF": lower_store_clock_fast,
    "STCKE": lower_store_clock_extended,
    "ECTG": lower_extract_cpu_time,
    "ECAG": lower_extract_cpu_attribute,
    "STFLE": lower_store_facility_list,
    "LCBB": lower_load_count_to_block_boundary,
    "NIAI": lower_hint,
    "PFD": lower_hint,
    "PFDRL": lower_hint,
    "TRAP2": lower_trap,
    "TRAP4": lower_trap,
}
