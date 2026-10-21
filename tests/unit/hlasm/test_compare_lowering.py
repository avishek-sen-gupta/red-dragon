# pyright: standard
"""Compare lowerings: the operand widths they read, nothing written, and the CC as the only state set."""

from collections.abc import Sequence

from hlasm_asg.program.imm_operand import ImmOperand
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.mask_operand import MaskOperand
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reg_operand import RegOperand
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
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


def _mask(value: int) -> MaskOperand:
    return MaskOperand(kind="MASK", value=value)


def _storage(displacement: int) -> StorageOperand:
    return StorageOperand(kind="STORAGE", displacement=displacement, index=0, base=BASE)


def _relative(offset: int) -> RelocImmOperand:
    return RelocImmOperand(kind="RELOC_IMM", section="T", offset=offset)


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


def _control(ir: Sequence[InstructionBase]) -> list[str]:
    return [
        f"StoreVar:{i.name}" if isinstance(i, StoreVar) else type(i).__name__
        for i in ir
        if isinstance(i, BranchIf | Halt_ | StoreVar)
    ]


def _gpr(r: int, width: int) -> tuple[str, int, int]:
    return "gpr", width, 8 * r + 8 - width


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_each_form_reads_its_operand_widths_and_sets_only_the_cc():
    lowered = {
        "CGF": _lowered(_statement("CGF", (_reg(2), _storage(8)))),
        "CR": _lowered(_statement("CR", (_reg(2), _reg(3)))),
        "CLGFR": _lowered(_statement("CLGFR", (_reg(2), _reg(3)))),
        "CHHSI": _lowered(_statement("CHHSI", (_storage(8), _imm(-2)))),
        "CLI": _lowered(_statement("CLI", (_storage(8), _imm(0x80)))),
        "CLGHSI": _lowered(_statement("CLGHSI", (_storage(8), _imm(0xFFFF)))),
        "CHRL": _lowered(_statement("CHRL", (_reg(2), _relative(6)))),
        "CLM": _lowered(_statement("CLM", (_reg(2), _mask(0b1010), _storage(8)))),
        "CLMY": _lowered(_statement("CLMY", (_reg(2), _mask(0), _storage(8)))),
    }

    assert {m: _accesses(ir) for m, ir in lowered.items()} == {
        "CGF": [
            ("LoadRegion", *_gpr(2, 8)),
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 4, 0),
        ],
        "CR": [("LoadRegion", *_gpr(2, 4)), ("LoadRegion", *_gpr(3, 4))],
        "CLGFR": [("LoadRegion", *_gpr(2, 8)), ("LoadRegion", *_gpr(3, 4))],
        "CHHSI": [("LoadRegion", *_gpr(BASE, 4)), ("LoadRegion", "storage", 2, 0)],
        "CLI": [("LoadRegion", *_gpr(BASE, 4)), ("LoadRegion", "storage", 1, 0)],
        "CLGHSI": [("LoadRegion", *_gpr(BASE, 4)), ("LoadRegion", "storage", 8, 0)],
        "CHRL": [("LoadRegion", *_gpr(2, 4)), ("LoadRegion", "storage", 2, 0)],
        "CLM": [
            ("LoadRegion", *_gpr(2, 4)),
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 2, 0),
        ],
        "CLMY": [],
    }
    assert {m: _control(ir) for m, ir in lowered.items()} == {
        m: [f"StoreVar:{CC}"] for m in lowered
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_word_and_doubleword_relative_forms_check_alignment_and_halfword_forms_do_not():
    branches = {
        m: [
            i
            for i in _lowered(_statement(m, (_reg(2), _relative(6))))
            if isinstance(i, BranchIf)
        ]
        for m in ("CRL", "CGRL", "CGFRL", "CLRL", "CLGRL", "CLGFRL", "CHRL", "CLGHRL")
    }

    assert {m: len(found) for m, found in branches.items()} == {
        "CRL": 1,
        "CGRL": 1,
        "CGFRL": 1,
        "CLRL": 1,
        "CLGRL": 1,
        "CLGFRL": 1,
        "CHRL": 0,
        "CLGHRL": 0,
    }
