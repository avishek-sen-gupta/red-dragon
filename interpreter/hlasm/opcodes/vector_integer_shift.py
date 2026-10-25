# pyright: standard
"""Vector integer shift and rotate instructions: element shifts and rotates by the D2(B2) address, by each V3 element or by I4, unrolled per element; whole-register shifts by a byte count, per-byte bit shifts over a 16-bit window of V2 extended by one byte, and double shifts over the 256-bit V2 || V3."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.data_movement import storage_address_at
from interpreter.hlasm.element_return_field import RESULT_BITS
from interpreter.hlasm.element_size import ElementSize
from interpreter.hlasm.hlasm_constants import BITS_PER_BYTE, VECTOR_REGISTER_BYTES
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.fp_forms import checked
from interpreter.hlasm.opcodes.vector_fields import (
    FIFTH,
    FOURTH,
    SECOND,
    THIRD,
    V1,
    assembled,
    element_bits,
    element_of,
    element_wise,
    ones,
    pair,
    per_size,
    to_v1,
    vr_at,
)
from interpreter.hlasm.operands import imm_operand
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

I4_IMAGE = 0xFF
DOUBLE_BYTE_INDEX = 0b1111
BIT_COUNT = 0b111
COUNT_BYTE = 7
BYTE_COUNT_SHIFT = RESULT_BITS - BITS_PER_BYTE * (COUNT_BYTE + 1)
BYTE_COUNT_BITS = 0b1111000
WINDOW = ones(2 * BITS_PER_BYTE)
LAST_BYTE = VECTOR_REGISTER_BYTES - 1
SIGN_BYTE = ones(BITS_PER_BYTE) << RESULT_BITS

B, H, F, G = (
    ElementSize.BYTE,
    ElementSize.HALFWORD,
    ElementSize.WORD,
    ElementSize.DOUBLEWORD,
)
UP_TO_DOUBLEWORD = frozenset({B, H, F, G})

type Shift = Callable[[HlasmEmitter, Register, Register, int], Register]
type Extend = Callable[[HlasmEmitter, Register], Register]
type Take = Callable[[HlasmEmitter, Register, Register], Register]


def _left(
    emitter: HlasmEmitter, value: Register, count: Register, bits: int
) -> Register:
    return emitter.binop(BinopKind.LSHIFT, value, count)


def _right(
    emitter: HlasmEmitter, value: Register, count: Register, bits: int
) -> Register:
    return emitter.binop(BinopKind.RSHIFT, value, count)


def _right_arithmetic(
    emitter: HlasmEmitter, value: Register, count: Register, bits: int
) -> Register:
    sign = emitter.binop(BinopKind.RSHIFT, value, emitter.int_(bits - 1))
    kept = emitter.binop(BinopKind.RSHIFT, emitter.int_(ones(bits)), count)
    vacated = emitter.binop(BinopKind.BIT_XOR, kept, emitter.int_(ones(bits)))
    fill = emitter.binop(BinopKind.MUL, sign, vacated)
    return emitter.binop(BinopKind.BIT_OR, _right(emitter, value, count, bits), fill)


def _rotate(
    emitter: HlasmEmitter, value: Register, count: Register, bits: int
) -> Register:
    back = emitter.binop(BinopKind.SUB, emitter.int_(bits), count)
    wrapped = emitter.binop(BinopKind.RSHIFT, value, back)
    return emitter.binop(BinopKind.BIT_OR, _left(emitter, value, count, bits), wrapped)


def _modulo(emitter: HlasmEmitter, count: Register, bits: int) -> Register:
    return emitter.binop(BinopKind.BIT_AND, count, emitter.int_(bits - 1))


def _each(
    emitter: HlasmEmitter,
    shift: Shift,
    source: Register,
    count: Register,
    size: ElementSize,
) -> Register:
    bits = element_bits(size)
    pieces = [
        shift(emitter, element_of(emitter, source, size, at), count, bits)
        for at in range(size.count)
    ]
    return assembled(emitter, size, pieces)


def _by_address(shift: Shift) -> Callable[[ElementSize], StatementLowering]:
    def build(size: ElementSize) -> StatementLowering:
        def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
            source = vr_at(SECOND)(emitter, statement)
            address = storage_address_at(THIRD)(emitter, statement)
            count = _modulo(emitter, address, element_bits(size))
            to_v1(emitter, statement, _each(emitter, shift, source, count, size))

        return lower

    return build


def _by_vector(shift: Shift) -> Callable[[ElementSize], StatementLowering]:
    def build(size: ElementSize) -> StatementLowering:
        bits = element_bits(size)
        return element_wise(
            2,
            lambda emitter, both: shift(
                emitter, both[0], _modulo(emitter, both[1], bits), bits
            ),
        )(size)

    return build


def _rotate_and_insert(size: ElementSize) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        source = vr_at(SECOND)(emitter, statement)
        mask = vr_at(THIRD)(emitter, statement)
        target = vr_at(V1)(emitter, statement)
        by = imm_operand(statement, FOURTH) % element_bits(size)
        count = emitter.int_(by)
        rotated = _each(emitter, _rotate, source, count, size)
        outside = emitter.binop(
            BinopKind.BIT_XOR, mask, emitter.int_(ones(RESULT_BITS))
        )
        kept = emitter.binop(BinopKind.BIT_AND, target, outside)
        inserted = emitter.binop(BinopKind.BIT_AND, rotated, mask)
        to_v1(emitter, statement, emitter.binop(BinopKind.BIT_OR, kept, inserted))

    return lower


def _by_bytes(shift: Shift) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        source = vr_at(SECOND)(emitter, statement)
        counts = vr_at(THIRD)(emitter, statement)
        moved = emitter.binop(BinopKind.RSHIFT, counts, emitter.int_(BYTE_COUNT_SHIFT))
        count = emitter.binop(BinopKind.BIT_AND, moved, emitter.int_(BYTE_COUNT_BITS))
        to_v1(emitter, statement, shift(emitter, source, count, RESULT_BITS))

    return lower


def _field(emitter: HlasmEmitter, value: Register, shift: int, mask: int) -> Register:
    moved = emitter.binop(BinopKind.RSHIFT, value, emitter.int_(shift))
    return emitter.binop(BinopKind.BIT_AND, moved, emitter.int_(mask))


def _per_byte(extend: Extend, take: Take) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        extended = extend(emitter, vr_at(SECOND)(emitter, statement))
        counts = vr_at(THIRD)(emitter, statement)

        def byte(at: int) -> Register:
            shift = BITS_PER_BYTE * (LAST_BYTE - at)
            window = _field(emitter, extended, shift, WINDOW)
            return take(emitter, window, _field(emitter, counts, shift, BIT_COUNT))

        pieces = [byte(at) for at in range(VECTOR_REGISTER_BYTES)]
        to_v1(emitter, statement, assembled(emitter, B, pieces))

    return lower


def _zero_byte_right(emitter: HlasmEmitter, value: Register) -> Register:
    return emitter.binop(BinopKind.LSHIFT, value, emitter.int_(BITS_PER_BYTE))


def _zero_byte_left(emitter: HlasmEmitter, value: Register) -> Register:
    return value


def _sign_byte_left(emitter: HlasmEmitter, value: Register) -> Register:
    sign = emitter.binop(BinopKind.RSHIFT, value, emitter.int_(RESULT_BITS - 1))
    fill = emitter.binop(BinopKind.MUL, sign, emitter.int_(SIGN_BYTE))
    return emitter.binop(BinopKind.BIT_OR, value, fill)


def _high_byte(emitter: HlasmEmitter, window: Register, count: Register) -> Register:
    moved = emitter.binop(BinopKind.LSHIFT, window, count)
    return emitter.binop(BinopKind.RSHIFT, moved, emitter.int_(BITS_PER_BYTE))


def _low_byte(emitter: HlasmEmitter, window: Register, count: Register) -> Register:
    return emitter.binop(BinopKind.RSHIFT, window, count)


def _double(right_by: Callable[[int], int]) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        by = right_by(imm_operand(statement, FOURTH) & I4_IMAGE)
        both = pair(emitter, statement)
        to_v1(emitter, statement, _field(emitter, both, by, ones(RESULT_BITS)))

    return lower


def _bit_count_checked(lowering: StatementLowering) -> StatementLowering:
    return checked(
        lambda statement: imm_operand(statement, FOURTH) & I4_IMAGE & ~BIT_COUNT != 0,
        lowering,
    )


VECTOR_INTEGER_SHIFT_LOWERINGS: Mapping[str, StatementLowering] = {
    "VERLL": per_size(FOURTH, UP_TO_DOUBLEWORD, _by_address(_rotate)),
    "VERLLV": per_size(FOURTH, UP_TO_DOUBLEWORD, _by_vector(_rotate)),
    "VERIM": per_size(FIFTH, UP_TO_DOUBLEWORD, _rotate_and_insert),
    "VESL": per_size(FOURTH, UP_TO_DOUBLEWORD, _by_address(_left)),
    "VESLV": per_size(FOURTH, UP_TO_DOUBLEWORD, _by_vector(_left)),
    "VESRA": per_size(FOURTH, UP_TO_DOUBLEWORD, _by_address(_right_arithmetic)),
    "VESRAV": per_size(FOURTH, UP_TO_DOUBLEWORD, _by_vector(_right_arithmetic)),
    "VESRL": per_size(FOURTH, UP_TO_DOUBLEWORD, _by_address(_right)),
    "VESRLV": per_size(FOURTH, UP_TO_DOUBLEWORD, _by_vector(_right)),
    "VSL": _per_byte(_zero_byte_right, _high_byte),
    "VSRA": _per_byte(_sign_byte_left, _low_byte),
    "VSRL": _per_byte(_zero_byte_left, _low_byte),
    "VSLB": _by_bytes(_left),
    "VSRAB": _by_bytes(_right_arithmetic),
    "VSRLB": _by_bytes(_right),
    "VSLD": _bit_count_checked(_double(lambda by: RESULT_BITS - by)),
    "VSRD": _bit_count_checked(_double(lambda by: by)),
    "VSLDB": _double(lambda by: RESULT_BITS - BITS_PER_BYTE * (by & DOUBLE_BYTE_INDEX)),
}
