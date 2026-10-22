# pyright: standard
"""Test under mask lowerings: the storage byte or register halfword read, nothing written, only the CC set."""

from collections.abc import Sequence

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.imm_operand import ImmOperand
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reg_operand import RegOperand
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.instructions import (
    Binop,
    Const,
    InstructionBase,
    LoadRegion,
    LoadVar,
    StoreVar,
    Symbolic,
    WriteRegion,
)
from interpreter.operator_kind import BinopKind
from tests.covers import NotLanguageFeature, covers

BASE = 12
GPRS = "__hlasm_gprs"
MASK = ImmOperand(kind="IMM", value=0x8000)
TEST_UNDER_MASK = ("TM", "TMY", "TMH", "TML", "TMHH", "TMHL", "TMLH", "TMLL")
HALFWORD_SHIFTS = {"TMHH": 48, "TMHL": 32, "TMLH": 16, "TMLL": 0}


def _statement(mnemonic: str, operands: Sequence[Operand]) -> MachineStatement:
    return MachineStatement(
        kind="MACHINE",
        section="T",
        offset=2,
        label="",
        mnemonic=mnemonic,
        base_mnemonic=mnemonic,
        format="",
        length=4,
        operands=tuple(operands),
        origin=OpenCodeOrigin(kind="OPEN_CODE", file="t.asm", line=1),
    )


def _lowered(mnemonic: str, first: Operand) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    statement = _statement(mnemonic, (first, MASK))
    OPCODE_LOWERINGS[mnemonic](emitter, statement)
    return emitter.instructions()


def _accesses(ir: Sequence[InstructionBase]) -> list[tuple[str, str, int]]:
    gprs = frozenset(
        i.result_reg for i in ir if isinstance(i, LoadVar) and str(i.name) == GPRS
    )
    return [
        (type(i).__name__, "gpr" if i.region_reg in gprs else "storage", i.length)
        for i in ir
        if isinstance(i, LoadRegion | WriteRegion)
    ]


def _field_shift(ir: Sequence[InstructionBase]) -> int:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    first = next(
        i for i in ir if isinstance(i, Binop) and i.operator == BinopKind.RSHIFT
    )
    return int(consts[first.right])


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_each_form_reads_its_byte_or_register_and_writes_only_the_cc():
    storage = StorageOperand(
        kind="STORAGE",
        displacement=8,
        index=0,
        base=BASE,
        written=AbsAddress(kind="ABS", value=8),
    )
    register = RegOperand(kind="REG", value=3)
    lowered = {
        m: _lowered(m, storage if m in ("TM", "TMY") else register)
        for m in TEST_UNDER_MASK
    }
    base_read = ("LoadRegion", "gpr", 4)
    register_read = ("LoadRegion", "gpr", 8)
    assert {m: _accesses(ir) for m, ir in lowered.items()} == {
        "TM": [base_read, ("LoadRegion", "storage", 1)],
        "TMY": [base_read, ("LoadRegion", "storage", 1)],
        **{m: [register_read] for m in ("TMH", "TML", *HALFWORD_SHIFTS)},
    }
    assert {
        m: [str(i.name) for i in ir if isinstance(i, StoreVar)]
        for m, ir in lowered.items()
    } == {m: ["__hlasm_cc"] for m in TEST_UNDER_MASK}
    assert {m: _field_shift(lowered[m]) for m in ("TMH", "TML", *HALFWORD_SHIFTS)} == {
        "TMH": 16,
        "TML": 0,
        **HALFWORD_SHIFTS,
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []
