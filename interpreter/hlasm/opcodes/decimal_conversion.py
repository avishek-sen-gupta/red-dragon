# pyright: standard
"""Decimal conversion: CVB and CVD between registers and signed-packed fields, PACK and UNPK between zoned and packed, and the ASCII and Unicode forms PKA, PKU, UNPKA and UNPKU; only CVB checks codes, and only UNPKA and UNPKU set the CC."""

from collections.abc import Callable, Mapping

from hlasm_asg.program.machine_statement import MachineStatement
from interpreter.hlasm.byte_one_layouts import (
    LENGTH_BYTE,
    LENGTH_NIBBLES,
    SECOND_LENGTH_BYTE,
)
from interpreter.hlasm.character_field import CharacterField
from interpreter.hlasm.data_field import DataField, LowerWithField
from interpreter.hlasm.data_movement import (
    FIRST_OPERAND,
    SECOND_OPERAND,
    Source,
    from_gr32,
    from_gr64,
    signed,
    to_gr32,
    to_gr64,
)
from interpreter.hlasm.decimal_exceptions import emit_data_check
from interpreter.hlasm.decimal_packing import SignOf, emit_pack, emit_unpack
from interpreter.hlasm.digit_source import DigitSource
from interpreter.hlasm.effective_address import (
    effective_address,
    length_operand_address,
)
from interpreter.hlasm.field_lowering import FieldLowering, written_lowerings
from interpreter.hlasm.fixed_point_divide import emit_fixed_point_divide_check
from interpreter.hlasm.hlasm_constants import (
    DOUBLEWORD_BITS,
    DOUBLEWORD_BYTES,
    NIBBLE_BITS,
    NIBBLE_MASK,
    ONE_BYTE,
    QUADWORD_BYTES,
    WORD_BITS,
)
from interpreter.hlasm.hlasm_emitter import HlasmEmitter
from interpreter.hlasm.operands import storage_length_operand, storage_operand
from interpreter.hlasm.packed_decimal import (
    MINUS_SIGNS,
    NOT_SIGNS,
    PLUS_SIGN,
    negative_bit,
    read_packed,
    sign_factor,
    signed_value,
    store_packed,
    table_bit,
)
from interpreter.hlasm.packed_field import PackedField
from interpreter.hlasm.packed_operands import packed_fields
from interpreter.hlasm.specification_check import emit_specification_check
from interpreter.hlasm.statement_lowering import StatementLowering
from interpreter.operator_kind import BinopKind
from interpreter.register import Register

ZONE = 0xF0
CHARACTER_ZONE = 0x30
TWO_BYTES = 2
LONGEST_ASCII_CODE = 31
LONGEST_UNICODE_CODE = 63
SIGN_INVALID_CC = 3

type LengthCheck = Callable[[HlasmEmitter, Register], None]


def _packed_operand(
    emitter: HlasmEmitter, statement: MachineStatement, width: int
) -> PackedField:
    address = effective_address(emitter, storage_operand(statement, SECOND_OPERAND))
    return PackedField(address, emitter.int_(width))


def _outside(emitter: HlasmEmitter, value: Register, bits: int) -> Register:
    return emitter.binop(BinopKind.NE, signed(bits)(emitter, value), value)


def _checked_value(
    emitter: HlasmEmitter, statement: MachineStatement, width: int
) -> Register:
    value = read_packed(emitter, _packed_operand(emitter, statement, width))
    emit_data_check(emitter, value.invalid(emitter))
    return signed_value(emitter, value)


