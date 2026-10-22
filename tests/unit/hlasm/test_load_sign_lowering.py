# pyright: standard
"""Load and test, complement, positive and negative lowerings: the operand widths they read and write, the CC, and the fixed-point-overflow trap only where the maximum negative number can overflow."""

from collections.abc import Sequence

from hlasm_asg.program.machine_statement import MachineStatement
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
from tests.unit.hlasm.lowering_helpers import (
    machine_statement,
    reg_operand,
    storage_operand,
)
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
def test_each_form_reads_and_writes_its_operand_widths_and_only_the_overflowing_forms_trap():
    lowered = {
        "LT": _lowered(machine_statement("LT", (reg_operand(2), storage_operand(8)))),
        "LTGF": _lowered(
            machine_statement("LTGF", (reg_operand(2), storage_operand(8)))
        ),
        "LTR": _lowered(machine_statement("LTR", (reg_operand(5), reg_operand(3)))),
        "LTGR": _lowered(machine_statement("LTGR", (reg_operand(5), reg_operand(3)))),
        "LCR": _lowered(machine_statement("LCR", (reg_operand(5), reg_operand(3)))),
        "LCGR": _lowered(machine_statement("LCGR", (reg_operand(5), reg_operand(3)))),
        "LCGFR": _lowered(machine_statement("LCGFR", (reg_operand(5), reg_operand(3)))),
        "LPR": _lowered(machine_statement("LPR", (reg_operand(5), reg_operand(3)))),
        "LPGR": _lowered(machine_statement("LPGR", (reg_operand(5), reg_operand(3)))),
        "LPGFR": _lowered(machine_statement("LPGFR", (reg_operand(5), reg_operand(3)))),
        "LNR": _lowered(machine_statement("LNR", (reg_operand(5), reg_operand(3)))),
        "LNGR": _lowered(machine_statement("LNGR", (reg_operand(5), reg_operand(3)))),
        "LNGFR": _lowered(machine_statement("LNGFR", (reg_operand(5), reg_operand(3)))),
    }
    word_from_3_to_5 = [("LoadRegion", *_gpr(3, 4)), ("WriteRegion", *_gpr(5, 4))]
    doubleword_from_3_to_5 = [("LoadRegion", *_gpr(3, 8)), ("WriteRegion", *_gpr(5, 8))]
    word_to_doubleword = [("LoadRegion", *_gpr(3, 4)), ("WriteRegion", *_gpr(5, 8))]

    assert {m: _accesses(ir) for m, ir in lowered.items()} == {
        "LT": [
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 4, 0),
            ("WriteRegion", *_gpr(2, 4)),
        ],
        "LTGF": [
            ("LoadRegion", *_gpr(BASE, 4)),
            ("LoadRegion", "storage", 4, 0),
            ("WriteRegion", *_gpr(2, 8)),
        ],
        "LTR": word_from_3_to_5,
        "LTGR": doubleword_from_3_to_5,
        "LCR": word_from_3_to_5,
        "LCGR": doubleword_from_3_to_5,
        "LCGFR": word_to_doubleword,
        "LPR": word_from_3_to_5,
        "LPGR": doubleword_from_3_to_5,
        "LPGFR": word_to_doubleword,
        "LNR": word_from_3_to_5,
        "LNGR": doubleword_from_3_to_5,
        "LNGFR": word_to_doubleword,
    }
    trapping = {"LCR", "LCGR", "LPR", "LPGR"}
    assert {m: _control(ir) for m, ir in lowered.items()} == {
        m: OVERFLOW_TRAP if m in trapping else ["StoreVar:__hlasm_cc"] for m in lowered
    }
    assert {m: _strings(ir) for m, ir in lowered.items()} == {
        m: ["S0C8"] if m in trapping else [] for m in lowered
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []


def _trap_taken(
    mnemonic: str, program_mask: int, value: int
) -> tuple[bool, int, list[int] | SymbolicValue]:
    emitter = HlasmEmitter()
    mask = emitter.int_(program_mask)
    emitter.emit_inst(StoreVar(name=PROGRAM_MASK_VAR, value_reg=mask))
    emitter.store_gr32(3, emitter.int_(value))
    OPCODE_LOWERINGS[mnemonic](
        emitter, machine_statement(mnemonic, (reg_operand(2), reg_operand(3)))
    )
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
        _trap_taken("LCR", OVERFLOW_UNMASKED, 0x80000000),
        _trap_taken("LPR", OVERFLOW_MASKED, 0x80000000),
        _trap_taken("LPR", OVERFLOW_UNMASKED, 0x80000000),
        _trap_taken("LCR", OVERFLOW_UNMASKED, 5),
    ] == [
        (True, 3, [0x80, 0, 0, 0]),
        (False, 3, [0x80, 0, 0, 0]),
        (True, 3, [0x80, 0, 0, 0]),
        (False, 1, [0xFF, 0xFF, 0xFF, 0xFB]),
    ]
