# pyright: standard
"""Edit lowerings: ED and EDMK read and check the source before any store, then edit, then set the CC; EDMK writes GR1 last; EX sees the length as one data field."""

from hlasm_asg.program.storage_length_operand import StorageLengthOperand
from interpreter.hlasm.byte_one_layouts import LENGTH_BYTE, byte_one_layout
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import DATA_FIELD_LOWERINGS, OPCODE_LOWERINGS
from interpreter.instructions import InstructionBase, Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.lowering_helpers import machine_statement, storage_operand
from tests.unit.hlasm.storage_events import storage_events

BASE = 12
MNEMONICS = ("ED", "EDMK")
PATTERN = StorageLengthOperand(
    kind="STORAGE_LENGTH", displacement=300, length=10, base=BASE
)


def _lowered(mnemonic: str) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[mnemonic](
        emitter, machine_statement(mnemonic, (PATTERN, storage_operand(8)))
    )
    return emitter.instructions()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_source_is_checked_before_the_pattern_is_stored():
    lowered = {m: _lowered(m) for m in MNEMONICS}

    assert {m: storage_events(ir) for m, ir in lowered.items()} == {
        "ED": ["read", "S0C7", "read", "write", "cc"],
        "EDMK": ["read", "S0C7", "read", "write", "cc", "write"],
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_ex_sees_the_length_as_one_data_field():
    statement = machine_statement("ED", (PATTERN, storage_operand(8))).model_copy(
        update={"format": "SS-a"}
    )

    assert (
        {m: DATA_FIELD_LOWERINGS[m].layout for m in MNEMONICS},
        byte_one_layout(statement),
        byte_one_layout(statement).byte_of(statement),
    ) == ({"ED": LENGTH_BYTE, "EDMK": LENGTH_BYTE}, LENGTH_BYTE, 0x09)
