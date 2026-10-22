# pyright: standard
"""The low word, the high word and the whole of a general register, and an access register, as register parts."""

from interpreter.hlasm.hlasm_constants import DOUBLEWORD_BITS, WORD_BITS
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.register_part import RegisterPart

LOW_WORD_PART = RegisterPart(HlasmEmitter.load_gr32, HlasmEmitter.store_gr32, WORD_BITS)
HIGH_WORD_PART = RegisterPart(
    HlasmEmitter.load_gr_high32, HlasmEmitter.store_gr_high32, WORD_BITS
)
WHOLE_REGISTER_PART = RegisterPart(
    HlasmEmitter.load_gr64, HlasmEmitter.store_gr64, DOUBLEWORD_BITS
)
ACCESS_REGISTER_PART = RegisterPart(
    HlasmEmitter.load_ar, HlasmEmitter.store_ar, WORD_BITS
)
