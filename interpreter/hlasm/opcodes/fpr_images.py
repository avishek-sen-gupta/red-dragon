# pyright: standard
"""Floating-point images in IR, whatever the radix: FPR access by width, operand sources, result-list items, an arithmetic select and an integer's sign and magnitude."""

from collections.abc import Callable, Mapping, Sequence
from functools import reduce

from interpreter.hlasm.data_movement import Source, from_storage_at, keep
from interpreter.hlasm.fpr_layout import FprLayout
from interpreter.hlasm.hlasm_constants import (
    BITS_PER_BYTE,
    DOUBLEWORD_BITS,
    LIST_GET,
    LIST_SET,
    MAKE_LIST,
    REGISTER_MASK,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.floating_point_support import PAIR_PARTNER
from interpreter.hlasm.operands import reg_operand
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

FIRST, SECOND, THIRD, FOURTH = 0, 1, 2, 3
SHORT_WIDTH = 32
LONG_WIDTH = 64
EXTENDED_WIDTH = 128


def _load_pair(emitter: HlasmEmitter, r: int) -> Register:
    high = emitter.binop(
        BinopKind.LSHIFT, emitter.load_fpr(r), emitter.int_(DOUBLEWORD_BITS)
    )
    return emitter.binop(BinopKind.BIT_OR, high, emitter.load_fpr(r + PAIR_PARTNER))


def _store_pair(emitter: HlasmEmitter, r: int, image: Register) -> None:
    high = emitter.binop(BinopKind.RSHIFT, image, emitter.int_(DOUBLEWORD_BITS))
    emitter.store_fpr(r, high)
    emitter.store_fpr(r + PAIR_PARTNER, keep(REGISTER_MASK)(emitter, image))


_LOADS: Mapping[int, Callable[[HlasmEmitter, int], Register]] = {
    SHORT_WIDTH: lambda emitter, r: emitter.load_fpr_high32(r),
    LONG_WIDTH: lambda emitter, r: emitter.load_fpr(r),
    EXTENDED_WIDTH: _load_pair,
}
_STORES: Mapping[int, Callable[[HlasmEmitter, int, Register], None]] = {
    SHORT_WIDTH: lambda emitter, r, image: emitter.store_fpr_high32(r, image),
    LONG_WIDTH: lambda emitter, r, image: emitter.store_fpr(r, image),
    EXTENDED_WIDTH: _store_pair,
}


def load_image(emitter: HlasmEmitter, r: int, layout: FprLayout) -> Register:
    return _LOADS[layout.width](emitter, r)


def store_image(
    emitter: HlasmEmitter, r: int, layout: FprLayout, image: Register
) -> None:
    _STORES[layout.width](emitter, r, image)


def fpr(index: int, layout: FprLayout) -> Source:
    return lambda emitter, statement: load_image(
        emitter, reg_operand(statement, index), layout
    )


def storage(index: int, layout: FprLayout) -> Source:
    return from_storage_at(index, layout.width // BITS_PER_BYTE)


def list_of(emitter: HlasmEmitter, items: Sequence[Register]) -> Register:
    empty = emitter.call(MAKE_LIST, (emitter.int_(len(items)), emitter.int_(0)))
    return reduce(
        lambda built, item: emitter.call(
            LIST_SET, (built, emitter.int_(item[0]), item[1])
        ),
        enumerate(items),
        empty,
    )


def list_item(emitter: HlasmEmitter, items: Register, slot: int) -> Register:
    return emitter.call(LIST_GET, (items, emitter.int_(slot)))


def signed_magnitude(
    emitter: HlasmEmitter, value: Register
) -> tuple[Register, Register]:
    negative = emitter.binop(BinopKind.LT, value, emitter.int_(0))
    doubled = emitter.binop(BinopKind.MUL, negative, emitter.int_(2))
    flipped = emitter.binop(BinopKind.MUL, doubled, value)
    return negative, emitter.binop(BinopKind.SUB, value, flipped)


def compared(
    emitter: HlasmEmitter, operator: BinopKind, value: Register, against: int
) -> Register:
    return emitter.binop(operator, value, emitter.int_(against))