def _to_binary(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    result = _checked_value(emitter, statement, DOUBLEWORD_BYTES)
    outside = _outside(emitter, result, WORD_BITS)
    to_gr32(emitter, statement, result)
    emit_fixed_point_divide_check(emitter, outside)


def _to_binary_long(emitter: HlasmEmitter, statement: MachineStatement) -> None:
    result = _checked_value(emitter, statement, QUADWORD_BYTES)
    emit_fixed_point_divide_check(emitter, _outside(emitter, result, DOUBLEWORD_BITS))
    to_gr64(emitter, statement, result)


def _to_decimal(source: Source, bits: int, width: int) -> StatementLowering:
    def lower(emitter: HlasmEmitter, statement: MachineStatement) -> None:
        value = signed(bits)(emitter, source(emitter, statement))
        negative = negative_bit(emitter, value)
        magnitude = emitter.binop(BinopKind.MUL, value, sign_factor(emitter, negative))
        store_packed(
            emitter, _packed_operand(emitter, statement, width), magnitude, negative
        )

    return lower


def _check_bytes(emitter: HlasmEmitter, code: Register) -> None:
    raised = emitter.binop(BinopKind.GT, code, emitter.int_(LONGEST_ASCII_CODE))
    emit_specification_check(emitter, raised)


def _check_pairs(emitter: HlasmEmitter, code: Register) -> None:
    even = emitter.binop(
        BinopKind.BIT_XOR,
        emitter.binop(BinopKind.BIT_AND, code, emitter.int_(1)),
        emitter.int_(1),
    )
    too_long = emitter.binop(BinopKind.GT, code, emitter.int_(LONGEST_UNICODE_CODE))
    emit_specification_check(emitter, emitter.binop(BinopKind.BIT_OR, too_long, even))


def _zone_sign(emitter: HlasmEmitter) -> SignOf:
    return lambda rightmost: emitter.binop(
        BinopKind.RSHIFT, rightmost, emitter.int_(NIBBLE_BITS)
    )


def _plus_sign(emitter: HlasmEmitter) -> SignOf:
    return lambda _: emitter.int_(PLUS_SIGN)


def _source(field: PackedField, emitter: HlasmEmitter, stride: int) -> DigitSource:
    last = emitter.binop(BinopKind.SUB, field.length, emitter.int_(ONE_BYTE))
    return DigitSource(field.address, last, stride)


def _pack(emitter: HlasmEmitter, statement: MachineStatement, field: DataField) -> None:
    target, source = packed_fields(emitter, statement, field)
    emit_pack(emitter, target, _source(source, emitter, ONE_BYTE), _zone_sign(emitter))


def _pack_characters(stride: int, check: LengthCheck) -> LowerWithField:
    def lower(
        emitter: HlasmEmitter, statement: MachineStatement, field: DataField
    ) -> None:
        code = field.value(emitter)
        check(emitter, code)
        source = length_operand_address(
            emitter, storage_length_operand(statement, SECOND_OPERAND)
        )
        target = effective_address(emitter, storage_operand(statement, FIRST_OPERAND))
        digits = DigitSource(source, code, stride)
        emit_pack(
            emitter,
            PackedField(target, emitter.int_(QUADWORD_BYTES)),
            digits,
            _plus_sign(emitter),
        )

    return lower


def _sign_into_zone(emitter: HlasmEmitter) -> SignOf:
    return lambda rightmost: emitter.binop(
        BinopKind.LSHIFT,
        emitter.binop(BinopKind.BIT_AND, rightmost, emitter.int_(NIBBLE_MASK)),
        emitter.int_(NIBBLE_BITS),
    )


def _unpack(
    emitter: HlasmEmitter, statement: MachineStatement, field: DataField
) -> None:
    target, source = packed_fields(emitter, statement, field)
    zoned = CharacterField(target.address, target.length, ONE_BYTE, ZONE)
    emit_unpack(emitter, zoned, source, _sign_into_zone(emitter))


def _sign_cc(emitter: HlasmEmitter, sign: Register) -> Register:
    minus = table_bit(emitter, emitter.int_(MINUS_SIGNS), sign)
    invalid = table_bit(emitter, emitter.int_(NOT_SIGNS), sign)
    return emitter.binop(
        BinopKind.ADD,
        minus,
        emitter.binop(BinopKind.MUL, invalid, emitter.int_(SIGN_INVALID_CC)),
    )


def _unpack_characters(width: int, check: LengthCheck) -> LowerWithField:
    def lower(
        emitter: HlasmEmitter, statement: MachineStatement, field: DataField
    ) -> None:
        code = field.value(emitter)
        check(emitter, code)
        target = length_operand_address(
            emitter, storage_length_operand(statement, FIRST_OPERAND)
        )
        length = emitter.binop(BinopKind.ADD, code, emitter.int_(ONE_BYTE))
        characters = CharacterField(target, length, width, CHARACTER_ZONE)
        zone = emitter.int_(CHARACTER_ZONE)
        sign = emit_unpack(
            emitter,
            characters,
            _packed_operand(emitter, statement, QUADWORD_BYTES),
            lambda _: zone,
        )
        emitter.set_cc(_sign_cc(emitter, sign))

    return lower


DECIMAL_CONVERSION_FIELD_LOWERINGS: Mapping[str, FieldLowering] = {
    "PACK": FieldLowering(LENGTH_NIBBLES, _pack),
    "UNPK": FieldLowering(LENGTH_NIBBLES, _unpack),
    "PKA": FieldLowering(SECOND_LENGTH_BYTE, _pack_characters(ONE_BYTE, _check_bytes)),
    "PKU": FieldLowering(SECOND_LENGTH_BYTE, _pack_characters(TWO_BYTES, _check_pairs)),
    "UNPKA": FieldLowering(LENGTH_BYTE, _unpack_characters(ONE_BYTE, _check_bytes)),
    "UNPKU": FieldLowering(LENGTH_BYTE, _unpack_characters(TWO_BYTES, _check_pairs)),
}

CONVERT_TO_DECIMAL = _to_decimal(from_gr32(FIRST_OPERAND), WORD_BITS, DOUBLEWORD_BYTES)

DECIMAL_CONVERSION_LOWERINGS: Mapping[str, StatementLowering] = {
    **written_lowerings(DECIMAL_CONVERSION_FIELD_LOWERINGS),
    "CVB": _to_binary,
    "CVBY": _to_binary,
    "CVBG": _to_binary_long,
    "CVD": CONVERT_TO_DECIMAL,
    "CVDY": CONVERT_TO_DECIMAL,
    "CVDG": _to_decimal(from_gr64(FIRST_OPERAND), DOUBLEWORD_BITS, QUADWORD_BYTES),
}
