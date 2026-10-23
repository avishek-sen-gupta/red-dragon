# pyright: standard
"""STFLE: a constant facility list (ruling R37), a bit on only when every problem-state instruction of its facility is lowered; GR0 bits 56-63 say how many doublewords to store and come back as the list's size."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.alignment_check import emit_alignment_check
from interpreter.hlasm.conditional import emit_either, emit_when
from interpreter.hlasm.data_movement import FIRST_OPERAND
from interpreter.hlasm.effective_address import effective_address
from interpreter.hlasm.hlasm_constants import (
    BYTE_MASK,
    DOUBLEWORD_BITS,
    DOUBLEWORD_BYTES,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import storage_operand
from interpreter.hlasm.register_parts import LOW_WORD_PART
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

FACILITY_BITS = (
    0,
    1,
    2,
    7,
    18,
    19,
    20,
    21,
    22,
    23,
    25,
    26,
    30,
    31,
    32,
    33,
    34,
    35,
    37,
    41,
    42,
    43,
    44,
    45,
    48,
    52,
    53,
    58,
    61,
    80,
    84,
    87,
)
COUNT_REGISTER = 0
COMPLETE_CC = 0
INCOMPLETE_CC = 3


def _doubleword(index: int) -> int:
    first = DOUBLEWORD_BITS * index
    return sum(
        1 << (DOUBLEWORD_BITS - 1 - (bit - first))
        for bit in FACILITY_BITS
        if first <= bit < first + DOUBLEWORD_BITS
    )


FACILITY_LIST = tuple(
    _doubleword(index) for index in range(max(FACILITY_BITS) // DOUBLEWORD_BITS + 1)
)


def _store_beyond_first(
    emitter: HlasmEmitter, address: Register, supplied: Register, index: int
) -> None:
    emit_when(
        emitter,
        emitter.binop(BinopKind.GT, supplied, emitter.int_(index)),
        lambda: emitter.store_storage(
            address,
            DOUBLEWORD_BYTES * index,
            DOUBLEWORD_BYTES,
            emitter.int_(FACILITY_LIST[index]),
        ),
    )


def lower_store_facility_list(
    emitter: HlasmEmitter, statement: MachineStatement
) -> None:
    address = effective_address(emitter, storage_operand(statement, FIRST_OPERAND))
    emit_alignment_check(emitter, address, DOUBLEWORD_BYTES)
    count = emitter.binop(
        BinopKind.BIT_AND, emitter.load_gr32(COUNT_REGISTER), emitter.int_(BYTE_MASK)
    )
    supplied = emitter.binop(BinopKind.ADD, count, emitter.int_(1))
    emitter.store_storage(address, 0, DOUBLEWORD_BYTES, emitter.int_(FACILITY_LIST[0]))
    _ = [
        _store_beyond_first(emitter, address, supplied, index)
        for index in range(1, len(FACILITY_LIST))
    ]
    LOW_WORD_PART.merge(
        emitter, COUNT_REGISTER, emitter.int_(len(FACILITY_LIST) - 1), BYTE_MASK
    )
    emit_either(
        emitter,
        emitter.binop(BinopKind.GE, supplied, emitter.int_(len(FACILITY_LIST))),
        lambda: emitter.set_cc(emitter.int_(COMPLETE_CC)),
        lambda: emitter.set_cc(emitter.int_(INCOMPLETE_CC)),
    )
