# pyright: standard
"""Branch on count and branch on index lowerings: the branch address first, then the operands, the wrapped result written to R1, and a signed or nonzero test before the dispatch."""

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
WORD = 1 << 32
DOUBLEWORD = 1 << 64


def _statement(mnemonic: str, operands: Sequence[Operand]) -> MachineStatement:
    return MachineStatement(
        kind="MACHINE",
        section="T",
        offset=2,
        label="",
        mnemonic=mnemonic,
        base_mnemonic=mnemonic,
        format="",
        length=4,
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


def _read(offset: int, width: int) -> list[str]:
    return [GPRS, f"LoadRegion {offset}+{width}"]


def _write(offset: int, width: int, modulus: int) -> list[str]:
    return [GPRS, f"% {modulus}", f"WriteRegion {offset}+{width}"]


def _signed(modulus: int) -> list[str]:
    return [f"+ {modulus // 2}", f"% {modulus}", f"- {modulus // 2}"]


STORAGE_TARGET = [*_read(100, 4), "+ reg", "& 2147483647"]
RELATIVE_TARGET = ["LoadVar __hlasm_sect_T", "+ 40"]
DISPATCH = ["BranchIf", "StoreVar __hlasm_target reg", "Branch hl_dispatch"]
COUNT_R4 = [*_read(36, 4), "- 1", f"% {WORD}", *_write(36, 4, WORD)]
COUNT_R4_64 = [*_read(32, 8), "- 1", f"% {DOUBLEWORD}", *_write(32, 8, DOUBLEWORD)]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_branch_on_count_takes_the_target_then_decrements_and_tests_nonzero():
    assert {
        "BCT": _shape("BCT", (_reg(4), _storage(16))),
        "BCTG": _shape("BCTG", (_reg(4), _storage(16))),
        "BCTR": _shape("BCTR", (_reg(4), _reg(5))),
        "BCTR 4,0": _shape("BCTR", (_reg(4), _reg(0))),
        "BCTGR": _shape("BCTGR", (_reg(4), _reg(5))),
        "BCTGR 4,0": _shape("BCTGR", (_reg(4), _reg(0))),
        "BRCT": _shape("BRCT", (_reg(4), _relative(40))),
        "BRCTG": _shape("BRCTG", (_reg(4), _relative(40))),
    } == {
        "BCT": [*STORAGE_TARGET, *COUNT_R4, "!= 0", *DISPATCH],
        "BCTG": [*STORAGE_TARGET, *COUNT_R4_64, "!= 0", *DISPATCH],
        "BCTR": [*_read(44, 4), *COUNT_R4, "!= 0", *DISPATCH],
        "BCTR 4,0": COUNT_R4,
        "BCTGR": [*_read(44, 4), *COUNT_R4_64, "!= 0", *DISPATCH],
        "BCTGR 4,0": COUNT_R4_64,
        "BRCT": [*RELATIVE_TARGET, *COUNT_R4, "!= 0", *DISPATCH],
        "BRCTG": [*RELATIVE_TARGET, *COUNT_R4_64, "!= 0", *DISPATCH],
    }


def _index(
    target: Sequence[str], reads: Sequence[int], width: int, comparison: str
) -> list[str]:
    modulus = 1 << (8 * width)
    r1 = reads[-1]
    return [
        *target,
        *(step for offset in reads for step in _read(offset, width)),
        "+ reg",
        f"% {modulus}",
        *_write(r1, width, modulus),
        *_signed(modulus),
        *_signed(modulus),
        f"{comparison} reg",
        *DISPATCH,
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_branch_on_index_reads_increment_and_compare_value_before_writing_r1():
    pair = (_reg(4), _reg(6))
    odd = (_reg(5), _reg(5))
    assert {
        "BXH": _shape("BXH", (*pair, _storage(16))),
        "BXLE": _shape("BXLE", (*pair, _storage(16))),
        "BXHG": _shape("BXHG", (*pair, _storage(16))),
        "BXLEG": _shape("BXLEG", (*pair, _storage(16))),
        "BRXH": _shape("BRXH", (*pair, _relative(40))),
        "BRXLE 5,5": _shape("BRXLE", (*odd, _relative(40))),
        "BRXHG": _shape("BRXHG", (*pair, _relative(40))),
        "BRXLG 5,5": _shape("BRXLG", (*odd, _relative(40))),
    } == {
        "BXH": _index(STORAGE_TARGET, (52, 60, 36), 4, ">"),
        "BXLE": _index(STORAGE_TARGET, (52, 60, 36), 4, "<="),
        "BXHG": _index(STORAGE_TARGET, (48, 56, 32), 8, ">"),
        "BXLEG": _index(STORAGE_TARGET, (48, 56, 32), 8, "<="),
        "BRXH": _index(RELATIVE_TARGET, (52, 60, 36), 4, ">"),
        "BRXLE 5,5": _index(RELATIVE_TARGET, (44, 44, 44), 4, "<="),
        "BRXHG": _index(RELATIVE_TARGET, (48, 56, 32), 8, ">"),
        "BRXLG 5,5": _index(RELATIVE_TARGET, (40, 40, 40), 8, "<="),
    }
