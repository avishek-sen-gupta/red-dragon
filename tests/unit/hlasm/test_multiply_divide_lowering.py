# pyright: standard
"""Multiply and divide lowerings: the register and storage widths they read and write, the CC and overflow trap of the checked forms, the divide-exception checks and the even-odd pair."""

from collections.abc import Sequence

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.machine_statement import MachineStatement
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
from tests.unit.hlasm.lowering_helpers import (
    machine_statement,
    reg_operand,
)

BASE = 12
GPRS = "__hlasm_gprs"
CC = "StoreVar:__hlasm_cc"
OVERFLOW_TRAP = [CC, "BranchIf", "StoreVar:__hlasm_abend", "Halt_"]


def _storage() -> StorageOperand:
    return StorageOperand(
        kind="STORAGE",
        displacement=8,
        index=0,
        base=BASE,
        written=AbsAddress(kind="ABS", value=8),
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


STORAGE = ("LoadRegion", *_gpr(BASE, 4))
DIVIDE_CHECKS = ["BranchIf", "StoreVar:__hlasm_abend", "Halt_"] * 2
PAIR_FORMS = {
    "M": _storage(),
    "MFY": _storage(),
    "MR": reg_operand(6),
    "ML": _storage(),
    "MLR": reg_operand(6),
    "MG": _storage(),
    "MLG": _storage(),
    "MLGR": reg_operand(6),
    "D": _storage(),
    "DR": reg_operand(6),
    "DL": _storage(),
    "DLR": reg_operand(6),
    "DLG": _storage(),
    "DLGR": reg_operand(6),
    "DSG": _storage(),
    "DSGR": reg_operand(6),
    "DSGF": _storage(),
    "DSGFR": reg_operand(6),
}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_multiplies_read_and_write_their_widths_and_only_checked_forms_set_cc():
    lowered = {
        "MS": _lowered(machine_statement("MS", (reg_operand(2), _storage()))),
        "MSGF": _lowered(machine_statement("MSGF", (reg_operand(5), _storage()))),
        "M": _lowered(machine_statement("M", (reg_operand(2), _storage()))),
        "MLGR": _lowered(machine_statement("MLGR", (reg_operand(4), reg_operand(7)))),
        "MGRK": _lowered(
            machine_statement("MGRK", (reg_operand(4), reg_operand(7), reg_operand(9)))
        ),
        "MSC": _lowered(machine_statement("MSC", (reg_operand(2), _storage()))),
        "MSGRKC": _lowered(
            machine_statement(
                "MSGRKC", (reg_operand(5), reg_operand(3), reg_operand(4))
            )
        ),
    }

    assert {m: _accesses(ir) for m, ir in lowered.items()} == {
        "MS": [
            ("LoadRegion", *_gpr(2, 4)),
            STORAGE,
            ("LoadRegion", "storage", 4, 0),
            ("WriteRegion", *_gpr(2, 4)),
        ],
        "MSGF": [
            ("LoadRegion", *_gpr(5, 8)),
            STORAGE,
            ("LoadRegion", "storage", 4, 0),
            ("WriteRegion", *_gpr(5, 8)),
        ],
        "M": [
            ("LoadRegion", *_gpr(3, 4)),
            STORAGE,
            ("LoadRegion", "storage", 4, 0),
            ("WriteRegion", *_gpr(2, 4)),
            ("WriteRegion", *_gpr(3, 4)),
        ],
        "MLGR": [
            ("LoadRegion", *_gpr(5, 8)),
            ("LoadRegion", *_gpr(7, 8)),
            ("WriteRegion", *_gpr(4, 8)),
            ("WriteRegion", *_gpr(5, 8)),
        ],
        "MGRK": [
            ("LoadRegion", *_gpr(9, 8)),
            ("LoadRegion", *_gpr(7, 8)),
            ("WriteRegion", *_gpr(4, 8)),
            ("WriteRegion", *_gpr(5, 8)),
        ],
        "MSC": [
            ("LoadRegion", *_gpr(2, 4)),
            STORAGE,
            ("LoadRegion", "storage", 4, 0),
            ("WriteRegion", *_gpr(2, 4)),
        ],
        "MSGRKC": [
            ("LoadRegion", *_gpr(4, 8)),
            ("LoadRegion", *_gpr(3, 8)),
            ("WriteRegion", *_gpr(5, 8)),
        ],
    }
    assert {m: _control(ir) for m, ir in lowered.items()} == {
        **{m: [] for m in ("MS", "MSGF", "M", "MLGR", "MGRK")},
        "MSC": OVERFLOW_TRAP,
        "MSGRKC": OVERFLOW_TRAP,
    }
    assert {m: _strings(ir) for m, ir in lowered.items()} == {
        **{m: [] for m in ("MS", "MSGF", "M", "MLGR", "MGRK")},
        "MSC": ["S0C8"],
        "MSGRKC": ["S0C8"],
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_divides_check_the_divisor_and_quotient_before_writing_the_pair():
    lowered = {
        "D": _lowered(machine_statement("D", (reg_operand(2), _storage()))),
        "DLR": _lowered(machine_statement("DLR", (reg_operand(2), reg_operand(7)))),
        "DLG": _lowered(machine_statement("DLG", (reg_operand(4), _storage()))),
        "DSGFR": _lowered(machine_statement("DSGFR", (reg_operand(4), reg_operand(7)))),
    }

    assert {m: _accesses(ir) for m, ir in lowered.items()} == {
        "D": [
            ("LoadRegion", *_gpr(2, 4)),
            ("LoadRegion", *_gpr(3, 4)),
            STORAGE,
            ("LoadRegion", "storage", 4, 0),
            ("WriteRegion", *_gpr(2, 4)),
            ("WriteRegion", *_gpr(3, 4)),
        ],
        "DLR": [
            ("LoadRegion", *_gpr(2, 4)),
            ("LoadRegion", *_gpr(3, 4)),
            ("LoadRegion", *_gpr(7, 4)),
            ("WriteRegion", *_gpr(2, 4)),
            ("WriteRegion", *_gpr(3, 4)),
        ],
        "DLG": [
            ("LoadRegion", *_gpr(4, 8)),
            ("LoadRegion", *_gpr(5, 8)),
            STORAGE,
            ("LoadRegion", "storage", 8, 0),
            ("WriteRegion", *_gpr(4, 8)),
            ("WriteRegion", *_gpr(5, 8)),
        ],
        "DSGFR": [
            ("LoadRegion", *_gpr(5, 8)),
            ("LoadRegion", *_gpr(7, 4)),
            ("WriteRegion", *_gpr(4, 8)),
            ("WriteRegion", *_gpr(5, 8)),
        ],
    }
    assert {m: (_control(ir), _strings(ir)) for m, ir in lowered.items()} == {
        m: (DIVIDE_CHECKS, ["S0C9", "S0C9"]) for m in lowered
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_odd_first_register_of_a_pair_form_is_a_specification_exception():
    lowered = {
        **{
            m: _lowered(machine_statement(m, (reg_operand(3), second)))
            for m, second in PAIR_FORMS.items()
        },
        "MGRK": _lowered(
            machine_statement("MGRK", (reg_operand(3), reg_operand(6), reg_operand(8)))
        ),
    }

    assert {
        m: (_accesses(ir), _control(ir), _strings(ir)) for m, ir in lowered.items()
    } == {m: ([], ["StoreVar:__hlasm_abend", "Halt_"], ["S0C6"]) for m in lowered}
