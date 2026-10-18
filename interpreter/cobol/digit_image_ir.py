"""A numeric item's digit characters in IR: its digit image for a nonnumeric comparison, and its DISPLAY image."""

from __future__ import annotations

from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.cobol_constants import BuiltinName, ByteConstants
from interpreter.cobol.field_resolution import ResolvedFieldRef
from interpreter.cobol.ir_emitter import IrEmitter
from interpreter.cobol.ir_encoders import (
    build_decode_alphanumeric_ir,
    build_encode_zoned_ir,
)
from interpreter.register import Register


def emit_field_digit_image(
    e: IrEmitter, region_reg: Register, ref: ResolvedFieldRef
) -> Register:
    fl, offset_reg, extent = ref.fl, ref.offset_reg, ref.extent
    td = fl.type_descriptor
    if td.category == CobolDataCategory.ZONED_DECIMAL and not td.signed:
        return _with_scaling_zeros(
            e,
            e.ctx.emit_decode_zoned_display(
                region_reg, fl, offset_reg, extent=extent, span=e.span
            ),
            td.scale,
        )
    return emit_value_digit_image(
        e,
        e.ctx.emit_decode_field(region_reg, fl, offset_reg, extent=extent, span=e.span),
        td,
    )


def emit_value_digit_image(
    e: IrEmitter, value: Register, td: CobolTypeDescriptor
) -> Register:
    return _with_scaling_zeros(
        e,
        _digit_characters(e, value, td, e.int_(ByteConstants.SIGN_NIBBLE_UNSIGNED)),
        td.scale,
    )


def emit_display_image(
    e: IrEmitter, value: Register, td: CobolTypeDescriptor
) -> Register:
    sign = e.call(BuiltinName.COBOL_PREPARE_SIGN, value, e.bool_(True))
    zone = e.choose(
        "display_zone",
        e.int_(ByteConstants.SIGN_NIBBLE_UNSIGNED),
        e.binop("!=", sign, e.int_(ByteConstants.SIGN_NIBBLE_NEGATIVE)),
        lambda: sign,
    )
    return _digit_characters(e, value, td, zone)


def _digit_characters(
    e: IrEmitter, value: Register, td: CobolTypeDescriptor, sign_nibble: Register
) -> Register:
    digits = e.call(
        BuiltinName.COBOL_PREPARE_DIGITS,
        value,
        e.int_(td.total_digits),
        e.int_(td.decimal_digits),
        e.bool_(False),
        e.int_(td.scale),
    )
    zoned = e.ctx.inline_ir(
        build_encode_zoned_ir("enc_digit_image", td.total_digits),
        {"%p_digits": digits, "%p_sign_nibble": sign_nibble},
        span=e.span,
    )
    return e.ctx.inline_ir(
        build_decode_alphanumeric_ir("dec_digit_image"),
        {"%p_data": zoned},
        span=e.span,
    )


def _with_scaling_zeros(e: IrEmitter, stored: Register, scale: int) -> Register:
    if scale <= 0:
        return stored
    return e.call(BuiltinName.STRING_CONCAT_PAIR, stored, e.text("0" * scale))
