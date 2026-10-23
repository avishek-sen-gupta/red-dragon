# pyright: standard
"""Densely packed decimal in IR (PoO 20-58 to 20-60): every declet of a trailing significand decoded or encoded at once, one ten-bit lane per declet, by the IEEE 754 DPD bit equations."""

from dataclasses import dataclass
from functools import reduce

from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

LANE_BITS = 10
LANE_MASK = (1 << LANE_BITS) - 1
LANE_VALUES = 1000
HUNDREDS = 100
TENS = 10
DIGIT_MASK = 0b1111
PAIR_MASK = 0b11
TRIPLE_MASK = 0b111
EVEN_PAIR_MASK = 0b110
BIG_DIGIT = 8
BIG_SHIFT = 3


@dataclass(frozen=True)
class _Lanes:
    emitter: HlasmEmitter
    count: int

    def ones(self, value: int) -> Register:
        spread = sum(value << (LANE_BITS * k) for k in range(self.count))
        return self.emitter.int_(spread)

    def op(self, operator: BinopKind, left: Register, right: Register) -> Register:
        return self.emitter.binop(operator, left, right)

    def all_(self, *values: Register) -> Register:
        return reduce(lambda a, b: self.op(BinopKind.BIT_AND, a, b), values)

    def any_(self, *values: Register) -> Register:
        return reduce(lambda a, b: self.op(BinopKind.BIT_OR, a, b), values)

    def field(self, word: Register, shift: int, mask: int) -> Register:
        moved = self.op(BinopKind.RSHIFT, word, self.emitter.int_(shift))
        return self.op(BinopKind.BIT_AND, moved, self.ones(mask))

    def not_(self, flags: Register) -> Register:
        return self.op(BinopKind.BIT_XOR, flags, self.ones(1))

    def placed(self, value: Register, shift: int) -> Register:
        return self.op(BinopKind.LSHIFT, value, self.emitter.int_(shift))

    def select(
        self, flags: Register, then: Register, otherwise: Register, mask: int
    ) -> Register:
        chosen = self.op(BinopKind.MUL, flags, self.emitter.int_(mask))
        rest = self.op(BinopKind.BIT_XOR, chosen, self.ones(mask))
        return self.any_(
            self.op(BinopKind.BIT_AND, then, chosen),
            self.op(BinopKind.BIT_AND, otherwise, rest),
        )

    def scaled(self, value: Register, factor: int) -> Register:
        return self.op(BinopKind.MUL, value, self.emitter.int_(factor))


type _Bits = tuple[Register, ...]


def _bits(lanes: _Lanes, word: Register) -> _Bits:
    y, x, w, v, u, t, s, r = (lanes.field(word, at, 1) for at in range(8))
    return (y, x, w, v, u, t, s, r, *(lanes.not_(bit) for bit in (x, w, s, t)))


def _first_digit(lanes: _Lanes, word: Register, bits: _Bits) -> Register:
    _y, _x, w, v, _u, t, _s, r, nx, _nw, ns, _nt = bits
    big = lanes.all_(v, w, lanes.any_(nx, ns, t))
    eight = lanes.any_(lanes.ones(BIG_DIGIT), r)
    return lanes.select(big, eight, lanes.field(word, 7, TRIPLE_MASK), DIGIT_MASK)


def _second_digit(lanes: _Lanes, word: Register, bits: _Bits) -> Register:
    _y, x, w, v, u, t, s, _r, _nx, nw, ns, nt = bits
    big = lanes.all_(v, x, lanes.any_(nw, s, nt))
    from_pq = lanes.all_(v, w, x, ns, t)
    pq = lanes.any_(lanes.field(word, 7, EVEN_PAIR_MASK), u)
    small = lanes.select(from_pq, pq, lanes.field(word, 4, TRIPLE_MASK), DIGIT_MASK)
    eight = lanes.any_(lanes.ones(BIG_DIGIT), u)
    return lanes.select(big, eight, small, DIGIT_MASK)


def _third_digit(lanes: _Lanes, word: Register, bits: _Bits) -> Register:
    y, x, w, v, _u, t, s, _r, nx, nw, ns, nt = bits
    big = lanes.all_(
        v, lanes.any_(lanes.all_(nw, nx), lanes.all_(w, x, lanes.any_(s, t)))
    )
    from_st = lanes.all_(v, nw, x)
    from_pq = lanes.all_(v, w, lanes.any_(nx, lanes.all_(ns, nt)))
    pq = lanes.any_(lanes.field(word, 7, EVEN_PAIR_MASK), y)
    st = lanes.any_(lanes.field(word, 4, EVEN_PAIR_MASK), y)
    plain = lanes.select(from_pq, pq, lanes.field(word, 0, TRIPLE_MASK), DIGIT_MASK)
    small = lanes.select(from_st, st, plain, DIGIT_MASK)
    eight = lanes.any_(lanes.ones(BIG_DIGIT), y)
    return lanes.select(big, eight, small, DIGIT_MASK)


