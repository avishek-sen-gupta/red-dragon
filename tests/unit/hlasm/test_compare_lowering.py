# pyright: standard
"""Compare lowerings: the operand widths they read, nothing written, and the CC as the only state set."""

from collections.abc import Sequence

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
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
from tests.unit.hlasm.lowering_helpers import (
    imm_operand,
    machine_statement,
    mask_operand,
    reg_operand,
    storage_operand,
)

BASE = 12
GPRS = "__hlasm_gprs"
CC = "__hlasm_cc"


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
        "CGF": _lowered(machine_statement("CGF", (reg_operand(2), storage_operand(8)))),
        "CR": _lowered(machine_statement("CR", (reg_operand(2), reg_operand(3)))),
        "CLGFR": _lowered(machine_statement("CLGFR", (reg_operand(2), reg_operand(3)))),
        "CHHSI": _lowered(
            machine_statement("CHHSI", (storage_operand(8), imm_operand(-2)))
        ),
        "CLI": _lowered(
            machine_statement("CLI", (storage_operand(8), imm_operand(0x80)))
        ),
        "CLGHSI": _lowered(
            machine_statement("CLGHSI", (storage_operand(8), imm_operand(0xFFFF)))
        ),
        "CHRL": _lowered(machine_statement("CHRL", (reg_operand(2), _relative(6)))),
        "CLM": _lowered(
            machine_statement(
                "CLM", (reg_operand(2), mask_operand(0b1010), storage_operand(8))
            )
        ),
        "CLMY": _lowered(
            machine_statement(
                "CLMY", (reg_operand(2), mask_operand(0), storage_operand(8))
            )
        ),
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
    lowered = {
        m: _lowered(machine_statement(m, (reg_operand(2), _relative(6))))
        for m in ("CRL", "CGRL", "CGFRL", "CLRL", "CLGRL", "CLGFRL", "CHRL", "CLGHRL")
    }
    branches = {
        m: [i for i in ir if isinstance(i, BranchIf)] for m, ir in lowered.items()
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
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []
