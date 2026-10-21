# pyright: standard
"""Load address and immediate opcodes: addresses, relative and indexed addresses, and immediates."""

from collections.abc import Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import (
    immediate,
    into_bits,
    keep,
    move,
    relative_target,
    shifted,
    signed,
    storage_address,
    to_gr32,
    to_gr64,
)
from interpreter.hlasm.effective_address import indexed_address
from interpreter.hlasm.hlasm_constants import (
    ADDRESS_MASK_31,
    HALFWORD_BITS,
    WORD_BITS,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import mask_operand, storage_operand
from interpreter.hlasm.statement_lowering import StatementLowering

TARGET_OPERAND = 0
ADDRESS_OPERAND = 1


def _field_mask(bits: int, shift: int) -> int:
    return ((1 << bits) - 1) << shift


def _logical(bits: int, shift: int) -> StatementLowering:
    return move(immediate(bits), (shifted(shift),), to_gr64)


def _inserted(bits: int, shift: int) -> StatementLowering:
    return move(immediate(bits), (shifted(shift),), into_bits(_field_mask(bits, shift)))


def _indexed(shift: int) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        emitter.store_gr32(
            mask_operand(statement, TARGET_OPERAND),
            indexed_address(
                emitter, storage_operand(statement, ADDRESS_OPERAND), shift
            ),
        )

    return lower


ADDRESSES: Mapping[str, StatementLowering] = {
    "LA": move(storage_address, (), to_gr32),
    "LAY": move(storage_address, (), to_gr32),
    "LAE": move(storage_address, (), to_gr32),
    "LAEY": move(storage_address, (), to_gr32),
    "LARL": move(relative_target, (keep(ADDRESS_MASK_31),), to_gr32),
    "LXAB": _indexed(0),
    "LXAH": _indexed(1),
    "LXAF": _indexed(2),
    "LXAG": _indexed(3),
    "LXAQ": _indexed(4),
    "LLXAB": _indexed(0),
    "LLXAH": _indexed(1),
    "LLXAF": _indexed(2),
    "LLXAG": _indexed(3),
    "LLXAQ": _indexed(4),
}

IMMEDIATES: Mapping[str, StatementLowering] = {
    "LHI": move(immediate(HALFWORD_BITS), (signed(HALFWORD_BITS),), to_gr32),
    "LGHI": move(immediate(HALFWORD_BITS), (signed(HALFWORD_BITS),), to_gr64),
    "LGFI": move(immediate(WORD_BITS), (signed(WORD_BITS),), to_gr64),
    "LLIHF": _logical(WORD_BITS, 32),
    "LLIHH": _logical(HALFWORD_BITS, 48),
    "LLIHL": _logical(HALFWORD_BITS, 32),
    "LLILF": _logical(WORD_BITS, 0),
    "LLILH": _logical(HALFWORD_BITS, 16),
    "LLILL": _logical(HALFWORD_BITS, 0),
    "IIHF": _inserted(WORD_BITS, 32),
    "IIHH": _inserted(HALFWORD_BITS, 48),
    "IIHL": _inserted(HALFWORD_BITS, 32),
    "IILF": _inserted(WORD_BITS, 0),
    "IILH": _inserted(HALFWORD_BITS, 16),
    "IILL": _inserted(HALFWORD_BITS, 0),
}

LOAD_ADDRESS_IMMEDIATE_LOWERINGS: Mapping[str, StatementLowering] = {
    **ADDRESSES,
    **IMMEDIATES,
}
