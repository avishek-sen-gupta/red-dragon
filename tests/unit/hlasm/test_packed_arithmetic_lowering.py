# pyright: standard
"""Packed-decimal lowerings: every check precedes the first store, the CC and the overflow abend follow it, and EX sees byte 1 as one data field."""

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.operand import Operand
from interpreter.hlasm.byte_one_layouts import (
    LENGTH_AND_IMMEDIATE,
    LENGTH_NIBBLES,
    byte_one_layout,
)
from interpreter.hlasm.opcodes import DATA_FIELD_LOWERINGS
from interpreter.instructions import Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.lowering_helpers import (
    imm_operand,
    lowered,
    machine_statement,
    storage_length_operand,
    storage_operand,
)
from tests.unit.hlasm.storage_events import storage_events

PACKED = ("AP", "SP", "ZAP", "MP", "DP", "SRP")
CHECKED_THEN_STORED = ["read", "S0C7", "write", "cc", "S0CA"]


def _statement(mnemonic: str) -> MachineStatement:
    operands: tuple[Operand, ...] = (
        (storage_length_operand(8, 8), storage_operand(63), imm_operand(5))
        if mnemonic == "SRP"
        else (storage_length_operand(8, 8), storage_length_operand(300, 2))
    )
    return machine_statement(mnemonic, operands)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_check_precedes_the_first_store_and_the_cc_precedes_the_overflow_abend():
    irs = {m: lowered(_statement(m)) for m in PACKED}

    assert {m: storage_events(ir) for m, ir in irs.items()} == {
        "AP": CHECKED_THEN_STORED,
        "SP": CHECKED_THEN_STORED,
        "ZAP": CHECKED_THEN_STORED,
        "SRP": CHECKED_THEN_STORED,
        "MP": ["S0C6", "read", "S0C7", "write"],
        "DP": ["S0C6", "read", "S0C7", "S0CB", "write"],
    }
    assert [i for ir in irs.values() for i in ir if isinstance(i, Symbolic)] == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_ex_sees_the_lengths_and_the_rounding_digit_as_one_data_field():
    srp = _statement("SRP").model_copy(update={"format": "SS-c"})
    ap = _statement("AP").model_copy(update={"format": "SS-b"})

    assert (
        {m: DATA_FIELD_LOWERINGS[m].layout for m in PACKED},
        byte_one_layout(srp),
        byte_one_layout(ap),
        LENGTH_AND_IMMEDIATE.byte_of(srp),
        LENGTH_NIBBLES.byte_of(ap),
        LENGTH_AND_IMMEDIATE.opcode_bits,
    ) == (
        {
            "AP": LENGTH_NIBBLES,
            "SP": LENGTH_NIBBLES,
            "ZAP": LENGTH_NIBBLES,
            "MP": LENGTH_NIBBLES,
            "DP": LENGTH_NIBBLES,
            "SRP": LENGTH_AND_IMMEDIATE,
        },
        LENGTH_AND_IMMEDIATE,
        LENGTH_NIBBLES,
        0x75,
        0x71,
        0,
    )
