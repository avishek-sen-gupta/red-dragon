# pyright: standard
"""Logical add and subtract lowerings: the operand widths they read and write, the carry-in they read, and the CC with no trap."""

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
    BranchIf,
    Const,
    Halt_,
    InstructionBase,
    LoadRegion,
    LoadVar,
    StoreVar,
    Symbolic,
    WriteRegion,
)
from tests.covers import NotLanguageFeature, covers

BASE = 12
GPRS = "__hlasm_gprs"
CC = "__hlasm_cc"


def _statement(mnemonic: str, operands: Sequence[Operand]) -> MachineStatement:
    return MachineStatement(
        kind="MACHINE",
        section="T",
        offset=2,
        label="",
        mnemonic=mnemonic,
        base_mnemonic=mnemonic,
        format="",
        length=6,
        operands=tuple(operands),
        origin=OpenCodeOrigin(kind="OPEN_CODE", file="t.asm", line=1),
    )


def _reg(value: int) -> RegOperand:
    return RegOperand(kind="REG", value=value)


def _imm(value: int) -> ImmOperand:
    return ImmOperand(kind="IMM", value=value)


def _storage(displacement: int) -> StorageOperand:
    return StorageOperand(
        kind="STORAGE",
        displacement=displacement,
        index=0,
        base=BASE,
        written=AbsAddress(kind="ABS", value=displacement),
    )


def _lowered(statement: MachineStatement) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[statement.base_mnemonic](emitter, statement)
    return emitter.instructions()


def _accesses(ir: Sequence[InstructionBase]) -> list[tuple[str, str, int, int | str]]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    gprs = frozenset(
        i.result_reg for i in ir if isinstance(i, LoadVar) and str(i.name) == GPRS
    )
    return [
        (
            type(i).__name__,
            "gpr" if i.region_reg in gprs else "storage",
            i.length,
            consts.get(i.offset_reg, "computed"),
        )
        for i in ir
        if isinstance(i, LoadRegion | WriteRegion)
    ]


def _cc_reads(ir: Sequence[InstructionBase]) -> int:
    return len([i for i in ir if isinstance(i, LoadVar) and str(i.name) == CC])


def _control(ir: Sequence[InstructionBase]) -> list[str]:
    return [
        f"StoreVar:{i.name}" if isinstance(i, StoreVar) else type(i).__name__
        for i in ir
        if isinstance(i, BranchIf | Halt_ | StoreVar)
    ]


def _gpr(r: int, width: int) -> tuple[str, int, int]:
    return "gpr", width, 8 * r + 8 - width


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_each_form_reads_and_writes_its_operand_widths_then_sets_cc_without_a_trap():
    lowered = {
        "ALGF": _lowered(_statement("ALGF", (_reg(2), _storage(8)))),
        "ALRK": _lowered(_statement("ALRK", (_reg(5), _reg(3), _reg(4)))),
        "SLGFR": _lowered(_statement("SLGFR", (_reg(2), _reg(3)))),
        "ALCR": _lowered(_statement("ALCR", (_reg(2), _reg(3)))),
        "SLBG": _lowered(_statement("SLBG", (_reg(2), _storage(8)))),
        "ALHSIK": _lowered(_statement("ALHSIK", (_reg(5), _reg(3), _imm(-2)))),
        "ALSI": _lowered(_statement("ALSI", (_storage(8), _imm(-1)))),
        "ALGSI": _lowered(_statement("ALGSI", (_storage(8), _imm(255)))),
    }

    assert {m: _accesses(ir) for m, ir in lowered.items()} == {
        "ALGF": [
            ("LoadRegion", *_gpr(2, 8)),
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 4, 0),
            ("WriteRegion", *_gpr(2, 8)),
        ],
        "ALRK": [
            ("LoadRegion", *_gpr(3, 4)),
            ("LoadRegion", *_gpr(4, 4)),
            ("WriteRegion", *_gpr(5, 4)),
        ],
        "SLGFR": [
            ("LoadRegion", *_gpr(2, 8)),
            ("LoadRegion", *_gpr(3, 4)),
            ("WriteRegion", *_gpr(2, 8)),
        ],
        "ALCR": [
            ("LoadRegion", *_gpr(2, 4)),
            ("LoadRegion", *_gpr(3, 4)),
            ("WriteRegion", *_gpr(2, 4)),
        ],
        "SLBG": [
            ("LoadRegion", *_gpr(2, 8)),
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 8, 0),
            ("WriteRegion", *_gpr(2, 8)),
        ],
        "ALHSIK": [
            ("LoadRegion", *_gpr(3, 4)),
            ("WriteRegion", *_gpr(5, 4)),
        ],
        "ALSI": [
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 4, 0),
            ("WriteRegion", "storage", 4, 0),
        ],
        "ALGSI": [
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 8, 0),
            ("WriteRegion", "storage", 8, 0),
        ],
    }
    assert {m: _cc_reads(ir) for m, ir in lowered.items()} == {
        "ALGF": 0,
        "ALRK": 0,
        "SLGFR": 0,
        "ALCR": 1,
        "SLBG": 1,
        "ALHSIK": 0,
        "ALSI": 0,
        "ALGSI": 0,
    }
    assert {m: _control(ir) for m, ir in lowered.items()} == {
        m: [f"StoreVar:{CC}"] for m in lowered
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []
