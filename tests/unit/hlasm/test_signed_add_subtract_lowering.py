# pyright: standard
"""Signed add and subtract lowerings: the operand widths they read and write, the CC, and the fixed-point-overflow trap."""

from collections.abc import Sequence

from hlasm_asg.program.imm_operand import ImmOperand
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reg_operand import RegOperand
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.hlasm.hlasm_constants import PROGRAM_MASK_VAR
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.machine import machine_allocation
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
from interpreter.var_name import VarName
from interpreter.vm.vm_types import SymbolicValue
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.straight_line_vm import register_value, run_straight_line

BASE = 12
GPRS = "__hlasm_gprs"
OVERFLOW_TRAP = [
    "StoreVar:__hlasm_cc",
    "BranchIf",
    "StoreVar:__hlasm_abend",
    "Halt_",
]
OVERFLOW_UNMASKED = 0b1110
OVERFLOW_MASKED = 0b0110


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
    return StorageOperand(kind="STORAGE", displacement=displacement, index=0, base=BASE)


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


def _strings(ir: Sequence[InstructionBase]) -> list[str]:
    return [i.value for i in ir if isinstance(i, Const) and isinstance(i.value, str)]


def _gpr(r: int, width: int) -> tuple[str, int, int]:
    return "gpr", width, 8 * r + 8 - width


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_each_form_reads_and_writes_its_operand_widths_then_sets_cc_and_traps():
    lowered = {
        "AGF": _lowered(_statement("AGF", (_reg(2), _storage(8)))),
        "AH": _lowered(_statement("AH", (_reg(2), _storage(8)))),
        "ARK": _lowered(_statement("ARK", (_reg(5), _reg(3), _reg(4)))),
        "AGHIK": _lowered(_statement("AGHIK", (_reg(5), _reg(3), _imm(-1)))),
        "ASI": _lowered(_statement("ASI", (_storage(8), _imm(-5)))),
        "AGSI": _lowered(_statement("AGSI", (_storage(8), _imm(255)))),
    }

    assert {m: _accesses(ir) for m, ir in lowered.items()} == {
        "AGF": [
            ("LoadRegion", *_gpr(2, 8)),
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 4, 0),
            ("WriteRegion", *_gpr(2, 8)),
        ],
        "AH": [
            ("LoadRegion", *_gpr(2, 4)),
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 2, 0),
            ("WriteRegion", *_gpr(2, 4)),
        ],
        "ARK": [
            ("LoadRegion", *_gpr(3, 4)),
            ("LoadRegion", *_gpr(4, 4)),
            ("WriteRegion", *_gpr(5, 4)),
        ],
        "AGHIK": [
            ("LoadRegion", *_gpr(3, 8)),
            ("WriteRegion", *_gpr(5, 8)),
        ],
        "ASI": [
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 4, 0),
            ("WriteRegion", "storage", 4, 0),
        ],
        "AGSI": [
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 8, 0),
            ("WriteRegion", "storage", 8, 0),
        ],
    }
    assert {m: _control(ir) for m, ir in lowered.items()} == {
        m: OVERFLOW_TRAP for m in lowered
    }
    assert {m: _strings(ir) for m, ir in lowered.items()} == {
        m: ["S0C8"] for m in lowered
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []


def _trap_taken(
    program_mask: int, left: int, right: int
) -> tuple[bool, int, list[int] | SymbolicValue]:
    emitter = HlasmEmitter()
    mask = emitter.int_(program_mask)
    emitter.emit_inst(StoreVar(name=PROGRAM_MASK_VAR, value_reg=mask))
    emitter.store_gr32(2, emitter.int_(left))
    emitter.store_gr32(3, emitter.int_(right))
    OPCODE_LOWERINGS["AR"](emitter, _statement("AR", (_reg(2), _reg(3))))
    ir = emitter.instructions()
    branch = next(i for i in ir if isinstance(i, BranchIf))
    vm = run_straight_line((*machine_allocation(), *ir[: ir.index(branch)]), {})
    frame = vm.current_frame.local_vars
    return (
        bool(register_value(vm, branch.cond_reg).value),
        frame[VarName("__hlasm_cc")].value,
        vm.load(frame[VarName(GPRS)].value + 8 * 2 + 4, 4),
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_overflow_traps_only_when_the_fixed_point_overflow_mask_is_one():
    assert [
        _trap_taken(OVERFLOW_UNMASKED, 0x7FFFFFFF, 1),
        _trap_taken(OVERFLOW_MASKED, 0x7FFFFFFF, 1),
        _trap_taken(OVERFLOW_UNMASKED, 5, 1),
    ] == [
        (True, 3, [0x80, 0, 0, 0]),
        (False, 3, [0x80, 0, 0, 0]),
        (False, 2, [0, 0, 0, 6]),
    ]
