# pyright: standard
"""Shift and rotate lowerings: the register widths they read and write, no storage access, the CC, the overflow trap, the even-odd pair and the RISBG-family masks."""

from collections.abc import Sequence

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.hlasm.opcodes.shift_rotate import CONTROL_BIT
from interpreter.hlasm.register_span import HIGH_WORD, LOW_WORD, WHOLE_REGISTER
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
)

BASE = 12
GPRS = "__hlasm_gprs"
CC = "StoreVar:__hlasm_cc"
OVERFLOW_TRAP = [CC, "BranchIf", "StoreVar:__hlasm_abend", "Halt_"]


def _amount(displacement: int, base: int) -> StorageOperand:
    return StorageOperand(
        kind="STORAGE",
        displacement=displacement,
        index=0,
        base=base,
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
def test_shifts_read_and_write_registers_only_and_set_cc_only_when_signed():
    lowered = {
        "SLL": _lowered(machine_statement("SLL", (reg_operand(2), _amount(5, 0)))),
        "SLLG": _lowered(
            machine_statement(
                "SLLG", (reg_operand(5), reg_operand(3), _amount(7, BASE))
            )
        ),
        "RLL": _lowered(
            machine_statement("RLL", (reg_operand(5), reg_operand(3), _amount(1, 0)))
        ),
        "SRAK": _lowered(
            machine_statement("SRAK", (reg_operand(5), reg_operand(3), _amount(4, 0)))
        ),
        "SLDL": _lowered(machine_statement("SLDL", (reg_operand(2), _amount(4, 0)))),
        "SLA": _lowered(machine_statement("SLA", (reg_operand(2), _amount(1, 0)))),
        "SLDA": _lowered(machine_statement("SLDA", (reg_operand(4), _amount(1, 0)))),
    }

    assert {m: _accesses(ir) for m, ir in lowered.items()} == {
        "SLL": [("LoadRegion", *_gpr(2, 4)), ("WriteRegion", *_gpr(2, 4))],
        "SLLG": [
            ("LoadRegion", *_gpr(3, 8)),
            ("LoadRegion", *_gpr(BASE, 4)),
            ("WriteRegion", *_gpr(5, 8)),
        ],
        "RLL": [("LoadRegion", *_gpr(3, 4)), ("WriteRegion", *_gpr(5, 4))],
        "SRAK": [("LoadRegion", *_gpr(3, 4)), ("WriteRegion", *_gpr(5, 4))],
        "SLDL": [
            ("LoadRegion", *_gpr(2, 4)),
            ("LoadRegion", *_gpr(3, 4)),
            ("WriteRegion", *_gpr(2, 4)),
            ("WriteRegion", *_gpr(3, 4)),
        ],
        "SLA": [("LoadRegion", *_gpr(2, 4)), ("WriteRegion", *_gpr(2, 4))],
        "SLDA": [
            ("LoadRegion", *_gpr(4, 4)),
            ("LoadRegion", *_gpr(5, 4)),
            ("WriteRegion", *_gpr(4, 4)),
            ("WriteRegion", *_gpr(5, 4)),
        ],
    }
    assert {m: _control(ir) for m, ir in lowered.items()} == {
        "SLL": [],
        "SLLG": [],
        "RLL": [],
        "SRAK": [CC],
        "SLDL": [],
        "SLA": OVERFLOW_TRAP,
        "SLDA": OVERFLOW_TRAP,
    }
    assert {m: _strings(ir) for m, ir in lowered.items()} == {
        **{m: [] for m in ("SLL", "SLLG", "RLL", "SRAK", "SLDL")},
        "SLA": ["S0C8"],
        "SLDA": ["S0C8"],
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_odd_first_register_of_a_double_shift_is_a_specification_exception():
    lowered = {
        m: _lowered(machine_statement(m, (reg_operand(3), _amount(1, 0))))
        for m in ("SLDL", "SRDL", "SLDA", "SRDA")
    }

    assert {
        m: (_accesses(ir), _control(ir), _strings(ir)) for m, ir in lowered.items()
    } == {m: ([], ["StoreVar:__hlasm_abend", "Halt_"], ["S0C6"]) for m in lowered}


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_register_spans_select_a_wrapping_range_of_bit_positions():
    assert [
        WHOLE_REGISTER.selected(40, CONTROL_BIT | 43),
        WHOLE_REGISTER.selected(CONTROL_BIT | 62, 1),
        WHOLE_REGISTER.selected(0, 63),
        HIGH_WORD.selected(24, CONTROL_BIT | 7),
        LOW_WORD.selected(8, 11),
        LOW_WORD.selected(31, 0),
    ] == [
        0x00000000_00F00000,
        0xC0000000_00000003,
        0xFFFFFFFF_FFFFFFFF,
        0xFF0000FF_00000000,
        0x00000000_00F00000,
        0x00000000_80000001,
    ]
    assert [WHOLE_REGISTER.word(), HIGH_WORD.word(), LOW_WORD.word()] == [
        0xFFFFFFFF_FFFFFFFF,
        0xFFFFFFFF_00000000,
        0x00000000_FFFFFFFF,
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_rotate_selected_bits_forms_write_r1_unless_testing_and_set_cc_as_defined():
    lowered = {
        "RISBG": _lowered(
            machine_statement(
                "RISBG",
                (
                    reg_operand(5),
                    reg_operand(3),
                    imm_operand(40),
                    imm_operand(43),
                    imm_operand(4),
                ),
            )
        ),
        "RISBGN": _lowered(
            machine_statement(
                "RISBGN",
                (
                    reg_operand(5),
                    reg_operand(3),
                    imm_operand(40),
                    imm_operand(CONTROL_BIT | 43),
                ),
            )
        ),
        "RISBHG": _lowered(
            machine_statement(
                "RISBHG",
                (
                    reg_operand(5),
                    reg_operand(3),
                    imm_operand(0),
                    imm_operand(31),
                    imm_operand(32),
                ),
            )
        ),
        "RNSBG test": _lowered(
            machine_statement(
                "RNSBG",
                (
                    reg_operand(5),
                    reg_operand(3),
                    imm_operand(CONTROL_BIT | 40),
                    imm_operand(43),
                ),
            )
        ),
        "ROSBG": _lowered(
            machine_statement(
                "ROSBG",
                (
                    reg_operand(5),
                    reg_operand(3),
                    imm_operand(62),
                    imm_operand(1),
                    imm_operand(-4),
                ),
            )
        ),
    }

    assert {m: _accesses(ir) for m, ir in lowered.items()} == {
        "RISBG": [
            ("LoadRegion", *_gpr(3, 8)),
            ("LoadRegion", *_gpr(5, 8)),
            ("WriteRegion", *_gpr(5, 8)),
        ],
        "RISBGN": [
            ("LoadRegion", *_gpr(3, 8)),
            ("LoadRegion", *_gpr(5, 8)),
            ("WriteRegion", *_gpr(5, 8)),
        ],
        "RISBHG": [
            ("LoadRegion", *_gpr(3, 8)),
            ("LoadRegion", *_gpr(5, 8)),
            ("WriteRegion", *_gpr(5, 8)),
        ],
        "RNSBG test": [("LoadRegion", *_gpr(3, 8)), ("LoadRegion", *_gpr(5, 8))],
        "ROSBG": [
            ("LoadRegion", *_gpr(3, 8)),
            ("LoadRegion", *_gpr(5, 8)),
            ("WriteRegion", *_gpr(5, 8)),
        ],
    }
    assert {m: _control(ir) for m, ir in lowered.items()} == {
        "RISBG": [CC],
        "RISBGN": [],
        "RISBHG": [],
        "RNSBG test": [CC],
        "ROSBG": [CC],
    }
    assert [i for ir in lowered.values() for i in ir if isinstance(i, Symbolic)] == []
