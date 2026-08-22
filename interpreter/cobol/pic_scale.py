"""PIC P decimal scaling arithmetic (red-dragon-qhtv).

P positions occupy no storage but shift the assumed decimal point. The stored
digits are therefore the value divided by the scaling factor; reading the field
multiplies back. Both directions live here so the encode path (emit_context)
and the edit-picture formatter (edit_picture) share one implementation.
"""

from __future__ import annotations

from decimal import Decimal

from interpreter.cobol.cobol_types import CobolTypeDescriptor
from interpreter.cobol.data_filters import align_decimal, left_adjust


def descale(value: Decimal, scale: int) -> Decimal:
    """Value -> the number the digit positions actually hold.

    There is deliberately no `rescale` counterpart: decoding happens in emitted
    IR (a Binop multiply in emit_decode_field), not in Python, so a Python-side
    inverse would have no caller.
    """
    return value / (Decimal(10) ** scale) if scale else value


def encode_scaled_digits(value: str, td: CobolTypeDescriptor) -> str:
    """Return the digit characters stored for `value` in a field of type `td`.

    Divides by the scaling factor BEFORE truncating to the field's digit
    positions — order matters. 12300 into PIC 999PP is 123, not 300: dividing
    first keeps the significant digits, whereas truncating first keeps the
    low-order ones.
    """
    clean = value.lstrip("+-")
    if td.scale:
        scaled = descale(Decimal(clean), td.scale)
        # Truncate toward zero: COBOL does not round unless ROUNDED is given.
        # `format(scaled, "f")` is required (not `str(scaled)`): dividing by a
        # power of ten can push Decimal into scientific notation (e.g.
        # '1.2E+5'), which `align_decimal` cannot parse — it splits on '.',
        # finds one inside the mantissa, and silently corrupts the exponent
        # digits. Plain fixed-point avoids that entirely.
        clean = str(int(scaled)) if td.decimal_digits == 0 else format(scaled, "f")
    integer_digits = td.total_digits - td.decimal_digits
    if td.decimal_digits > 0:
        return align_decimal(clean, integer_digits, td.decimal_digits)
    return left_adjust(clean.replace(".", ""), td.total_digits)
