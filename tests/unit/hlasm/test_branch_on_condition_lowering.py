# pyright: standard
"""Branch on condition lowerings: the mask test on the CC, the target each form computes, and the forms that lower to nothing."""

from collections.abc import Mapping, Sequence
from functools import singledispatch

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


def _mask(value: int) -> MaskOperand:
    return MaskOperand(kind="MASK", value=value)


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


def _shape(ir: Sequence[InstructionBase]) -> list[str]:
    consts = {i.result_reg: i.value for i in ir if isinstance(i, Const)}
    return [
        _describe(i, consts)
        for i in ir
        if isinstance(i, (LoadVar, StoreVar, BranchIf, Branch, LoadRegion, Binop))
    ]


@singledispatch
def _describe(i: InstructionBase, consts: Mapping[Register, int | str]) -> str:
    return type(i).__name__


@_describe.register
def _describe_load_var(i: LoadVar, consts: Mapping[Register, int | str]) -> str:
    return f"LoadVar {i.name}"


@_describe.register
def _describe_store_var(i: StoreVar, consts: Mapping[Register, int | str]) -> str:
    return f"StoreVar {i.name}"


@_describe.register
def _describe_load_region(i: LoadRegion, consts: Mapping[Register, int | str]) -> str:
    return f"LoadRegion {consts[i.offset_reg]}+{i.length}"


@_describe.register
def _describe_binop(i: Binop, consts: Mapping[Register, int | str]) -> str:
    return f"{i.operator.value} {consts.get(i.right, 'reg')}"


@_describe.register
def _describe_branch(i: Branch, consts: Mapping[Register, int | str]) -> str:
    return f"Branch {i.label}"


GPR_12 = ["LoadVar __hlasm_gprs", "LoadRegion 100+4"]
CC_TEST = ["LoadVar __hlasm_cc", ">> reg", "& 4", "!= 0", "BranchIf"]
DISPATCH = ["StoreVar __hlasm_target", "Branch hl_dispatch"]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_conditional_masks_test_the_cc_bit_then_branch_to_their_target():
    assert [
        _shape(_lowered("BC", (_mask(4), _storage(16)))),
        _shape(_lowered("BRC", (_mask(4), _relative(40)))),
        _shape(_lowered("BRCL", (_mask(4), _relative(40)))),
        _shape(_lowered("BIC", (_mask(4), _storage(16)))),
        _shape(_lowered("BCR", (_mask(4), _reg(BASE)))),
    ] == [
        [*CC_TEST, *GPR_12, "+ reg", "& 2147483647", *DISPATCH],
        [*CC_TEST, "LoadVar __hlasm_sect_T", "+ 40", *DISPATCH],
        [*CC_TEST, "LoadVar __hlasm_sect_T", "+ 40", *DISPATCH],
        [
            *CC_TEST,
            *GPR_12,
            "+ reg",
            "& 2147483647",
            "LoadRegion 0+8",
            *DISPATCH,
        ],
        [*CC_TEST, *GPR_12, *DISPATCH],
    ]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_mask_fifteen_branches_without_a_test_and_no_ops_lower_to_nothing():
    lowered = {
        "BC": _lowered("BC", (_mask(15), _storage(16))),
        "BRC": _lowered("BRC", (_mask(15), _relative(40))),
        "BIC": _lowered("BIC", (_mask(15), _storage(16))),
    }
    nothing = [
        _lowered("BC", (_mask(0), _storage(16))),
        _lowered("BRC", (_mask(0), _relative(40))),
        _lowered("BRCL", (_mask(0), _relative(40))),
        _lowered("BIC", (_mask(0), _storage(16))),
        _lowered("BCR", (_mask(0), _reg(BASE))),
        _lowered("BCR", (_mask(15), _reg(0))),
        _lowered("BCR", (_mask(14), _reg(0))),
        _lowered("BPP", (_mask(8), _relative(40), _storage(16))),
        _lowered("BPRP", (_mask(8), _relative(40), _relative(48))),
    ]

    assert {name: _shape(ir)[-2:] for name, ir in lowered.items()} == {
        name: DISPATCH for name in lowered
    }
    assert [
        [i for i in ir if isinstance(i, (BranchIf, WriteRegion, Symbolic))]
        for ir in lowered.values()
    ] == [[], [], []]
    assert nothing == [()] * len(nothing)
