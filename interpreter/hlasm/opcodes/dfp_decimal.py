# pyright: standard
"""DFP to and from signed packed, unsigned packed and zoned decimal, in IR (ruling R52a): digits move between the DPD codec's fields and decimal lanes; a bad digit or sign is a data exception with DXC 0, suppressed (PoO 20-26 to 20-29, 20-33 to 20-37)."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.conditional import emit_when
from interpreter.hlasm.data_movement import (
    Sink,
    Source,
    doubleword_pair_at,
    from_gr64,
    keep,
    to_doubleword_pair,
    to_gr64,
)
from interpreter.hlasm.dfp_layout import EXTENDED_DFP, LONG_DFP, DfpLayout
from interpreter.hlasm.hlasm_constants import FPC_VAR
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.opcodes.bfp_forms import checked
from interpreter.hlasm.opcodes.decimal_lanes import (
    combined_digits,
    invalid_digits,
    spread_digits,
)
from interpreter.hlasm.opcodes.dfp_ir import Fields, decoded, fields_of, store_fields
from interpreter.hlasm.opcodes.floating_point_support import (
    emit_data_exception,
    pairs,
)
from interpreter.hlasm.opcodes.fpr_images import FIRST, SECOND, THIRD, fpr, pick
from interpreter.hlasm.operands import optional_mask_operand, reg_operand
from interpreter.hlasm.packed_decimal import MINUS_SIGNS, NOT_SIGNS, table_bit
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

PACKED_LANE = 4
SIGN_MASK = 0xF
MINUS_CODE = 0xD
PLUS_CODE = 0xC
PREFERRED_PLUS = 0xF
PLUS_SELECTION = 0b0001
GENERAL_OPERAND_DXC = 0

type SignedDigits = tuple[Register, Register, Register]


def packed_count(layout: DfpLayout) -> int:
    return layout.format.precision + 2


def emit_general_operand_check(emitter: HlasmEmitter, bad: Register) -> None:
    emit_when(
        emitter,
        bad,
        lambda: emit_data_exception(
            emitter, emitter.load_var(FPC_VAR), emitter.int_(GENERAL_OPERAND_DXC)
        ),
    )


def signed_nibbles(emitter: HlasmEmitter, image: Register) -> SignedDigits:
    sign = keep(SIGN_MASK)(emitter, image)
    digits = emitter.binop(BinopKind.RSHIFT, image, emitter.int_(PACKED_LANE))
    return (
        digits,
        table_bit(emitter, emitter.int_(MINUS_SIGNS), sign),
        table_bit(emitter, emitter.int_(NOT_SIGNS), sign),
    )


def unsigned_nibbles(emitter: HlasmEmitter, image: Register) -> SignedDigits:
    zero = emitter.int_(0)
    return image, zero, zero


def converted(
    emitter: HlasmEmitter, value: Register, negative: Register, layout: DfpLayout
) -> Fields:
    return negative, emitter.int_(layout.bias), value


type Nibbles = Callable[[HlasmEmitter, Register], SignedDigits]


def _from_register(
    layout: DfpLayout, read: Source, nibbles: tuple[Nibbles, int]
) -> StatementLowering:
    split, count = nibbles

    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        digits, negative, bad_sign = split(emitter, read(emitter, statement))
        bad_digits = invalid_digits(emitter, digits, PACKED_LANE, count)
        emit_general_operand_check(
            emitter, emitter.binop(BinopKind.BIT_OR, bad_digits, bad_sign)
        )
        function = combined_digits(PACKED_LANE, packed_count(layout))
        value = function.call(emitter, (digits,))
        fields = converted(emitter, value, negative, layout)
        store_fields(emitter, reg_operand(statement, FIRST), layout, fields)

    return lower


def sign_code(
    emitter: HlasmEmitter, negative: Register, preferred_plus: bool
) -> Register:
    plus = emitter.int_(PREFERRED_PLUS if preferred_plus else PLUS_CODE)
    return pick(emitter, negative, emitter.int_(MINUS_CODE), plus)


def digit_lanes(
    emitter: HlasmEmitter, significand: Register, count: int, lanes: tuple[int, int]
) -> tuple[Register, Register]:
    lane_bits, functions = lanes
    modulus = emitter.int_(10**count)
    kept = emitter.binop(BinopKind.MOD, significand, modulus)
    spread = spread_digits(lane_bits, functions).call(emitter, (kept,))
    return kept, spread


def _register_image(
    emitter: HlasmEmitter,
    statement: MachineStatement,
    digits: tuple[Register, Register],
    signed: bool,
) -> Register:
    image, sign = digits
    if not signed:
        return image
    preferred = bool(optional_mask_operand(statement, THIRD, 0) & PLUS_SELECTION)
    shifted = emitter.binop(BinopKind.LSHIFT, image, emitter.int_(PACKED_LANE))
    return emitter.binop(BinopKind.BIT_OR, shifted, sign_code(emitter, sign, preferred))


def _to_register(
    layout: DfpLayout, store: Sink, signed: bool, count: int
) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        source = decoded(fpr(SECOND, layout), layout)(emitter, statement)
        sign, _exponent, significand = fields_of(emitter, source)
        lanes = (PACKED_LANE, layout.format.precision)
        image = digit_lanes(emitter, significand, count, lanes)[1]
        digits = (image, sign)
        store(emitter, statement, _register_image(emitter, statement, digits, signed))

    return lower


def _odd(index: int) -> Callable[[MachineStatement], bool]:
    return lambda statement: bool(reg_operand(statement, index) & 1)


REGISTER_FORMS: Mapping[str, StatementLowering] = {
    "CDSTR": _from_register(LONG_DFP, from_gr64(SECOND), (signed_nibbles, 15)),
    "CDUTR": _from_register(LONG_DFP, from_gr64(SECOND), (unsigned_nibbles, 16)),
    "CXSTR": checked(
        _odd(SECOND),
        pairs(
            (FIRST,),
            _from_register(
                EXTENDED_DFP, doubleword_pair_at(SECOND), (signed_nibbles, 31)
            ),
        ),
    ),
    "CXUTR": checked(
        _odd(SECOND),
        pairs(
            (FIRST,),
            _from_register(
                EXTENDED_DFP, doubleword_pair_at(SECOND), (unsigned_nibbles, 32)
            ),
        ),
    ),
    "CSDTR": _to_register(LONG_DFP, to_gr64, True, 15),
    "CUDTR": _to_register(LONG_DFP, to_gr64, False, 16),
    "CSXTR": checked(
        _odd(FIRST),
        pairs((SECOND,), _to_register(EXTENDED_DFP, to_doubleword_pair, True, 31)),
    ),
    "CUXTR": checked(
        _odd(FIRST),
        pairs((SECOND,), _to_register(EXTENDED_DFP, to_doubleword_pair, False, 32)),
    ),
}


DFP_DECIMAL_LOWERINGS: Mapping[str, StatementLowering] = {**REGISTER_FORMS}
