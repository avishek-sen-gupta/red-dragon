# pyright: standard
"""IR for HFP images: field lists for the builtins, images from result fields with the extended low-order part, an image's condition code, and the program-mask ladder (ruling R46)."""

from collections.abc import Callable, Sequence

from interpreter.hlasm.abend import emit_abend
from interpreter.hlasm.conditional import emit_when
from interpreter.hlasm.data_movement import keep
from interpreter.hlasm.hfp_layout import (
    CHARACTERISTIC_BITS,
    PART_FRACTION_BITS,
    PART_WIDTH,
    HfpLayout,
)
from interpreter.hlasm.hfp_slots import (
    MASKABLE_BITS,
    OVERFLOW_BIT,
    SIGNIFICANCE_BIT,
    UNDERFLOW_BIT,
)
from interpreter.hlasm.hlasm_constants import (
    HFP_EXPONENT_OVERFLOW_ABEND,
    HFP_EXPONENT_UNDERFLOW_ABEND,
    HFP_SIGNIFICANCE_ABEND,
    PROGRAM_MASK_VAR,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.fpr_images import list_item, list_of
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

type LowCharacteristic = Callable[[HlasmEmitter, Register, Register], Register]
type Deliver = Callable[[Register], None]
type Exceptions = Sequence[tuple[int, str]]

CHARACTERISTIC_MASK = (1 << CHARACTERISTIC_BITS) - 1
PART_MASK = (1 << PART_WIDTH) - 1
PART_FRACTION_MASK = (1 << PART_FRACTION_BITS) - 1
LOW_CHARACTERISTIC_OFFSET = 128 - 14
POSITIVE_CC = 2
SIGN, CHARACTERISTIC, FRACTION = 0, 1, 2
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


def emit_program_mask_ladder(
    emitter: HlasmEmitter,
    conditions: Register,
    suppressing: Exceptions,
    deliver: Deliver,
) -> None:
    _abend_on(emitter, conditions, suppressing)
    mask = emitter.load_var(PROGRAM_MASK_VAR)
    unmasked = emitter.binop(BinopKind.BIT_XOR, mask, emitter.int_(MASKABLE_BITS))
    zeroed = emitter.binop(
        BinopKind.BIT_AND, keep(MASKABLE_BITS)(emitter, conditions), unmasked
    )
    deliver(emitter.binop(BinopKind.NE, zeroed, emitter.int_(0)))
    enabled = emitter.binop(BinopKind.BIT_OR, mask, emitter.int_(OVERFLOW_BIT))
    taken = emitter.binop(BinopKind.BIT_AND, conditions, enabled)
    _abend_on(emitter, taken, COMPLETING)
