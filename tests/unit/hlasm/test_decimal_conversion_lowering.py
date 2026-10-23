# pyright: standard
"""Decimal conversion lowerings: CVB checks the codes before it writes R1 and raises S0C9 after, CVBG raises S0C9 before; PKA and UNPKU check their lengths before any store; UNPKA sets the CC after its stores and never raises S0C7; EX sees byte 1 as one data field."""

from collections.abc import Mapping

from hlasm_asg.program.operand import Operand
from interpreter.hlasm.byte_one_layouts import (
    byte_one_layout,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.instructions import InstructionBase, Symbolic
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.lowering_helpers import (
    machine_statement,
    reg_operand,
    storage_length_operand,
    storage_operand,
)
from tests.unit.hlasm.storage_events import storage_events

STATEMENTS: Mapping[str, tuple[Operand, ...]] = {
    "CVB": (reg_operand(3), storage_operand(8)),
    "CVBG": (reg_operand(3), storage_operand(8)),
    "CVDG": (reg_operand(3), storage_operand(8)),
    "PACK": (storage_length_operand(8, 8), storage_length_operand(300, 5)),
    "UNPK": (storage_length_operand(300, 5), storage_length_operand(8, 3)),
    "PKA": (storage_operand(8), storage_length_operand(300, 5)),
    "UNPKA": (storage_length_operand(300, 8), storage_operand(8)),
    "UNPKU": (storage_length_operand(300, 8), storage_operand(8)),
}


def _lowered(mnemonic: str) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[mnemonic](
        emitter, machine_statement(mnemonic, STATEMENTS[mnemonic])
    )
    return emitter.instructions()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_checks_precede_stores_and_cvb_completes_before_its_divide_check():
    lowered = {m: _lowered(m) for m in STATEMENTS}

    assert {m: storage_events(ir) for m, ir in lowered.items()} == {
        "CVB": ["read", "S0C7", "write", "S0C9"],
        "CVBG": ["read", "S0C7", "S0C9", "write"],
        "CVDG": ["write"],
        "PACK": ["read", "write", "read", "write"],
        "UNPK": ["read", "write", "read", "write"],
        "PKA": ["S0C6", "read", "write", "read", "write"],
        "UNPKA": ["S0C6", "read", "write", "read", "write", "cc"],
        "UNPKU": ["S0C6", "read", "write", "read", "write", "cc"],
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_ex_sees_the_lengths_as_one_data_field():
    formats = {
        "PACK": "SS-b",
        "UNPK": "SS-b",
        "PKA": "SS-f",
        "UNPKA": "SS-a",
        "UNPKU": "SS-a",
    }
    statements = {
        m: machine_statement(m, STATEMENTS[m]).model_copy(update={"format": f})
        for m, f in formats.items()
    }

    assert {m: byte_one_layout(s).byte_of(s) for m, s in statements.items()} == {
        "PACK": 0x74,
        "UNPK": 0x42,
        "PKA": 0x04,
        "UNPKA": 0x07,
        "UNPKU": 0x07,
    }