def _decoded_digits(lanes: _Lanes, word: Register) -> Register:
    bits = _bits(lanes, word)
    hundreds = lanes.scaled(_first_digit(lanes, word, bits), HUNDREDS)
    tens = lanes.scaled(_second_digit(lanes, word, bits), TENS)
    sum_ = lanes.op(BinopKind.ADD, hundreds, tens)
    return lanes.op(BinopKind.ADD, sum_, _third_digit(lanes, word, bits))


def declets_to_integer(
    emitter: HlasmEmitter, trailing: Register, count: int
) -> Register:
    lanes = _Lanes(emitter, count)
    values = _decoded_digits(lanes, trailing)

    def lane(k: int) -> Register:
        moved = emitter.binop(BinopKind.RSHIFT, values, emitter.int_(LANE_BITS * k))
        return emitter.binop(BinopKind.BIT_AND, moved, emitter.int_(LANE_MASK))

    return reduce(
        lambda total, k: emitter.binop(
            BinopKind.ADD, lanes.scaled(total, LANE_VALUES), lane(k)
        ),
        range(count - 2, -1, -1),
        lane(count - 1),
    )


type _Digits = tuple[Register, Register, Register, Register]


def _split_lane(lanes: _Lanes, digits: _Digits, k: int) -> _Digits:
    emitter = lanes.emitter
    rest, firsts, seconds, thirds = digits
    value = emitter.binop(BinopKind.MOD, rest, emitter.int_(LANE_VALUES))
    after = emitter.binop(BinopKind.FLOOR_DIV, rest, emitter.int_(LANE_VALUES))
    tens = emitter.binop(BinopKind.FLOOR_DIV, value, emitter.int_(TENS))
    split = (
        emitter.binop(BinopKind.FLOOR_DIV, value, emitter.int_(HUNDREDS)),
        emitter.binop(BinopKind.MOD, tens, emitter.int_(TENS)),
        emitter.binop(BinopKind.MOD, value, emitter.int_(TENS)),
    )
    placed = tuple(lanes.placed(digit, LANE_BITS * k) for digit in split)
    return (
        after,
        lanes.any_(firsts, placed[0]),
        lanes.any_(seconds, placed[1]),
        lanes.any_(thirds, placed[2]),
    )


def _encoded(
    lanes: _Lanes, first: Register, second: Register, third: Register
) -> Register:
    big_a, big_b, big_c = (lanes.field(d, BIG_SHIFT, 1) for d in (first, second, third))
    low_a, low_b, low_c = (lanes.field(d, 0, 1) for d in (first, second, third))
    mid_a, mid_b, mid_c = (lanes.field(d, 1, PAIR_MASK) for d in (first, second, third))
    not_a, not_b, not_c = (lanes.not_(big) for big in (big_a, big_b, big_c))
    any_big = lanes.any_(big_a, big_b, big_c)
    a_and_c = lanes.all_(big_a, big_c)
    pq = lanes.select(
        not_a,
        mid_a,
        lanes.select(
            not_c,
            mid_c,
            lanes.select(not_b, mid_b, lanes.ones(0), PAIR_MASK),
            PAIR_MASK,
        ),
        PAIR_MASK,
    )
    st = lanes.select(
        big_b,
        lanes.select(
            lanes.all_(not_a, not_c),
            mid_c,
            lanes.any_(lanes.placed(big_c, 1), a_and_c),
            PAIR_MASK,
        ),
        lanes.select(a_and_c, lanes.ones(1), mid_b, PAIR_MASK),
        PAIR_MASK,
    )
    several = lanes.any_(lanes.all_(big_a, big_b), a_and_c, lanes.all_(big_b, big_c))
    wx = lanes.select(
        lanes.not_(any_big),
        mid_c,
        lanes.select(
            several,
            lanes.ones(PAIR_MASK),
            lanes.any_(big_b, lanes.placed(big_a, 1)),
            PAIR_MASK,
        ),
        PAIR_MASK,
    )
    return lanes.any_(
        lanes.placed(pq, 8),
        lanes.placed(low_a, 7),
        lanes.placed(st, 5),
        lanes.placed(low_b, 4),
        lanes.placed(any_big, 3),
        lanes.placed(wx, 1),
        low_c,
    )


def integer_to_declets(emitter: HlasmEmitter, value: Register, count: int) -> Register:
    lanes = _Lanes(emitter, count)
    zero = emitter.int_(0)
    _, first, second, third = reduce(
        lambda digits, k: _split_lane(lanes, digits, k),
        range(count),
        (value, zero, zero, zero),
    )
    return _encoded(lanes, first, second, third)
