# pyright: standard
"""Operand addresses: the AMODE 31 effective address of D(X,B), and a relative-immediate target."""

from hlasm_asg.program.reloc_imm_operand import RelocImmOperand
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


def effective_address(emitter: HlasmEmitter, operand: StorageOperand) -> Register:
    displaced = emitter.int_(operand.displacement)
    indexed = _plus_register(emitter, displaced, operand.index)
    based = _plus_register(emitter, indexed, operand.base)
    return emitter.binop(BinopKind.BIT_AND, based, emitter.int_(ADDRESS_MASK_31))


def relative_address(emitter: HlasmEmitter, operand: RelocImmOperand) -> Register:
    base = emitter.load_var(section_var(operand.section))
    return emitter.binop(BinopKind.ADD, base, emitter.int_(operand.offset))
