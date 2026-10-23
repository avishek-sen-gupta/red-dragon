# pyright: standard
"""IR for HFP images: field lists for the builtins, normalized fields of an exact binary value, images from result fields with the extended low-order part, an image's condition code, and the program-mask ladder (ruling R46)."""

from collections.abc import Callable, Sequence

from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.bit_counts import leading_zeros
from interpreter.hlasm.conditional import emit_when
from interpreter.hlasm.data_movement import Source, keep
from interpreter.hlasm.hfp_layout import (
    CHARACTERISTIC_MASK,
    PART_FRACTION_BITS,
    PART_WIDTH,
    HfpLayout,
)
from interpreter.hlasm.hfp_slots import (
    CONDITIONS_SLOT,
    DIVIDE_BIT,
    MASKABLE_BITS,
    OVERFLOW_BIT,
    SIGNIFICANCE_BIT,
    SQUARE_ROOT_BIT,
    UNDERFLOW_BIT,
)
from interpreter.hlasm.hlasm_constants import (
    DOUBLEWORD_BITS,
    HFP_DIVIDE_ABEND,
    HFP_EXPONENT_OVERFLOW_ABEND,
    HFP_EXPONENT_UNDERFLOW_ABEND,
    HFP_SIGNIFICANCE_ABEND,
    HFP_SQUARE_ROOT_ABEND,
    PROGRAM_MASK_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.fpr_images import list_item, list_of
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type LowCharacteristic = Callable[[HlasmEmitter, Register, Register], Register]
type Deliver = Callable[[Register], None]
type Exceptions = Sequence[tuple[int, str]]

PART_MASK = (1 << PART_WIDTH) - 1
PART_FRACTION_MASK = (1 << PART_FRACTION_BITS) - 1
LOW_CHARACTERISTIC_OFFSET = 128 - 14
EXCESS_DIGIT = 65
BITS_PER_DIGIT = 4
DIGIT_SHIFT = 2
POSITIVE_CC = 2
SIGN, CHARACTERISTIC, FRACTION = 0, 1, 2
SUPPRESSING: Exceptions = (
    (DIVIDE_BIT, HFP_DIVIDE_ABEND),
    (SQUARE_ROOT_BIT, HFP_SQUARE_ROOT_ABEND),
)
COMPLETING_BITS = OVERFLOW_BIT | UNDERFLOW_BIT | SIGNIFICANCE_BIT
COMPLETING: Exceptions = (
    (OVERFLOW_BIT, HFP_EXPONENT_OVERFLOW_ABEND),
    (UNDERFLOW_BIT, HFP_EXPONENT_UNDERFLOW_ABEND),
    (SIGNIFICANCE_BIT, HFP_SIGNIFICANCE_ABEND),
)


def _shifted(emitter: HlasmEmitter, value: Register, shift: int) -> Register:
    return emitter.binop(BinopKind.RSHIFT, value, emitter.int_(shift))


def _placed(emitter: HlasmEmitter, value: Register, shift: int) -> Register:
    return emitter.binop(BinopKind.LSHIFT, value, emitter.int_(shift))


def _or(emitter: HlasmEmitter, *values: Register) -> Register:
    first, *rest = values
    return (
        emitter.binop(BinopKind.BIT_OR, first, _or(emitter, *rest)) if rest else first
    )


def _fraction(emitter: HlasmEmitter, image: Register, layout: HfpLayout) -> Register:
    if layout.width <= PART_WIDTH:
        return keep(layout.fraction_mask)(emitter, image)
    high = keep(PART_FRACTION_MASK)(emitter, _shifted(emitter, image, PART_WIDTH))
    low = keep(PART_FRACTION_MASK)(emitter, image)
    return _or(emitter, _placed(emitter, high, PART_FRACTION_BITS), low)


def sign_of(emitter: HlasmEmitter, image: Register, layout: HfpLayout) -> Register:
    return _shifted(emitter, image, layout.sign_shift)


def fields_of(
    emitter: HlasmEmitter, image: Register, layout: HfpLayout
) -> tuple[Register, Register, Register]:
    characteristic = keep(CHARACTERISTIC_MASK)(
        emitter, _shifted(emitter, image, layout.characteristic_shift)
    )
    return (
        sign_of(emitter, image, layout),
        characteristic,
        _fraction(emitter, image, layout),
    )


def fields_list(emitter: HlasmEmitter, image: Register, layout: HfpLayout) -> Register:
    return list_of(emitter, fields_of(emitter, image, layout))


def field_sources(layout: HfpLayout, sources: Sequence[Source]) -> tuple[Source, ...]:
    return tuple(_field_list(source, layout) for source in sources)


def _field_list(image: Source, layout: HfpLayout) -> Source:
    return lambda emitter, statement: fields_list(
        emitter, image(emitter, statement), layout
    )


def _positive_part(emitter: HlasmEmitter, value: Register) -> Register:
    positive = emitter.binop(BinopKind.GT, value, emitter.int_(0))
    return emitter.binop(BinopKind.MUL, positive, value)


def normalized_fields(
    emitter: HlasmEmitter,
    negative: Register,
    binary: tuple[Register, Register],
    layout: HfpLayout,
) -> tuple[Register, Register, Register]:
    magnitude, exponent = binary
    top = emitter.binop(
        BinopKind.SUB,
        emitter.int_(DOUBLEWORD_BITS - 1),
        leading_zeros(emitter, magnitude),
    )
    leading = emitter.binop(BinopKind.ADD, top, exponent)
    digits = _shifted(emitter, leading, DIGIT_SHIFT)
    characteristic = emitter.binop(BinopKind.ADD, digits, emitter.int_(EXCESS_DIGIT))
    shift = emitter.binop(
        BinopKind.SUB,
        emitter.binop(BinopKind.ADD, exponent, emitter.int_(layout.fraction_bits)),
        emitter.binop(
            BinopKind.MUL,
            emitter.binop(BinopKind.ADD, digits, emitter.int_(1)),
            emitter.int_(BITS_PER_DIGIT),
        ),
    )
    left = emitter.binop(BinopKind.LSHIFT, magnitude, _positive_part(emitter, shift))
    right = _positive_part(
        emitter, emitter.binop(BinopKind.SUB, emitter.int_(0), shift)
    )
    nonzero = emitter.binop(BinopKind.NE, magnitude, emitter.int_(0))
    return (
        negative,
        emitter.binop(BinopKind.MUL, nonzero, characteristic),
        emitter.binop(BinopKind.RSHIFT, left, right),
    )


def true_zero_low(
    emitter: HlasmEmitter, characteristic: Register, fraction: Register
) -> Register:
    nonzero = emitter.binop(
        BinopKind.NE, _or(emitter, characteristic, fraction), emitter.int_(0)
    )
    return emitter.binop(
        BinopKind.MUL, nonzero, wrapped_low(emitter, characteristic, fraction)
    )


def wrapped_low(
    emitter: HlasmEmitter, characteristic: Register, fraction: Register
) -> Register:
    lowered = emitter.binop(
        BinopKind.ADD, characteristic, emitter.int_(LOW_CHARACTERISTIC_OFFSET)
    )
    return keep(CHARACTERISTIC_MASK)(emitter, lowered)


def _part(
    emitter: HlasmEmitter, sign: Register, characteristic: Register, fraction: Register
) -> Register:
    return _or(
        emitter,
        _placed(emitter, sign, PART_WIDTH - 1),
        _placed(emitter, characteristic, PART_FRACTION_BITS),
        fraction,
    )


def image_of(
    emitter: HlasmEmitter,
    fields: tuple[Register, Register, Register],
    layout: HfpLayout,
    low: LowCharacteristic,
) -> Register:
    sign, characteristic, fraction = fields
    if layout.width <= PART_WIDTH:
        return _or(
            emitter,
            _placed(emitter, sign, layout.sign_shift),
            _placed(emitter, characteristic, layout.characteristic_shift),
            fraction,
        )
    high = _part(
        emitter, sign, characteristic, _shifted(emitter, fraction, PART_FRACTION_BITS)
    )
    low_part = _part(
        emitter,
        sign,
        low(emitter, characteristic, fraction),
        keep(PART_FRACTION_MASK)(emitter, fraction),
    )
    return _or(emitter, _placed(emitter, high, PART_WIDTH), low_part)


def result_image(
    emitter: HlasmEmitter, result: Register, layout: HfpLayout, low: LowCharacteristic
) -> Register:
    sign, characteristic, fraction = (
        list_item(emitter, result, slot) for slot in (SIGN, CHARACTERISTIC, FRACTION)
    )
    return image_of(emitter, (sign, characteristic, fraction), layout, low)


def image_cc(emitter: HlasmEmitter, image: Register, layout: HfpLayout) -> Register:
    fraction = keep(layout.fraction_mask)(emitter, image)
    nonzero = emitter.binop(BinopKind.NE, fraction, emitter.int_(0))
    signed = emitter.binop(
        BinopKind.SUB, emitter.int_(POSITIVE_CC), sign_of(emitter, image, layout)
    )
    return emitter.binop(BinopKind.MUL, nonzero, signed)


def _abend_on(emitter: HlasmEmitter, raised: Register, exceptions: Exceptions) -> None:
    _ = [
        emit_when(
            emitter,
            emitter.binop(
                BinopKind.NE,
                emitter.binop(BinopKind.BIT_AND, raised, emitter.int_(bit)),
                emitter.int_(0),
            ),
            lambda code=code: emit_abend(emitter, code),
        )
        for bit, code in exceptions
    ]


def _only(exceptions: Exceptions, raisable: int) -> Exceptions:
    return tuple((bit, code) for bit, code in exceptions if bit & raisable)


def _zeroed(emitter: HlasmEmitter, conditions: Register, mask: Register) -> Register:
    unmasked = emitter.binop(BinopKind.BIT_XOR, mask, emitter.int_(MASKABLE_BITS))
    zeroed = emitter.binop(
        BinopKind.BIT_AND, keep(MASKABLE_BITS)(emitter, conditions), unmasked
    )
    return emitter.binop(BinopKind.NE, zeroed, emitter.int_(0))


def _completed(
    emitter: HlasmEmitter, conditions: Register, raisable: int, deliver: Deliver
) -> None:
    mask = emitter.load_var(PROGRAM_MASK_VAR)
    deliver(_zeroed(emitter, conditions, mask))
    enabled = emitter.binop(BinopKind.BIT_OR, mask, emitter.int_(OVERFLOW_BIT))
    taken = emitter.binop(BinopKind.BIT_AND, conditions, enabled)
    _abend_on(emitter, taken, _only(COMPLETING, raisable))


def emit_program_mask_ladder(
    emitter: HlasmEmitter, result: Register, raisable: int, deliver: Deliver
) -> None:
    if not raisable:
        deliver(emitter.int_(0))
        return
    conditions = list_item(emitter, result, CONDITIONS_SLOT)
    _abend_on(emitter, conditions, _only(SUPPRESSING, raisable))
    if not raisable & COMPLETING_BITS:
        deliver(emitter.int_(0))
        return
    _completed(emitter, conditions, raisable, deliver)
