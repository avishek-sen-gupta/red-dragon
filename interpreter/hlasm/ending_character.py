# pyright: standard
"""The ending character of MOVE STRING and COMPARE LOGICAL STRING: GR0 bits 56-63, with bits 32-55 zero or the run abends S0C6."""

from interpreter.hlasm.hlasm_constants import BYTE_MASK
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.specification_check import emit_specification_check
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

ENDING_CHARACTER_REGISTER = 0
RESERVED_BITS = 0xFFFFFF00


def ending_character(emitter: HlasmEmitter) -> Register:
    gr0 = emitter.load_gr32(ENDING_CHARACTER_REGISTER)
    reserved = emitter.binop(BinopKind.BIT_AND, gr0, emitter.int_(RESERVED_BITS))
    emit_specification_check(
        emitter, emitter.binop(BinopKind.NE, reserved, emitter.int_(0))
    )
    return emitter.binop(BinopKind.BIT_AND, gr0, emitter.int_(BYTE_MASK))
