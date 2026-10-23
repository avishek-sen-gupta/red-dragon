# pyright: standard
"""IR for BFP images: field lists for the builtins, images from result fields or from an exact magnitude, an image's condition code, and the IEEE trap ladder (ruling R43), with a step a radix may apply to the outcome first."""

from collections.abc import Callable
from dataclasses import replace

from interpreter.hlasm.bfp_layout import (
    BfpLayout,
)
from interpreter.hlasm.bfp_slots import (
    FLAGS_SLOT,
    INEXACT_DXC_SLOT,
    SCALED_DXC_SLOT,
    SCALED_SLOT,
    SCALING_BITS,
    SUPPRESSING_BITS,
    TRAP_SLOT,
)
from interpreter.hlasm.bit_counts import leading_zeros
from interpreter.hlasm.conditional import emit_when
from interpreter.hlasm.data_movement import keep
from interpreter.hlasm.hlasm_constants import (
    BYTE_MASK,
    DOUBLEWORD_BITS,
    FPC_VAR,
    LIST_GET,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ieee_outcome import IeeeOutcome
from interpreter.hlasm.opcodes.floating_point_support import (
    FLAG_SHIFT,
    IEEE_BITS,
    MASK_SHIFT,
    MODE_FIELD,
    emit_data_exception,
)
from interpreter.hlasm.opcodes.fpr_images import list_item, list_of, pick
from interpreter.instructions import StoreVar
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type Deliver = Callable[[Register], None]
type OutcomeStep = Callable[[HlasmEmitter, Register, IeeeOutcome], IeeeOutcome]

FPC_TO_MODIFIER = 4
NAN_CC = 3
POSITIVE_CC = 2


def fields_list(emitter: HlasmEmitter, image: Register, layout: BfpLayout) -> Register:
    sign = emitter.binop(BinopKind.RSHIFT, image, emitter.int_(layout.sign_shift))
    biased = keep(layout.exponent_mask)(
        emitter,
        emitter.binop(BinopKind.RSHIFT, image, emitter.int_(layout.fraction_bits)),
    )
    fraction = keep((1 << layout.fraction_bits) - 1)(emitter, image)
    return list_of(emitter, (sign, biased, fraction))


def field_at(
    emitter: HlasmEmitter, result: Register, slot: Register, at: int
) -> Register:
    index = emitter.binop(BinopKind.ADD, slot, emitter.int_(at))
    return emitter.call(LIST_GET, (result, index))


def image_at(
    emitter: HlasmEmitter, result: Register, slot: Register, layout: BfpLayout
) -> Register:
    sign, biased, fraction = (field_at(emitter, result, slot, at) for at in range(3))
    placed = emitter.binop(
        BinopKind.BIT_OR,
        emitter.binop(BinopKind.LSHIFT, sign, emitter.int_(layout.sign_shift)),
        emitter.binop(BinopKind.LSHIFT, biased, emitter.int_(layout.fraction_bits)),
    )
    return emitter.binop(BinopKind.BIT_OR, placed, fraction)


def _normal_magnitude(
    emitter: HlasmEmitter, magnitude: Register, exponent: Register, layout: BfpLayout
) -> Register:
    zeros = leading_zeros(emitter, magnitude)
    top = emitter.binop(BinopKind.SUB, emitter.int_(DOUBLEWORD_BITS - 1), zeros)
    scale = emitter.binop(BinopKind.ADD, exponent, emitter.int_(layout.format.emax))
    biased = emitter.binop(BinopKind.ADD, scale, top)
    left = emitter.binop(BinopKind.SUB, emitter.int_(layout.fraction_bits), top)
    justified = emitter.binop(BinopKind.LSHIFT, magnitude, left)
    fraction = keep((1 << layout.fraction_bits) - 1)(emitter, justified)
    placed = emitter.binop(BinopKind.LSHIFT, biased, emitter.int_(layout.fraction_bits))
    return emitter.binop(BinopKind.BIT_OR, placed, fraction)


def exact_image(
    emitter: HlasmEmitter,
    negative: Register,
    magnitude: Register,
    exponent: Register,
    layout: BfpLayout,
) -> Register:
    finite = _normal_magnitude(emitter, magnitude, exponent, layout)
    nonzero = emitter.binop(BinopKind.NE, magnitude, emitter.int_(0))
    sign = emitter.binop(BinopKind.LSHIFT, negative, emitter.int_(layout.sign_shift))
    return emitter.binop(
        BinopKind.BIT_OR, sign, emitter.binop(BinopKind.MUL, nonzero, finite)
    )


def significand_of(
    emitter: HlasmEmitter, image: Register, biased: Register, source: BfpLayout
) -> tuple[Register, Register]:
    normal = emitter.binop(BinopKind.NE, biased, emitter.int_(0))
    implied = emitter.binop(
        BinopKind.LSHIFT, normal, emitter.int_(source.fraction_bits)
    )
    fraction = keep((1 << source.fraction_bits) - 1)(emitter, image)
    magnitude = emitter.binop(BinopKind.BIT_OR, fraction, implied)
    floor = emitter.binop(BinopKind.SUB, emitter.int_(1), normal)
    unbiased = emitter.binop(BinopKind.ADD, biased, floor)
    exponent = emitter.binop(
        BinopKind.SUB,
        unbiased,
        emitter.int_(source.format.emax + source.fraction_bits),
    )
    return magnitude, exponent


def image_cc(emitter: HlasmEmitter, image: Register, layout: BfpLayout) -> Register:
    magnitude = keep(layout.magnitude_mask)(emitter, image)
    sign = emitter.binop(BinopKind.RSHIFT, image, emitter.int_(layout.sign_shift))
    nan = emitter.binop(BinopKind.GT, magnitude, emitter.int_(layout.infinity))
    nonzero = emitter.binop(BinopKind.NE, magnitude, emitter.int_(0))
    signed = emitter.binop(BinopKind.SUB, emitter.int_(POSITIVE_CC), sign)
    number = emitter.binop(BinopKind.MUL, nonzero, signed)
    return pick(emitter, nan, emitter.int_(NAN_CC), number)


def magnitude_of(emitter: HlasmEmitter, image: Register, layout: BfpLayout) -> Register:
    return keep(layout.magnitude_mask)(emitter, image)


def nan_of(emitter: HlasmEmitter, image: Register, layout: BfpLayout) -> Register:
    magnitude = magnitude_of(emitter, image, layout)
    return emitter.binop(BinopKind.GT, magnitude, emitter.int_(layout.infinity))


def quiet_of(emitter: HlasmEmitter, image: Register, layout: BfpLayout) -> Register:
    quiet = keep(layout.quiet_bit)(emitter, image)
    return emitter.binop(BinopKind.NE, quiet, emitter.int_(0))


def signaling_nan_of(
    emitter: HlasmEmitter, image: Register, layout: BfpLayout
) -> Register:
    loud = emitter.binop(
        BinopKind.EQ, quiet_of(emitter, image, layout), emitter.int_(0)
    )
    return emitter.binop(BinopKind.MUL, nan_of(emitter, image, layout), loud)


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


def enabled_traps(emitter: HlasmEmitter, fpc: Register, trap: Register) -> Register:
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


def _deliver_once(
    emitter: HlasmEmitter,
    fpc: Register,
    enabled: Register,
    outcome: IeeeOutcome,
    deliver: Deliver,
) -> None:
    scaling = keep(SCALING_BITS)(emitter, enabled)
    scaled = emitter.binop(BinopKind.NE, scaling, emitter.int_(0))
    deliver(emitter.binop(BinopKind.MUL, scaled, emitter.int_(SCALED_SLOT)))
    emit_when(
        emitter, scaled, lambda: emit_data_exception(emitter, fpc, outcome.scaled_dxc)
    )


def as_raised(
    emitter: HlasmEmitter, fpc: Register, outcome: IeeeOutcome
) -> IeeeOutcome:
    return outcome


def emit_ieee_ladder(
    emitter: HlasmEmitter,
    raised: IeeeOutcome,
    deliver: Deliver,
    step: OutcomeStep = as_raised,
) -> None:
    fpc = emitter.load_var(FPC_VAR)
    outcome = step(emitter, fpc, raised)
    enabled = enabled_traps(emitter, fpc, outcome.trap)
    suppressing = keep(SUPPRESSING_BITS)(emitter, enabled)
    _when_any(
        emitter, suppressing, lambda: emit_data_exception(emitter, fpc, suppressing)
    )
    _deliver_once(emitter, fpc, enabled, outcome, deliver)
    flagged = _flagged(emitter, fpc, outcome.flags, enabled)
    emitter.emit_inst(StoreVar(name=FPC_VAR, value_reg=flagged))
    _when_any(
        emitter,
        enabled,
        lambda: emit_data_exception(emitter, flagged, outcome.inexact_dxc),
    )
