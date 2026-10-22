# pyright: standard
"""Packed-decimal lowerings: every check precedes the first store, the CC and the overflow abend follow it, and EX sees byte 1 as one data field."""

from collections.abc import Mapping, Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.operand import Operand
from hlasm_asg.program.storage_length_operand import StorageLengthOperand
from interpreter.hlasm.byte_one_layouts import (
    LENGTH_AND_IMMEDIATE,
    LENGTH_NIBBLES,
    byte_one_layout,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import DATA_FIELD_LOWERINGS, OPCODE_LOWERINGS
from interpreter.instructions import (
    Const,
    InstructionBase,
    LoadRegion,
    LoadVar,
    StoreVar,
    Symbolic,
    WriteRegion,
)
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.lowering_helpers import (
    imm_operand,
    machine_statement,
    storage_operand,
)

BASE = 12
GPRS = "__hlasm_gprs"
ABEND = "__hlasm_abend"
CC = "__hlasm_cc"
PACKED = ("AP", "SP", "ZAP", "MP", "DP", "SRP")
STORAGE_ACCESSES: Mapping[type[InstructionBase], str] = {
    LoadRegion: "read",
    WriteRegion: "write",
}
CHECKED_THEN_STORED = ["read", "S0C7", "write", "cc", "S0CA"]


def _with_length(displacement: int, length: int) -> StorageLengthOperand:
    return StorageLengthOperand(
        kind="STORAGE_LENGTH", displacement=displacement, length=length, base=BASE
    )


def _statement(mnemonic: str) -> MachineStatement:
    operands: tuple[Operand, ...] = (
        (_with_length(8, 8), storage_operand(63), imm_operand(5))
        if mnemonic == "SRP"
        else (_with_length(8, 8), _with_length(300, 2))
    )
    return machine_statement(mnemonic, operands)


def _lowered(statement: MachineStatement) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[statement.base_mnemonic](emitter, statement)
    return emitter.instructions()


def _abend_or_cc(i: StoreVar, consts: Mapping[str, int | str]) -> str:
    return {ABEND: str(consts.get(str(i.value_reg), "")), CC: "cc"}.get(str(i.name), "")


def _access(i: InstructionBase, gprs: frozenset[str]) -> str:
    in_gprs = isinstance(i, LoadRegion) and str(i.region_reg) in gprs
    return "" if in_gprs else STORAGE_ACCESSES.get(type(i), "")


def _event(
    i: InstructionBase, gprs: frozenset[str], consts: Mapping[str, int | str]
) -> str:
    if isinstance(i, StoreVar):
        return _abend_or_cc(i, consts)
    return _access(i, gprs)


def _events(ir: Sequence[InstructionBase]) -> list[str]:
    gprs = frozenset(
        str(i.result_reg) for i in ir if isinstance(i, LoadVar) and str(i.name) == GPRS
    )
    consts = {str(i.result_reg): i.value for i in ir if isinstance(i, Const)}
    named = [e for e in (_event(i, gprs, consts) for i in ir) if e]
    return [e for k, e in enumerate(named) if k == 0 or named[k - 1] != e]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_check_precedes_the_first_store_and_the_cc_precedes_the_overflow_abend():
    lowered = {m: _lowered(_statement(m)) for m in PACKED}

    assert {m: _events(ir) for m, ir in lowered.items()} == {
        "AP": CHECKED_THEN_STORED,
        "SP": CHECKED_THEN_STORED,
        "ZAP": CHECKED_THEN_STORED,
        "SRP": CHECKED_THEN_STORED,
        "MP": ["S0C6", "read", "S0C7", "write"],
        "DP": ["S0C6", "read", "S0C7", "S0CB", "write"],
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []


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
