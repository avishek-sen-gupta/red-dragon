# pyright: standard
"""One field of an element function's single return value: the 128-bit result in bits 0-127, the CC at 128-129, FPC flags at 136-143, the VXC at 144-151 and a trap bit at 152."""

from dataclasses import dataclass

from interpreter.hlasm.bit_fields import placed_bits
from interpreter.hlasm.hlasm_constants import BITS_PER_BYTE, VECTOR_REGISTER_BYTES
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


@dataclass(frozen=True)
class ElementReturnField:
    shift: int
    mask: int

    def of(self, emitter: HlasmEmitter, returned: Register) -> Register:
        moved = emitter.binop(BinopKind.RSHIFT, returned, emitter.int_(self.shift))
        return emitter.binop(BinopKind.BIT_AND, moved, emitter.int_(self.mask))

    def placed(self, emitter: HlasmEmitter, value: Register) -> Register:
        return placed_bits(emitter, value, self.mask, self.shift)


RESULT_BITS = BITS_PER_BYTE * VECTOR_REGISTER_BYTES
RESULT_FIELD = ElementReturnField(0, (1 << RESULT_BITS) - 1)
CC_FIELD = ElementReturnField(RESULT_BITS, 0b11)
FLAGS_FIELD = ElementReturnField(RESULT_BITS + BITS_PER_BYTE, 0xFF)
VXC_FIELD = ElementReturnField(RESULT_BITS + 2 * BITS_PER_BYTE, 0xFF)
TRAP_FIELD = ElementReturnField(RESULT_BITS + 3 * BITS_PER_BYTE, 1)
