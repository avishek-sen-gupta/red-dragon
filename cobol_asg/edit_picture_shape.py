"""A parsed numeric edit picture: positions, digit counts, sign and float facts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EditPicture:
    """A parsed numeric edit picture.

    Attributes:
        template: the expanded per-character position symbols.
        width: total character width (== storage byte length).
        int_digits: number of digit positions (9/Z) left of the decimal point.
        frac_digits: number of digit positions (9/Z) right of the decimal point.
        signed: whether the picture carries a sign symbol (+/-).
        sign_symbol: the sign symbol ('+' or '-'), or '' if unsigned.
        sign_leading: True if the sign is at the start, False if trailing.
        all_suppressible: True if every digit position is suppressible (no '9').
        fill_char: the character leading suppressed zeros become — ' ' for Z
            suppression, '*' for check protection.
        float_symbol: the floating insertion symbol ('$', '+', '-'), or ''.
        float_positions: template indices of the float symbols, in order. The
            FIRST is the reserved slot for the symbol itself; the rest are
            suppressible digit positions. So N float symbols give N-1 digits.
        trailing_sign: 'CR' / 'DB' if the picture ends with one, else ''.
    """

    template: tuple[str, ...]
    width: int
    int_digits: int
    frac_digits: int
    signed: bool
    sign_symbol: str
    sign_leading: bool
    all_suppressible: bool
    fill_char: str = " "
    float_symbol: str = ""
    float_positions: tuple[int, ...] = ()
    trailing_sign: str = ""
