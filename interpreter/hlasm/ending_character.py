# pyright: standard
"""The character GR0 names for the string instructions: its rightmost one or two bytes, with the rest of bits 32-63 zero or the run abends S0C6."""

from interpreter.hlasm.hlasm_constants import BITS_PER_BYTE, LOW_WORD_MASK, ONE_BYTE
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.specification_check import emit_specification_check
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

ENDING_CHARACTER_REGISTER = 0


def ending_unit(emitter: HlasmEmitter, width: int) -> Register:
    character_bits = (1 << (BITS_PER_BYTE * width)) - 1
    gr0 = emitter.load_gr32(ENDING_CHARACTER_REGISTER)
    reserved = emitter.binop(
        BinopKind.BIT_AND, gr0, emitter.int_(LOW_WORD_MASK & ~character_bits)
    )
    emit_specification_check(
        emitter, emitter.binop(BinopKind.NE, reserved, emitter.int_(0))
    )
    return emitter.binop(BinopKind.BIT_AND, gr0, emitter.int_(character_bits))


def ending_character(emitter: HlasmEmitter) -> Register:
    return ending_unit(emitter, ONE_BYTE)
