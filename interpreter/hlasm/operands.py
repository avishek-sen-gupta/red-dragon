# pyright: standard
"""Typed operand access for machine statements; a mismatched operand raises HlasmLoweringError."""

from collections.abc import Sequence

from hlasm_asg.program.imm_operand import ImmOperand
from hlasm_asg.program.machine_statement import MachineStatement
from hlasm_asg.program.mask_operand import MaskOperand
from hlasm_asg.program.operand import Operand
from hlasm_asg.program.reg_operand import RegOperand
from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
from hlasm_asg.program.storage_length_operand import StorageLengthOperand
from hlasm_asg.program.storage_operand import StorageOperand
from hlasm_asg.program.vec_reg_operand import VecRegOperand
from interpreter.hlasm.hlasm_lowering_error import HlasmLoweringError


def _mismatch(statement: MachineStatement, index: int, expected: str) -> Exception:
    where = (
        f"{statement.base_mnemonic} in {statement.section} at offset {statement.offset}"
        f" ({statement.origin.file}:{statement.origin.line}) operand {index}"
    )
    found = (
        repr(statement.operands[index])
        if index < len(statement.operands)
        else "no operand"
    )
    return HlasmLoweringError(where, expected, found)


def _at(statement: MachineStatement, index: int) -> Sequence[Operand]:
    return statement.operands[index : index + 1]


def reg_operand(statement: MachineStatement, index: int) -> int:
    match _at(statement, index):
        case [RegOperand(value=value)]:
            return value
        case _:
            raise _mismatch(statement, index, "a register")


def mask_operand(statement: MachineStatement, index: int) -> int:
    match _at(statement, index):
        case [MaskOperand(value=value)]:
            return value
        case _:
            raise _mismatch(statement, index, "a mask")


def optional_mask_operand(statement: MachineStatement, index: int, absent: int) -> int:
    match _at(statement, index):
        case [MaskOperand(value=value)]:
            return value
        case []:
            return absent
        case _:
            raise _mismatch(statement, index, "a mask or no operand")


def imm_operand(statement: MachineStatement, index: int) -> int:
    match _at(statement, index):
        case [ImmOperand(value=value)]:
            return value
        case _:
            raise _mismatch(statement, index, "an immediate")


def optional_imm_operand(statement: MachineStatement, index: int, absent: int) -> int:
    match _at(statement, index):
        case [ImmOperand(value=value)]:
            return value
        case []:
            return absent
        case _:
            raise _mismatch(statement, index, "an immediate or no operand")


def storage_operand(statement: MachineStatement, index: int) -> StorageOperand:
    match _at(statement, index):
        case [StorageOperand() as operand]:
            return operand
        case _:
            raise _mismatch(statement, index, "a storage operand")


def reloc_operand(statement: MachineStatement, index: int) -> RelocImmOperand:
    match _at(statement, index):
        case [RelocImmOperand() as operand]:
            return operand
        case _:
            raise _mismatch(statement, index, "a relocatable immediate")


def storage_length_operand(
    statement: MachineStatement, index: int
) -> StorageLengthOperand:
    match _at(statement, index):
        case [StorageLengthOperand() as operand]:
            return operand
        case _:
            raise _mismatch(statement, index, "a storage length operand")


def vec_reg_operand(statement: MachineStatement, index: int) -> int:
    match _at(statement, index):
        case [VecRegOperand(value=value)]:
            return value
        case _:
            raise _mismatch(statement, index, "a vector register")
