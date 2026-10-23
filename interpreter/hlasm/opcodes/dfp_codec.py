# pyright: standard
"""DFP images to and from [negative, e, significand] as IR functions, one per format (ruling R49): e is the biased exponent, or -1 infinity, -2 QNaN, -3 SNaN (PoO figures 20-1, 20-21)."""

from collections.abc import Mapping, Sequence

from interpreter.hlasm.data_movement import keep
from interpreter.hlasm.dfp_fields import INFINITY, QUIET_NAN, SIGNALING_NAN
from interpreter.hlasm.dfp_layout import (
    EXTENDED_DFP,
    LONG_DFP,
    SHORT_DFP,
    DfpLayout,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.ir_function import Body, IrFunction
from interpreter.hlasm.opcodes.dpd_lanes import declets_to_integer, integer_to_declets
from interpreter.hlasm.opcodes.fpr_images import list_of, pick
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

TOP_MASK = 0b11111
INFINITY_TOP = 0b11110
NAN_TOP = 0b11111
BIG_DIGIT_TOP = 0b11000
BIG_DIGIT = 8
DIGIT_BITS = 0b111
HIGH_BITS = 0b11
HIGH_SHIFT = 3


def _shifted(emitter: HlasmEmitter, value: Register, shift: int) -> Register:
    return emitter.binop(BinopKind.RSHIFT, value, emitter.int_(shift))


def _placed(emitter: HlasmEmitter, value: Register, shift: int) -> Register:
    return emitter.binop(BinopKind.LSHIFT, value, emitter.int_(shift))


def _or(emitter: HlasmEmitter, *values: Register) -> Register:
    first, *rest = values
    return (
        emitter.binop(BinopKind.BIT_OR, first, _or(emitter, *rest)) if rest else first
    )


def _compared(
    emitter: HlasmEmitter, operator: BinopKind, value: Register, against: int
) -> Register:
    return emitter.binop(operator, value, emitter.int_(against))


def _finite_exponent(
    emitter: HlasmEmitter, top: Register, big: Register, layout: DfpLayout
) -> Register:
    high = pick(
        emitter,
        big,
        keep(HIGH_BITS)(emitter, _shifted(emitter, top, 1)),
        _shifted(emitter, top, HIGH_SHIFT),
    )
    return _placed(emitter, high, layout.continuation_bits)


def _leftmost(emitter: HlasmEmitter, top: Register, big: Register) -> Register:
    eight_or_nine = emitter.binop(
        BinopKind.ADD, keep(1)(emitter, top), emitter.int_(BIG_DIGIT)
    )
    return pick(emitter, big, eight_or_nine, keep(DIGIT_BITS)(emitter, top))


def _special_code(
    emitter: HlasmEmitter, top: Register, continuation: Register, layout: DfpLayout
) -> Register:
    signaling = _shifted(emitter, continuation, layout.continuation_bits - 1)
    return pick(
        emitter,
        _compared(emitter, BinopKind.EQ, top, INFINITY_TOP),
        emitter.int_(INFINITY),
        emitter.binop(BinopKind.SUB, emitter.int_(QUIET_NAN), signaling),
    )


def _trailing(emitter: HlasmEmitter, image: Register, layout: DfpLayout) -> Register:
    declets = keep((1 << layout.trailing_bits) - 1)(emitter, image)
    return declets_to_integer(emitter, declets, layout.declets)


def _decoded(
    emitter: HlasmEmitter, image: Register, top: Register, layout: DfpLayout
) -> tuple[Register, Register]:
    continuation = keep((1 << layout.continuation_bits) - 1)(
        emitter, _shifted(emitter, image, layout.continuation_shift)
    )
    big = _compared(emitter, BinopKind.GE, top, BIG_DIGIT_TOP)
    biased = emitter.binop(
        BinopKind.BIT_OR, _finite_exponent(emitter, top, big, layout), continuation
    )
    finite = _compared(emitter, BinopKind.LT, top, INFINITY_TOP)
    weight = emitter.int_(10**layout.trailing_digits)
    leading = emitter.binop(BinopKind.MUL, _leftmost(emitter, top, big), weight)
    significand = emitter.binop(
        BinopKind.ADD,
        _trailing(emitter, image, layout),
        emitter.binop(BinopKind.MUL, finite, leading),
    )
    special = _special_code(emitter, top, continuation, layout)
    return pick(emitter, finite, biased, special), significand


def _decode(layout: DfpLayout) -> Body:
    def body(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
        (image,) = parameters
        sign = _shifted(emitter, image, layout.sign_shift)
        top = keep(TOP_MASK)(emitter, _shifted(emitter, image, layout.top_shift))
        return list_of(emitter, (sign, *_decoded(emitter, image, top, layout)))

    return body


def _top(
    emitter: HlasmEmitter, exponent: Register, leftmost: Register, layout: DfpLayout
) -> Register:
    high = _shifted(emitter, exponent, layout.continuation_bits)
    big = _compared(emitter, BinopKind.GE, leftmost, BIG_DIGIT)
    big_top = _or(
        emitter,
        emitter.int_(BIG_DIGIT_TOP),
        _placed(emitter, high, 1),
        keep(1)(emitter, leftmost),
    )
    small_top = emitter.binop(
        BinopKind.BIT_OR, _placed(emitter, high, HIGH_SHIFT), leftmost
    )
    return pick(emitter, big, big_top, small_top)


def _special_top(emitter: HlasmEmitter, exponent: Register) -> Register:
    return pick(
        emitter,
        _compared(emitter, BinopKind.EQ, exponent, INFINITY),
        emitter.int_(INFINITY_TOP),
        emitter.int_(NAN_TOP),
    )


def _continuation(
    emitter: HlasmEmitter, exponent: Register, finite: Register, layout: DfpLayout
) -> Register:
    signaling = _placed(
        emitter,
        _compared(emitter, BinopKind.EQ, exponent, SIGNALING_NAN),
        layout.continuation_bits - 1,
    )
    biased = emitter.binop(BinopKind.MUL, exponent, finite)
    own = keep((1 << layout.continuation_bits) - 1)(emitter, biased)
    return pick(emitter, finite, own, signaling)


def _combination(
    emitter: HlasmEmitter, exponent: Register, significand: Register, layout: DfpLayout
) -> Register:
    finite = _compared(emitter, BinopKind.GE, exponent, 0)
    weight = emitter.int_(10**layout.trailing_digits)
    leftmost = emitter.binop(BinopKind.FLOOR_DIV, significand, weight)
    biased = emitter.binop(BinopKind.MUL, exponent, finite)
    finite_top = _top(emitter, biased, leftmost, layout)
    top = pick(emitter, finite, finite_top, _special_top(emitter, exponent))
    return emitter.binop(
        BinopKind.BIT_OR,
        _placed(emitter, top, layout.continuation_bits),
        _continuation(emitter, exponent, finite, layout),
    )


def _encode(layout: DfpLayout) -> Body:
    def body(emitter: HlasmEmitter, parameters: Sequence[Register]) -> Register:
        negative, exponent, significand = parameters
        weight = emitter.int_(10**layout.trailing_digits)
        trailing = emitter.binop(BinopKind.MOD, significand, weight)
        return _or(
            emitter,
            _placed(emitter, negative, layout.sign_shift),
            _placed(
                emitter,
                _combination(emitter, exponent, significand, layout),
                layout.continuation_shift,
            ),
            integer_to_declets(emitter, trailing, layout.declets),
        )

    return body


DECODERS: Mapping[DfpLayout, IrFunction] = {
    layout: IrFunction(f"__hlasm_dfp_decode_{layout.suffix}", 1, _decode(layout))
    for layout in (SHORT_DFP, LONG_DFP, EXTENDED_DFP)
}
ENCODERS: Mapping[DfpLayout, IrFunction] = {
    layout: IrFunction(f"__hlasm_dfp_encode_{layout.suffix}", 3, _encode(layout))
    for layout in (LONG_DFP, EXTENDED_DFP)
}
DFP_CODEC_FUNCTIONS: tuple[IrFunction, ...] = (*DECODERS.values(), *ENCODERS.values())
