# pyright: standard
"""CP and TP lowerings: CP reads both operands and abends S0C7 before it sets the CC, TP reads one and only sets the CC, neither writes storage, and EX sees byte 1 as one data field."""

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_one_layouts import (
    LENGTH_HIGH_NIBBLE,
    LENGTH_NIBBLES,
    byte_one_layout,
)
from interpreter.hlasm.opcodes import DATA_FIELD_LOWERINGS
from interpreter.instructions import Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.lowering_helpers import (
    lowered,
    machine_statement,
    storage_length_operand,
)
from tests.unit.hlasm.storage_events import storage_events


def _cp() -> MachineStatement:
    return machine_statement(
        "CP", (storage_length_operand(8, 8), storage_length_operand(300, 2))
    )


def _tp() -> MachineStatement:
    return machine_statement("TP", (storage_length_operand(8, 16),))


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_cp_checks_both_operands_before_its_cc_and_tp_only_sets_the_cc():
    irs = {"CP": lowered(_cp()), "TP": lowered(_tp())}

    assert {m: storage_events(ir) for m, ir in irs.items()} == {
        "CP": ["read", "S0C7", "cc"],
        "TP": ["read", "cc"],
    }
    assert [i for ir in irs.values() for i in ir if isinstance(i, Symbolic)] == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_ex_sees_the_lengths_as_one_data_field():
    cp = _cp().model_copy(update={"format": "SS-b"})
    tp = _tp().model_copy(update={"format": "RSL-a"})

    assert (
        {m: DATA_FIELD_LOWERINGS[m].layout for m in ("CP", "TP")},
        byte_one_layout(cp),
        byte_one_layout(tp),
        LENGTH_NIBBLES.byte_of(cp),
        LENGTH_HIGH_NIBBLE.byte_of(tp),
        LENGTH_HIGH_NIBBLE.opcode_bits,
        LENGTH_HIGH_NIBBLE.ignored_bits,
    ) == (
        {"CP": LENGTH_NIBBLES, "TP": LENGTH_HIGH_NIBBLE},
        LENGTH_NIBBLES,
        LENGTH_HIGH_NIBBLE,
        0x71,
        0xF0,
        0,
        0x0F,
    )
