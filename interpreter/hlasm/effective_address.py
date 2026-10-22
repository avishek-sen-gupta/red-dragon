# pyright: standard
"""Operand addresses: the AMODE 31 effective address of D(X,B) and D(L,B), its element-scaled form, a relative-immediate target, and an address held in a register."""

from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
from hlasm_asg.program.storage_length_operand import StorageLengthOperand
from hlasm_asg.program.storage_operand import StorageOperand
from interpreter.hlasm.hlasm_constants import ADDRESS_MASK_31
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.storage_layout import section_var
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def _plus_register(emitter: HlasmEmitter, total: Register, r: int) -> Register:
    if r == 0:
        return total
    return emitter.binop(BinopKind.ADD, total, emitter.load_gr32(r))


def _scaled(emitter: HlasmEmitter, value: Register, shift: int) -> Register:
    if shift == 0:
        return value
    return emitter.binop(BinopKind.LSHIFT, value, emitter.int_(shift))


def _address(
    emitter: HlasmEmitter, displacement: int, index: int, base: int, shift: int
) -> Register:
    indexed = _plus_register(emitter, emitter.int_(displacement), index)
    based = _plus_register(emitter, _scaled(emitter, indexed, shift), base)
    return emitter.binop(BinopKind.BIT_AND, based, emitter.int_(ADDRESS_MASK_31))


def indexed_address(
    emitter: HlasmEmitter, operand: StorageOperand, shift: int
) -> Register:
    return _address(emitter, operand.displacement, operand.index, operand.base, shift)


def effective_address(emitter: HlasmEmitter, operand: StorageOperand) -> Register:
    return indexed_address(emitter, operand, 0)


def length_operand_address(
    emitter: HlasmEmitter, operand: StorageLengthOperand
) -> Register:
    return _address(emitter, operand.displacement, 0, operand.base, 0)


def relative_address(emitter: HlasmEmitter, operand: RelocImmOperand) -> Register:
    base = emitter.load_var(section_var(operand.section))
    return emitter.binop(BinopKind.ADD, base, emitter.int_(operand.offset))


def register_address(emitter: HlasmEmitter, r: int) -> Register:
    return emitter.binop(
        BinopKind.BIT_AND, emitter.load_gr32(r), emitter.int_(ADDRESS_MASK_31)
    )
