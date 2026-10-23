# pyright: standard
"""IR for BFP images: field lists for the builtins, images from result fields or from an exact magnitude, an image's condition code, and the BFP rounding mode."""

from interpreter.hlasm.bfp_layout import BfpLayout
from interpreter.hlasm.bit_counts import leading_zeros
from interpreter.hlasm.conditional import pick
from interpreter.hlasm.data_movement import keep
from interpreter.hlasm.hlasm_constants import DOUBLEWORD_BITS, FPC_VAR
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.floating_point_support import BFP_MODE_SHIFT, MODE_FIELD
from interpreter.hlasm.opcodes.fp_ir import field_at, mode_code_of
from interpreter.hlasm.opcodes.fpr_images import list_of
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

BFP_FPC_TO_MODIFIER = 4
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


def bfp_mode_of(emitter: HlasmEmitter, fpc: Register) -> Register:
    code = mode_code_of(emitter, fpc, BFP_MODE_SHIFT, BFP_FPC_TO_MODIFIER)
    return keep(MODE_FIELD)(emitter, code)


def current_mode(emitter: HlasmEmitter) -> Register:
    return bfp_mode_of(emitter, emitter.load_var(FPC_VAR))
