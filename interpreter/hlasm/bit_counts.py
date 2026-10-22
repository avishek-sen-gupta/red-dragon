# pyright: standard
"""Branch-free 64-bit bit counts in IR: population per byte and in total, the right smear, leading and trailing zeros, the leftmost one bit."""

from functools import reduce

from interpreter.hlasm.hlasm_constants import DOUBLEWORD_BITS, REGISTER_MASK
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

PAIR_BITS = 0x55555555_55555555
NIBBLE_PAIRS = 0x33333333_33333333
BYTE_NIBBLES = 0x0F0F0F0F_0F0F0F0F
EVERY_BYTE = 0x01010101_01010101
TOP_BYTE_SHIFT = 56
SMEAR_SHIFTS = (1, 2, 4, 8, 16, 32)
LOWEST_BIT = 1


def _shifted_and(
    emitter: HlasmEmitter, value: Register, shift: int, mask: int
) -> Register:
    moved = emitter.binop(BinopKind.RSHIFT, value, emitter.int_(shift))
    return emitter.binop(BinopKind.BIT_AND, moved, emitter.int_(mask))


def population_by_byte(emitter: HlasmEmitter, value: Register) -> Register:
    pairs = emitter.binop(
        BinopKind.SUB, value, _shifted_and(emitter, value, 1, PAIR_BITS)
    )
    nibbles = emitter.binop(
        BinopKind.ADD,
        emitter.binop(BinopKind.BIT_AND, pairs, emitter.int_(NIBBLE_PAIRS)),
        _shifted_and(emitter, pairs, 2, NIBBLE_PAIRS),
    )
    summed = emitter.binop(
        BinopKind.ADD,
        nibbles,
        emitter.binop(BinopKind.RSHIFT, nibbles, emitter.int_(4)),
    )
    return emitter.binop(BinopKind.BIT_AND, summed, emitter.int_(BYTE_NIBBLES))


def population(emitter: HlasmEmitter, value: Register) -> Register:
    spread = emitter.binop(
        BinopKind.MUL, population_by_byte(emitter, value), emitter.int_(EVERY_BYTE)
    )
    kept = emitter.binop(BinopKind.BIT_AND, spread, emitter.int_(REGISTER_MASK))
    return emitter.binop(BinopKind.RSHIFT, kept, emitter.int_(TOP_BYTE_SHIFT))


def smeared_right(emitter: HlasmEmitter, value: Register) -> Register:
    return reduce(
        lambda current, shift: emitter.binop(
            BinopKind.BIT_OR,
            current,
            emitter.binop(BinopKind.RSHIFT, current, emitter.int_(shift)),
        ),
        SMEAR_SHIFTS,
        value,
    )


def leading_zeros_of_smear(emitter: HlasmEmitter, smeared: Register) -> Register:
    return emitter.binop(
        BinopKind.SUB, emitter.int_(DOUBLEWORD_BITS), population(emitter, smeared)
    )


def leading_zeros(emitter: HlasmEmitter, value: Register) -> Register:
    return leading_zeros_of_smear(emitter, smeared_right(emitter, value))


def lowest_one(emitter: HlasmEmitter, value: Register) -> Register:
    negated = emitter.binop(BinopKind.MUL, value, emitter.int_(-1))
    return emitter.binop(BinopKind.BIT_AND, value, negated)


def trailing_zeros(emitter: HlasmEmitter, value: Register) -> Register:
    below = emitter.binop(
        BinopKind.SUB, lowest_one(emitter, value), emitter.int_(LOWEST_BIT)
    )
    return population(
        emitter, emitter.binop(BinopKind.BIT_AND, below, emitter.int_(REGISTER_MASK))
    )


def leftmost_one(emitter: HlasmEmitter, smeared: Register) -> Register:
    return emitter.binop(
        BinopKind.BIT_XOR,
        smeared,
        emitter.binop(BinopKind.RSHIFT, smeared, emitter.int_(1)),
    )


def any_one(emitter: HlasmEmitter, smeared: Register) -> Register:
    return emitter.binop(BinopKind.BIT_AND, smeared, emitter.int_(LOWEST_BIT))
