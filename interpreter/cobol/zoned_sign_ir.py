"""A signed zoned item's characters as INSPECT sees them: the operational sign taken out of its bytes and put back, in IR."""

from __future__ import annotations

from cobol_asg.cobol_types import CobolDataCategory
from cobol_memory.field_extent import FieldExtent
from interpreter.cobol.cobol_constants import BuiltinName, NibblePosition
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.ir_encoders import (
    build_decode_alphanumeric_ir,
    build_encode_alphanumeric_ir,
)
from interpreter.register import Register

_DIGIT_ZONE = 0xF
_LOWEST_SIGN_ZONE = 0xA
_HIGHEST_DIGIT = 9


def sign_index(fl: FieldLayout) -> int:
    return 0 if fl.type_descriptor.sign_leading else fl.byte_length - 1


def emit_inspected_characters(
    e: IrEmitter,
    region_reg: Register,
    fl: FieldLayout,
    offset_reg: Register,
    extent: FieldExtent,
) -> Register:
    ctx = e.ctx
    td = fl.type_descriptor
    if not (td.category == CobolDataCategory.ZONED_DECIMAL and td.signed):
        return ctx.emit_decode_field_characters(
            region_reg, fl, offset_reg, extent=extent, span=e.span
        )
    stored = ctx.emit_load_field_bytes(
        region_reg, fl, offset_reg, extent=extent, span=e.span
    )
    digits = emit_strip_sign(e, stored, sign_index(fl), td.sign_separate)
    return ctx.inline_ir(
        build_decode_alphanumeric_ir(f"dec_inspected_{fl.name}"),
        {"%p_data": digits},
        span=e.span,
    )


def emit_write_inspected_characters(
    e: IrEmitter,
    region_reg: Register,
    fl: FieldLayout,
    value_str_reg: Register,
    offset_reg: Register,
    extent: FieldExtent,
) -> None:
    ctx = e.ctx
    td = fl.type_descriptor
    if not (td.category == CobolDataCategory.ZONED_DECIMAL and td.signed):
        ctx.emit_encode_and_write(
            region_reg, fl, value_str_reg, offset_reg, extent=extent, span=e.span
        )
        return
    digits = ctx.inline_ir(
        build_encode_alphanumeric_ir(f"enc_inspected_{fl.name}", td.total_digits),
        {"%p_value": value_str_reg},
        span=e.span,
    )
    original = ctx.emit_load_field_bytes(
        region_reg, fl, offset_reg, extent=extent, span=e.span
    )
    signed = emit_restore_sign(e, digits, original, sign_index(fl), td.sign_separate)
    ctx.emit_write_field_bytes(
        region_reg, fl, signed, offset_reg, extent=extent, span=e.span
    )


def emit_strip_sign(
    e: IrEmitter, stored: Register, index: int, separate: bool
) -> Register:
    if separate:
        return e.call(
            BuiltinName.LIST_CONCAT,
            e.call(BuiltinName.LIST_SLICE, stored, e.int_(0), e.int_(index)),
            e.call(
                BuiltinName.LIST_SLICE,
                stored,
                e.int_(index + 1),
                e.call(BuiltinName.LIST_LEN, stored),
            ),
        )
    byte = e.call(BuiltinName.LIST_GET, stored, e.int_(index))
    unzoned = e.choose(
        "unzoned_sign",
        byte,
        e.binop("==", _is_sign_zoned_digit(e, byte), e.bool_(False)),
        lambda: _with_zone(e, byte, e.int_(_DIGIT_ZONE)),
    )
    return e.call(BuiltinName.LIST_SET, stored, e.int_(index), unzoned)


def emit_restore_sign(
    e: IrEmitter, digits: Register, original: Register, index: int, separate: bool
) -> Register:
    sign_byte = e.call(BuiltinName.LIST_GET, original, e.int_(index))
    if separate:
        return e.call(
            BuiltinName.LIST_CONCAT,
            e.call(
                BuiltinName.LIST_CONCAT,
                e.call(BuiltinName.LIST_SLICE, digits, e.int_(0), e.int_(index)),
                e.call(BuiltinName.MAKE_LIST, e.int_(1), sign_byte),
            ),
            e.call(
                BuiltinName.LIST_SLICE,
                digits,
                e.int_(index),
                e.call(BuiltinName.LIST_LEN, digits),
            ),
        )
    byte = e.call(BuiltinName.LIST_GET, digits, e.int_(index))
    rezone = e.binop(
        "and", _is_unsigned_digit(e, byte), _is_sign_zoned_digit(e, sign_byte)
    )
    rezoned = e.choose(
        "rezoned_sign",
        byte,
        e.binop("==", rezone, e.bool_(False)),
        lambda: _with_zone(e, byte, _nibble(e, sign_byte, NibblePosition.HIGH)),
    )
    return e.call(BuiltinName.LIST_SET, digits, e.int_(index), rezoned)


def _nibble(e: IrEmitter, byte: Register, position: NibblePosition) -> Register:
    return e.call(BuiltinName.NIBBLE_GET, byte, e.text(position.value))


def _with_zone(e: IrEmitter, byte: Register, zone: Register) -> Register:
    return e.call(BuiltinName.NIBBLE_SET, byte, e.text(NibblePosition.HIGH.value), zone)


def _low_is_digit(e: IrEmitter, byte: Register) -> Register:
    return e.binop("<=", _nibble(e, byte, NibblePosition.LOW), e.int_(_HIGHEST_DIGIT))


def _is_sign_zoned_digit(e: IrEmitter, byte: Register) -> Register:
    return e.binop(
        "and",
        e.binop(">=", _nibble(e, byte, NibblePosition.HIGH), e.int_(_LOWEST_SIGN_ZONE)),
        _low_is_digit(e, byte),
    )


def _is_unsigned_digit(e: IrEmitter, byte: Register) -> Register:
    return e.binop(
        "and",
        e.binop("==", _nibble(e, byte, NibblePosition.HIGH), e.int_(_DIGIT_ZONE)),
        _low_is_digit(e, byte),
    )
