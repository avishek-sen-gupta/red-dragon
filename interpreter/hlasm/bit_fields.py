# pyright: standard
"""IR for an int's bit fields: one masked and moved left, several ORed into one."""

from collections.abc import Sequence
from functools import reduce

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.operator_kind import BinopKind
from interpreter.register import Register


def placed_bits(
    emitter: HlasmEmitter, value: Register, mask: int, shift: int
) -> Register:
    masked = emitter.binop(BinopKind.BIT_AND, value, emitter.int_(mask))
    return emitter.binop(BinopKind.LSHIFT, masked, emitter.int_(shift))


def combined_bits(emitter: HlasmEmitter, parts: Sequence[Register]) -> Register:
    return reduce(
        lambda left, right: emitter.binop(BinopKind.BIT_OR, left, right), parts
    )
