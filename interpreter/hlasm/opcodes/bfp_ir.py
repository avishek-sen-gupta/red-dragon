# pyright: standard
"""IR for BFP images: field lists for the builtins, images from result fields, FPR access by layout, an image's condition code, and the IEEE trap ladder (ruling R43)."""

from collections.abc import Callable, Mapping
from dataclasses import replace
from functools import reduce

from interpreter.hlasm.bfp_layout import (
    EXTENDED_LAYOUT,
    LONG_LAYOUT,
    SHORT_LAYOUT,
    BfpLayout,
)
from interpreter.hlasm.bfp_slots import (
    FIELD_COUNT,
    FLAGS_SLOT,
    INEXACT_DXC_SLOT,
    SCALED_DXC_SLOT,
    SCALED_SLOT,
    SCALING_BITS,
    SUPPRESSING_BITS,
    TRAP_SLOT,
    VALUE_SLOT,
)
from interpreter.hlasm.conditional import emit_when
from interpreter.hlasm.data_movement import keep
from interpreter.hlasm.hlasm_constants import (
    BYTE_MASK,
    DOUBLEWORD_BITS,
    FPC_VAR,
    LIST_GET,
    LIST_SET,
    MAKE_LIST,
    REGISTER_MASK,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ieee_outcome import IeeeOutcome
from interpreter.hlasm.opcodes.floating_point_support import (
    FLAG_SHIFT,
    IEEE_BITS,
    MASK_SHIFT,
    MODE_FIELD,
    PAIR_PARTNER,
    emit_data_exception,
)
from interpreter.instructions import StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Deliver = Callable[[int], None]

FPC_TO_MODIFIER = 4
NAN_CC = 3
POSITIVE_CC = 2


def _load_pair(emitter: HlasmEmitter, r: int) -> Register:
    high = emitter.binop(
        BinopKind.LSHIFT, emitter.load_fpr(r), emitter.int_(DOUBLEWORD_BITS)
    )
    return emitter.binop(BinopKind.BIT_OR, high, emitter.load_fpr(r + PAIR_PARTNER))


def _store_pair(emitter: HlasmEmitter, r: int, image: Register) -> None:
    high = emitter.binop(BinopKind.RSHIFT, image, emitter.int_(DOUBLEWORD_BITS))
    emitter.store_fpr(r, high)
    emitter.store_fpr(r + PAIR_PARTNER, keep(REGISTER_MASK)(emitter, image))


_LOADS: Mapping[BfpLayout, Callable[[HlasmEmitter, int], Register]] = {
    SHORT_LAYOUT: lambda emitter, r: emitter.load_fpr_high32(r),
    LONG_LAYOUT: lambda emitter, r: emitter.load_fpr(r),
    EXTENDED_LAYOUT: _load_pair,
}
_STORES: Mapping[BfpLayout, Callable[[HlasmEmitter, int, Register], None]] = {
    SHORT_LAYOUT: lambda emitter, r, image: emitter.store_fpr_high32(r, image),
    LONG_LAYOUT: lambda emitter, r, image: emitter.store_fpr(r, image),
    EXTENDED_LAYOUT: _store_pair,
}


def load_image(emitter: HlasmEmitter, r: int, layout: BfpLayout) -> Register:
    return _LOADS[layout](emitter, r)


def store_image(
    emitter: HlasmEmitter, r: int, layout: BfpLayout, image: Register
) -> None:
    _STORES[layout](emitter, r, image)


def fields_list(emitter: HlasmEmitter, image: Register, layout: BfpLayout) -> Register:
    sign = emitter.binop(BinopKind.RSHIFT, image, emitter.int_(layout.sign_shift))
    biased = keep(layout.exponent_mask)(
        emitter,
        emitter.binop(BinopKind.RSHIFT, image, emitter.int_(layout.fraction_bits)),
    )
    fraction = keep((1 << layout.fraction_bits) - 1)(emitter, image)
    empty = emitter.call(MAKE_LIST, (emitter.int_(FIELD_COUNT), emitter.int_(0)))
    return reduce(
        lambda items, field: emitter.call(
            LIST_SET, (items, emitter.int_(field[0]), field[1])
        ),
        enumerate((sign, biased, fraction)),
        empty,
    )


def list_item(emitter: HlasmEmitter, items: Register, slot: int) -> Register:
    return emitter.call(LIST_GET, (items, emitter.int_(slot)))


def image_at(
    emitter: HlasmEmitter, result: Register, slot: int, layout: BfpLayout
) -> Register:
    sign, biased, fraction = (list_item(emitter, result, slot + at) for at in range(3))
    placed = emitter.binop(
        BinopKind.BIT_OR,
        emitter.binop(BinopKind.LSHIFT, sign, emitter.int_(layout.sign_shift)),
        emitter.binop(BinopKind.LSHIFT, biased, emitter.int_(layout.fraction_bits)),
    )
    return emitter.binop(BinopKind.BIT_OR, placed, fraction)


def image_cc(emitter: HlasmEmitter, image: Register, layout: BfpLayout) -> Register:
    magnitude = keep(layout.magnitude_mask)(emitter, image)
    sign = emitter.binop(BinopKind.RSHIFT, image, emitter.int_(layout.sign_shift))
    nan = emitter.binop(BinopKind.GT, magnitude, emitter.int_(layout.infinity))
    nonzero = emitter.binop(BinopKind.NE, magnitude, emitter.int_(0))
    signed = emitter.binop(BinopKind.SUB, emitter.int_(POSITIVE_CC), sign)
    number = emitter.binop(BinopKind.MUL, nonzero, signed)
    to_nan = emitter.binop(BinopKind.SUB, emitter.int_(NAN_CC), number)
    return emitter.binop(
        BinopKind.ADD, number, emitter.binop(BinopKind.MUL, nan, to_nan)
    )


def current_mode(emitter: HlasmEmitter) -> Register:
    mode = keep(MODE_FIELD)(emitter, emitter.load_var(FPC_VAR))
    shifted = emitter.binop(BinopKind.ADD, mode, emitter.int_(FPC_TO_MODIFIER))
    return keep(MODE_FIELD)(emitter, shifted)


def outcome_of(emitter: HlasmEmitter, result: Register) -> IeeeOutcome:
    return IeeeOutcome(
        list_item(emitter, result, TRAP_SLOT),
        list_item(emitter, result, FLAGS_SLOT),
        list_item(emitter, result, SCALED_DXC_SLOT),
        list_item(emitter, result, INEXACT_DXC_SLOT),
    )


def without(emitter: HlasmEmitter, outcome: IeeeOutcome, bits: int) -> IeeeOutcome:
    kept = BYTE_MASK ^ bits
    return replace(
        outcome,
        trap=keep(kept)(emitter, outcome.trap),
        flags=keep(kept)(emitter, outcome.flags),
    )


def _any(emitter: HlasmEmitter, value: Register) -> Register:
    return emitter.binop(BinopKind.NE, value, emitter.int_(0))


def _enabled(emitter: HlasmEmitter, fpc: Register, trap: Register) -> Register:
    shifted = emitter.binop(BinopKind.RSHIFT, fpc, emitter.int_(MASK_SHIFT))
    return emitter.binop(BinopKind.BIT_AND, trap, keep(IEEE_BITS)(emitter, shifted))


def _flagged(
    emitter: HlasmEmitter, fpc: Register, flags: Register, enabled: Register
) -> Register:
    inverted = emitter.binop(BinopKind.BIT_XOR, enabled, emitter.int_(BYTE_MASK))
    raised = emitter.binop(BinopKind.BIT_AND, flags, inverted)
    moved = emitter.binop(BinopKind.LSHIFT, raised, emitter.int_(FLAG_SHIFT))
    return emitter.binop(BinopKind.BIT_OR, fpc, moved)


def _when_any(emitter: HlasmEmitter, bits: Register, then: Callable[[], None]) -> None:
    emit_when(emitter, emitter.binop(BinopKind.NE, bits, emitter.int_(0)), then)


def _delivered_scaled(
    emitter: HlasmEmitter, fpc: Register, outcome: IeeeOutcome, deliver: Deliver
) -> Callable[[], None]:
    def scaled() -> None:
        deliver(SCALED_SLOT)
        emit_data_exception(emitter, fpc, outcome.scaled_dxc)

    return scaled


def emit_ieee_ladder(
    emitter: HlasmEmitter, outcome: IeeeOutcome, deliver: Deliver
) -> None:
    fpc = emitter.load_var(FPC_VAR)
    enabled = _enabled(emitter, fpc, outcome.trap)
    suppressing = keep(SUPPRESSING_BITS)(emitter, enabled)
    _when_any(
        emitter, suppressing, lambda: emit_data_exception(emitter, fpc, suppressing)
    )
    _when_any(
        emitter,
        keep(SCALING_BITS)(emitter, enabled),
        _delivered_scaled(emitter, fpc, outcome, deliver),
    )
    deliver(VALUE_SLOT)
    flagged = _flagged(emitter, fpc, outcome.flags, enabled)
    emitter.emit_inst(StoreVar(name=FPC_VAR, value_reg=flagged))
    _when_any(
        emitter,
        enabled,
        lambda: emit_data_exception(emitter, flagged, outcome.inexact_dxc),
    )
