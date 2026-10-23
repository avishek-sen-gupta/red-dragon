# pyright: standard
"""Decimal digits one per lane in IR, four bits a lane for packed and eight for zoned (the digit in each lane's low four bits): an integer spread into lanes and lanes combined into an integer, as IR functions defined once per program, and a test for a lane digit above 9."""

from collections.abc import Sequence
from functools import reduce

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import Body, IrFunction
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

DIGIT_MASK = 0b1111
DECIMAL_BASE = 10
EIGHTS_SHIFT = 3


def lanes_of(value: int, lane_bits: int, count: int) -> int:
    return sum(value << (lane_bits * k) for k in range(count))


def _spread(lane_bits: int, count: int) -> Body:
    def body(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
        (value,) = parameters
        ten = emitter.int_(DECIMAL_BASE)

        def step(
            spread: tuple[Register, Register], at: int
        ) -> tuple[Register, Register]:
            rest, image = spread
            digit = emitter.binop(BinopKind.MOD, rest, ten)
            placed = emitter.binop(
                BinopKind.LSHIFT, digit, emitter.int_(lane_bits * at)
            )
            return (
                emitter.binop(BinopKind.FLOOR_DIV, rest, ten),
                emitter.binop(BinopKind.BIT_OR, image, placed),
            )

        return reduce(step, range(count), (value, emitter.int_(0)))[1]

    return body


def _steps(width: int, count: int, factor: int) -> tuple[tuple[int, int, int], ...]:
    if count <= 1:
        return ()
    pairs = (count + 1) // 2
    mask = lanes_of((1 << width) - 1, 2 * width, pairs)
    return ((width, mask, factor), *_steps(2 * width, pairs, factor * factor))


def _combine(lane_bits: int, count: int) -> Body:
    def body(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
        (image,) = parameters
        digits = emitter.binop(
            BinopKind.BIT_AND,
            image,
            emitter.int_(lanes_of(DIGIT_MASK, lane_bits, count)),
        )

        def step(lanes: Register, at: tuple[int, int, int]) -> Register:
            width, mask, factor = at
            moved = emitter.binop(BinopKind.RSHIFT, lanes, emitter.int_(width))
            high = emitter.binop(BinopKind.BIT_AND, moved, emitter.int_(mask))
            low = emitter.binop(BinopKind.BIT_AND, lanes, emitter.int_(mask))
            scaled = emitter.binop(BinopKind.MUL, high, emitter.int_(factor))
            return emitter.binop(BinopKind.ADD, scaled, low)

        return reduce(step, _steps(lane_bits, count, DECIMAL_BASE), digits)

    return body


def spread_digits(lane_bits: int, count: int) -> IrFunction:
    return IrFunction(
        f"__hlasm_decimal_lanes_{lane_bits}_{count}", 1, _spread(lane_bits, count)
    )


def combined_digits(lane_bits: int, count: int) -> IrFunction:
    return IrFunction(
        f"__hlasm_decimal_value_{lane_bits}_{count}", 1, _combine(lane_bits, count)
    )


def invalid_digits(
    emitter: HlasmEmitter, image: Register, lane_bits: int, count: int
) -> Register:
    ones = emitter.int_(lanes_of(1, lane_bits, count))

    def bit(shift: int) -> Register:
        moved = emitter.binop(BinopKind.RSHIFT, image, emitter.int_(shift))
        return emitter.binop(BinopKind.BIT_AND, moved, ones)

    eights = bit(EIGHTS_SHIFT)
    rest = emitter.binop(BinopKind.BIT_OR, bit(1), bit(2))
    bad = emitter.binop(BinopKind.BIT_AND, eights, rest)
    return emitter.binop(BinopKind.NE, bad, emitter.int_(0))
