# pyright: standard
"""Branch and link lowerings: the target read before the AMODE 31 link word is written, the mode test of BASSM and BSM, and the addressing-mode instructions."""

from collections.abc import Sequence

from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
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
from tests.covers import NotLanguageFeature, covers
from tests.unit.hlasm.lowering_helpers import (
    describe,
    machine_statement,
    reg_operand,
    storage_operand,
)

LINK = 5
TARGET = 4


def _relative(offset: int) -> RelocImmOperand:
    return RelocImmOperand(kind="RELOC_IMM", section="T", offset=offset)


def _lowered(mnemonic: str, operands: Sequence[Operand]) -> tuple[InstructionBase, ...]:
    emitter = HlasmEmitter()
    OPCODE_LOWERINGS[mnemonic](emitter, machine_statement(mnemonic, operands))
    return emitter.instructions()


def _shape(mnemonic: str, operands: Sequence[Operand]) -> list[str]:
    ir = _lowered(mnemonic, operands)
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    return [
        describe(i, consts)
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


GPRS = "LoadVar __hlasm_gprs"
READ_R4 = [GPRS, "LoadRegion 36+4"]
READ_R12 = [GPRS, "LoadRegion 100+4"]
STORAGE_TARGET = [*READ_R12, "+ reg", "& 2147483647"]
RELATIVE_TARGET = ["LoadVar __hlasm_sect_.T", "+ 40"]
LINK_R5 = [
    "LoadVar __hlasm_sect_.T",
    "+ 8",
    "| 2147483648",
    GPRS,
    "% 4294967296",
    "WriteRegion 44+4",
]
DISPATCH = ["StoreVar __hlasm_target reg", "Branch hl_dispatch"]
LINK_DISPATCH = ["StoreVar __hlasm_target reg", "Branch hl_link_dispatch"]
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
def test_link_forms_compute_the_target_then_write_the_amode_31_link_then_branch_through_the_link_dispatch():
    assert {
        "BAL": _shape("BAL", (reg_operand(LINK), storage_operand(16))),
        "BAS": _shape("BAS", (reg_operand(LINK), storage_operand(16))),
        "BALR": _shape("BALR", (reg_operand(LINK), reg_operand(TARGET))),
        "BASR": _shape("BASR", (reg_operand(LINK), reg_operand(TARGET))),
        "BRAS": _shape("BRAS", (reg_operand(LINK), _relative(40))),
        "BRASL": _shape("BRASL", (reg_operand(LINK), _relative(40))),
        "BALR 5,0": _shape("BALR", (reg_operand(LINK), reg_operand(0))),
        "BASR 5,0": _shape("BASR", (reg_operand(LINK), reg_operand(0))),
    } == {
        "BAL": [*STORAGE_TARGET, *LINK_R5, *LINK_DISPATCH],
        "BAS": [*STORAGE_TARGET, *LINK_R5, *LINK_DISPATCH],
        "BALR": [*READ_R4, *LINK_R5, *LINK_DISPATCH],
        "BASR": [*READ_R4, *LINK_R5, *LINK_DISPATCH],
        "BRAS": [*RELATIVE_TARGET, *LINK_R5, *LINK_DISPATCH],
        "BRASL": [*RELATIVE_TARGET, *LINK_R5, *LINK_DISPATCH],
        "BALR 5,0": LINK_R5,
        "BASR 5,0": LINK_R5,
    }


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_set_mode_forms_branch_only_into_amode_31_and_abend_otherwise():
    assert {
        "BASSM": _shape("BASSM", (reg_operand(LINK), reg_operand(TARGET))),
        "BASSM 5,0": _shape("BASSM", (reg_operand(LINK), reg_operand(0))),
        "BSM": _shape("BSM", (reg_operand(LINK), reg_operand(TARGET))),
        "BSM 0,4": _shape("BSM", (reg_operand(0), reg_operand(TARGET))),
        "BSM 5,0": _shape("BSM", (reg_operand(LINK), reg_operand(0))),
        "BSM 0,0": _shape("BSM", (reg_operand(0), reg_operand(0))),
    } == {
        "BASSM": [*READ_R4, *LINK_R5, *MODE_TEST, *ABEND_S0C1, *LINK_DISPATCH],
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
