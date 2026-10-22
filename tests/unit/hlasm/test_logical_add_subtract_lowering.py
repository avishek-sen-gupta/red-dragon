# pyright: standard
"""Logical add and subtract lowerings: the operand widths they read and write, the carry-in they read, and the CC with no trap."""

from collections.abc import Sequence

from hlasm_asg.program.machine_statement import MachineStatement
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
    reg_operand,
    storage_operand,
)

BASE = 12
GPRS = "__hlasm_gprs"
CC = "__hlasm_cc"


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
        "ALGF": _lowered(
            machine_statement("ALGF", (reg_operand(2), storage_operand(8)))
        ),
        "ALRK": _lowered(
            machine_statement("ALRK", (reg_operand(5), reg_operand(3), reg_operand(4)))
        ),
        "SLGFR": _lowered(machine_statement("SLGFR", (reg_operand(2), reg_operand(3)))),
        "ALCR": _lowered(machine_statement("ALCR", (reg_operand(2), reg_operand(3)))),
        "SLBG": _lowered(
            machine_statement("SLBG", (reg_operand(2), storage_operand(8)))
        ),
        "ALHSIK": _lowered(
            machine_statement(
                "ALHSIK", (reg_operand(5), reg_operand(3), imm_operand(-2))
            )
        ),
        "ALSI": _lowered(
            machine_statement("ALSI", (storage_operand(8), imm_operand(-1)))
        ),
        "ALGSI": _lowered(
            machine_statement("ALGSI", (storage_operand(8), imm_operand(255)))
        ),
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
