# pyright: standard
"""Branch and link lowerings: the target read before the AMODE 31 link word is written, the mode test of BASSM and BSM, and the addressing-mode instructions."""

from collections.abc import Mapping, Sequence
from functools import singledispatch

from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reg_operand import RegOperand
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes import OPCODE_LOWERINGS
from interpreter.instructions import (
    Binop,
    Branch,
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
from interpreter.register import Register
from tests.covers import NotLanguageFeature, covers

BASE = 12
LINK = 5
TARGET = 4


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


def _storage(displacement: int) -> StorageOperand:
    return StorageOperand(kind="STORAGE", displacement=displacement, index=0, base=BASE)


def _relative(offset: int) -> RelocImmOperand:
    return RelocImmOperand(kind="RELOC_IMM", section="T", offset=offset)


def _lowered(mnemonic: str, operands: Sequence[Operand]) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[mnemonic](emitter, _statement(mnemonic, operands))
    return emitter.instructions()


def _shape(mnemonic: str, operands: Sequence[Operand]) -> list[str]:
    ir = _lowered(mnemonic, operands)
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    return [
        _describe(i, consts)
        for i in ir
        if isinstance(
            i,
            (
                LoadVar,
                StoreVar,
                BranchIf,
                Branch,
                LoadRegion,
                WriteRegion,
                Binop,
                Halt_,
                Symbolic,
            ),
        )
    ]


@singledispatch
def _describe(i: InstructionBase, consts: Mapping[Register, int | str]) -> str:
    return type(i).__name__


@_describe.register
def _describe_load_var(i: LoadVar, consts: Mapping[Register, int | str]) -> str:
    return f"LoadVar {i.name}"


@_describe.register
def _describe_store_var(i: StoreVar, consts: Mapping[Register, int | str]) -> str:
    return f"StoreVar {i.name} {consts.get(i.value_reg, 'reg')}"


@_describe.register
def _describe_load_region(i: LoadRegion, consts: Mapping[Register, int | str]) -> str:
    return f"LoadRegion {consts[i.offset_reg]}+{i.length}"


@_describe.register
def _describe_write_region(i: WriteRegion, consts: Mapping[Register, int | str]) -> str:
    return f"WriteRegion {consts[i.offset_reg]}+{i.length}"


@_describe.register
def _describe_binop(i: Binop, consts: Mapping[Register, int | str]) -> str:
    return f"{i.operator.value} {consts.get(i.right, 'reg')}"


@_describe.register
def _describe_branch(i: Branch, consts: Mapping[Register, int | str]) -> str:
    return f"Branch {i.label}"


GPRS = "LoadVar __hlasm_gprs"
READ_R4 = [GPRS, "LoadRegion 36+4"]
READ_R12 = [GPRS, "LoadRegion 100+4"]
STORAGE_TARGET = [*READ_R12, "+ reg", "& 2147483647"]
RELATIVE_TARGET = ["LoadVar __hlasm_sect_T", "+ 40"]
LINK_R5 = [
    "LoadVar __hlasm_sect_T",
    "+ 8",
    "| 2147483648",
    GPRS,
    "% 4294967296",
    "WriteRegion 44+4",
]
DISPATCH = ["StoreVar __hlasm_target reg", "Branch hl_dispatch"]
ABEND_S0C1 = ["StoreVar __hlasm_abend S0C1", "Halt_"]
MODE_TEST = [
    "& 2147483647",
    "== 4080",
    "BranchIf",
    "& 2147483649",
    "== 2147483648",
    "BranchIf",
]
SET_MODE_BIT_R5 = [
    GPRS,
    "LoadRegion 44+4",
    "| 2147483648",
    GPRS,
    "% 4294967296",
    "WriteRegion 44+4",
]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_link_forms_compute_the_target_then_write_the_amode_31_link_then_branch():
    assert {
        "BAL": _shape("BAL", (_reg(LINK), _storage(16))),
        "BAS": _shape("BAS", (_reg(LINK), _storage(16))),
        "BALR": _shape("BALR", (_reg(LINK), _reg(TARGET))),
        "BASR": _shape("BASR", (_reg(LINK), _reg(TARGET))),
        "BRAS": _shape("BRAS", (_reg(LINK), _relative(40))),
        "BRASL": _shape("BRASL", (_reg(LINK), _relative(40))),
        "BALR 5,0": _shape("BALR", (_reg(LINK), _reg(0))),
        "BASR 5,0": _shape("BASR", (_reg(LINK), _reg(0))),
    } == {
        "BAL": [*STORAGE_TARGET, *LINK_R5, *DISPATCH],
        "BAS": [*STORAGE_TARGET, *LINK_R5, *DISPATCH],
        "BALR": [*READ_R4, *LINK_R5, *DISPATCH],
        "BASR": [*READ_R4, *LINK_R5, *DISPATCH],
        "BRAS": [*RELATIVE_TARGET, *LINK_R5, *DISPATCH],
        "BRASL": [*RELATIVE_TARGET, *LINK_R5, *DISPATCH],
        "BALR 5,0": LINK_R5,
        "BASR 5,0": LINK_R5,
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_set_mode_forms_branch_only_into_amode_31_and_abend_otherwise():
    assert {
        "BASSM": _shape("BASSM", (_reg(LINK), _reg(TARGET))),
        "BASSM 5,0": _shape("BASSM", (_reg(LINK), _reg(0))),
        "BSM": _shape("BSM", (_reg(LINK), _reg(TARGET))),
        "BSM 0,4": _shape("BSM", (_reg(0), _reg(TARGET))),
        "BSM 5,0": _shape("BSM", (_reg(LINK), _reg(0))),
        "BSM 0,0": _shape("BSM", (_reg(0), _reg(0))),
    } == {
        "BASSM": [*READ_R4, *LINK_R5, *MODE_TEST, *ABEND_S0C1, *DISPATCH],
        "BASSM 5,0": LINK_R5,
        "BSM": [*READ_R4, *SET_MODE_BIT_R5, *MODE_TEST, *ABEND_S0C1, *DISPATCH],
        "BSM 0,4": [*READ_R4, *MODE_TEST, *ABEND_S0C1, *DISPATCH],
        "BSM 5,0": SET_MODE_BIT_R5,
        "BSM 0,0": [],
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_addressing_mode_instructions_stay_in_amode_31():
    assert {
        mnemonic: _shape(mnemonic, ())
        for mnemonic in ("SAM24", "SAM31", "SAM64", "TAM")
    } == {
        "SAM24": ABEND_S0C1,
        "SAM31": [],
        "SAM64": ABEND_S0C1,
        "TAM": ["StoreVar __hlasm_cc 1"],
    }
