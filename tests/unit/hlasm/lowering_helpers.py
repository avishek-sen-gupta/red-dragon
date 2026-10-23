# pyright: standard
"""Operand and statement builders and the IR describer shared by the HLASM lowering unit tests."""

from collections.abc import Mapping, Sequence
from functools import singledispatch

from hlasm_asg.program.abs_address import AbsAddress
from hlasm_asg.program.imm_operand import ImmOperand
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.mask_operand import MaskOperand
from hlasm_asg.program.open_code_origin import OpenCodeOrigin
from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reg_operand import RegOperand
from hlasm_asg.program.storage_length_operand import StorageLengthOperand
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.instructions import (
    Binop,
    Branch,
    InstructionBase,
    LoadRegion,
    LoadVar,
    StoreVar,
    WriteRegion,
)
from interpreter.register import Register

BASE_REGISTER = 12


def machine_statement(mnemonic: str, operands: Sequence[Operand]) -> MachineStatement:
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


def reg_operand(value: int) -> RegOperand:
    return RegOperand(kind="REG", value=value)


def imm_operand(value: int) -> ImmOperand:
    return ImmOperand(kind="IMM", value=value)


def mask_operand(value: int) -> MaskOperand:
    return MaskOperand(kind="MASK", value=value)


def storage_operand(displacement: int) -> StorageOperand:
    return StorageOperand(
        kind="STORAGE",
        displacement=displacement,
        index=0,
        base=BASE_REGISTER,
        written=AbsAddress(kind="ABS", value=displacement),
    )


def storage_length_operand(displacement: int, length: int) -> StorageLengthOperand:
    return StorageLengthOperand(
        kind="STORAGE_LENGTH",
        displacement=displacement,
        length=length,
        base=BASE_REGISTER,
    )


@singledispatch
def describe(i: InstructionBase, consts: Mapping[Register, int | str]) -> str:
    return type(i).__name__


@describe.register
def _describe_load_var(i: LoadVar, consts: Mapping[Register, int | str]) -> str:
    return f"LoadVar {i.name}"


@describe.register
def _describe_store_var(i: StoreVar, consts: Mapping[Register, int | str]) -> str:
    return f"StoreVar {i.name} {consts.get(i.value_reg, 'reg')}"


@describe.register
def _describe_load_region(i: LoadRegion, consts: Mapping[Register, int | str]) -> str:
    return f"LoadRegion {consts[i.offset_reg]}+{i.length}"


@describe.register
def _describe_write_region(i: WriteRegion, consts: Mapping[Register, int | str]) -> str:
    return f"WriteRegion {consts[i.offset_reg]}+{i.length}"


@describe.register
def _describe_binop(i: Binop, consts: Mapping[Register, int | str]) -> str:
    return f"{i.operator.value} {consts.get(i.right, 'reg')}"


@describe.register
def _describe_branch(i: Branch, consts: Mapping[Register, int | str]) -> str:
    return f"Branch {i.label}"
