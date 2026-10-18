"""A signed zoned item's characters as INSPECT sees them: the operational sign taken out of its bytes and put back, in IR."""

from __future__ import annotations

from cobol_asg.cobol_types import CobolDataCategory
from interpreter.cobol.cobol_constants import BuiltinName, NibblePosition
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.ir_encoders import (
    build_decode_alphanumeric_ir,
    build_encode_alphanumeric_ir,
)
from interpreter.cobol.sign_position import SignPosition
from interpreter.register import Register

_DIGIT_ZONE = 0xF
_LOWEST_SIGN_ZONE = 0xA
_HIGHEST_DIGIT = 9


def sign_position(fl: FieldLayout) -> SignPosition:
    td = fl.type_descriptor
    return SignPosition(
        index=0 if td.sign_leading else fl.byte_length - 1,
        separate=td.sign_separate,
    )


def emit_inspected_characters(
    e: IrEmitter, region_reg: Register, ref: ResolvedFieldRef
) -> Register:
    ctx = e.ctx
    fl = ref.fl
    td = fl.type_descriptor
    if not (td.category == CobolDataCategory.ZONED_DECIMAL and td.signed):
        return ctx.emit_decode_field_characters(
            region_reg, fl, ref.offset_reg, extent=ref.extent, span=e.span
        )
    stored = ctx.emit_load_field_bytes(region_reg, ref, span=e.span)
    digits = emit_strip_sign(e, stored, sign_position(fl))
    return ctx.inline_ir(
        build_decode_alphanumeric_ir(f"dec_inspected_{fl.name}"),
        {"%p_data": digits},
        span=e.span,
    )


def emit_write_inspected_characters(
    e: IrEmitter, region_reg: Register, ref: ResolvedFieldRef, value_str_reg: Register
) -> None:
    ctx = e.ctx
    fl = ref.fl
    td = fl.type_descriptor
    if not (td.category == CobolDataCategory.ZONED_DECIMAL and td.signed):
        ctx.emit_encode_and_write(
            region_reg,
            fl,
            value_str_reg,
            ref.offset_reg,
            extent=ref.extent,
            span=e.span,
        )
        return
    digits = ctx.inline_ir(
        build_encode_alphanumeric_ir(f"enc_inspected_{fl.name}", td.total_digits),
        {"%p_value": value_str_reg},
        span=e.span,
    )
    original = ctx.emit_load_field_bytes(region_reg, ref, span=e.span)
    signed = emit_restore_sign(e, digits, original, sign_position(fl))
    ctx.emit_write_field_bytes(region_reg, ref, signed, span=e.span)


def emit_strip_sign(e: IrEmitter, stored: Register, sign: SignPosition) -> Register:
    index = sign.index
    if sign.separate:
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
    e: IrEmitter, digits: Register, original: Register, sign: SignPosition
) -> Register:
    index = sign.index
    sign_byte = e.call(BuiltinName.LIST_GET, original, e.int_(index))
    if sign.separate:
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
