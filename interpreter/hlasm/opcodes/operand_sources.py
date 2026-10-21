# pyright: standard
"""Named second-operand sources shared by the arithmetic and compare opcode units."""

from interpreter.hlasm.data_movement import (
    from_gr32,
    from_storage,
    immediate,
    sign_extended,
    signed_immediate,
)
from interpreter.hlasm.hlasm_constants import (
    DOUBLEWORD_BYTES,
    HALFWORD_BITS,
    HALFWORD_BYTES,
    WORD_BITS,
    WORD_BYTES,
)

WORD_STORAGE = from_storage(WORD_BYTES)
DOUBLEWORD_STORAGE = from_storage(DOUBLEWORD_BYTES)
SIGNED_HALFWORD_STORAGE = sign_extended(from_storage(HALFWORD_BYTES), HALFWORD_BITS)
SIGNED_WORD_STORAGE = sign_extended(from_storage(WORD_BYTES), WORD_BITS)
SIGNED_LOW_WORD = sign_extended(from_gr32(1), WORD_BITS)
HALFWORD_IMMEDIATE = signed_immediate(1, HALFWORD_BITS)
WORD_IMMEDIATE = signed_immediate(1, WORD_BITS)
THIRD_HALFWORD_IMMEDIATE = signed_immediate(2, HALFWORD_BITS)
LOGICAL_WORD_IMMEDIATE = immediate(WORD_BITS)
