"""COBOL numeric edit-picture formatting.

Applies COBOL numeric editing rules when a numeric value is MOVEd into a
numeric-edited receiving item (e.g. ``PIC +99999999.99``, ``+ZZZ,ZZZ,ZZZ.99``,
``Z(9).99-``). This is the software analogue of GnuCOBOL's ``cob_move_edited``
(libcob) and IBM's hardware ``ED``/``EDMK`` instructions: a precompiled edit
mask is applied to the numeric source at runtime.

Supported edit constructs (the subset used by AWS CardDemo):
  - Fixed sign insertion: leading or trailing ``+`` / ``-``
  - Zero suppression: ``Z`` (leading zeros -> spaces; commas in the suppressed
    zone -> spaces; suppression stops at the first significant digit or the
    decimal point)
  - Simple insertion: ``,`` (comma) and ``.`` (decimal point)
  - Digit positions: ``9`` (always shown) and ``Z`` (suppressible)

NOT supported (absent from CardDemo): floating sign / currency (``$$$``,
``++++``, ``----``), ``*`` check protection, ``CR`` / ``DB``, ``B`` / ``0`` /
``/`` insertion, ``P`` scaling.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# Picture symbols that mark a position as numeric-edited (vs. plain numeric /
# alphanumeric). The presence of any of these — or an actual '.' decimal point —
# makes the PIC a numeric-edited item.
_SIGN_SYMS = frozenset("+-")
_EDIT_SYMS = frozenset("Z+-,.")


def _expand(pic: str) -> list[str]:
    """Expand a PIC string into a flat list of per-character position symbols.

    ``(N)`` repeats the immediately preceding symbol N times, e.g.
    ``Z(9)`` -> nine ``'Z'`` entries, ``+ZZZ,ZZZ,ZZZ.99`` -> the 15 single
    characters in declaration order. The count is read structurally.
    """
    out: list[str] = []
    i = 0
    while i < len(pic):
        ch = pic[i]
        if ch == "(":
            j = pic.index(")", i)
            count = int(pic[i + 1 : j])
            if not out:
                raise ValueError(f"PIC repeat count with no preceding symbol: {pic!r}")
            prev = out[-1]
            out.extend([prev] * (count - 1))
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return out


def is_numeric_edited(pic: str) -> bool:
    """Return True if ``pic`` is a numeric-edited picture.

    A picture is numeric-edited when it contains digit positions and at least
    one editing symbol (sign, Z suppression, comma, or an actual decimal point),
    but no alphanumeric ``X``/``A`` positions. ``V`` is an *implied* decimal
    point (plain numeric), not an editing symbol, so ``S9(5)V99`` is not edited.
    """
    upper = pic.upper()
    if "X" in upper or "A" in upper:
        return False
    has_digit = "9" in upper or "Z" in upper
    if not has_digit:
        return False
    return any(c in _EDIT_SYMS for c in upper)


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
        all_suppressible: True if every digit position is Z (no '9').
    """

    template: tuple[str, ...]
    width: int
    int_digits: int
    frac_digits: int
    signed: bool
    sign_symbol: str
    sign_leading: bool
    all_suppressible: bool


def parse_edit_picture(pic: str) -> EditPicture:
    """Parse a numeric-edited PIC string into an :class:`EditPicture`."""
    template = _expand(pic.upper())

    seen_decimal = False
    int_digits = 0
    frac_digits = 0
    has_nine = False
    for sym in template:
        if sym == ".":
            seen_decimal = True
        elif sym in ("9", "Z"):
            if seen_decimal:
                frac_digits += 1
            else:
                int_digits += 1
            if sym == "9":
                has_nine = True

    sign_symbol = ""
    sign_leading = True
    if template and template[0] in _SIGN_SYMS:
        sign_symbol = template[0]
        sign_leading = True
    elif template and template[-1] in _SIGN_SYMS:
        sign_symbol = template[-1]
        sign_leading = False

    return EditPicture(
        template=tuple(template),
        width=len(template),
        int_digits=int_digits,
        frac_digits=frac_digits,
        signed=bool(sign_symbol),
        sign_symbol=sign_symbol,
        sign_leading=sign_leading,
        all_suppressible=not has_nine and (int_digits + frac_digits) > 0,
    )


def _digit_strings(value: Decimal, ep: EditPicture) -> tuple[str, str]:
    """Return (integer_digits, fraction_digits) zero-padded/truncated to the
    picture's digit-position counts. Truncates toward zero (no ROUNDED)."""
    magnitude = abs(value)
    # Scale to an integer holding all fractional digit positions, truncating
    # any excess fraction (COBOL truncates unless ROUNDED is specified).
    scaled = int(magnitude * (10**ep.frac_digits))
    all_digits = str(scaled)
    # Split off the fractional positions from the right.
    if ep.frac_digits:
        frac_part = all_digits[-ep.frac_digits :].rjust(ep.frac_digits, "0")
        int_part = all_digits[: -ep.frac_digits]
    else:
        frac_part = ""
        int_part = all_digits
    # Pad / truncate the integer part to the picture's positions (low-order
    # digits win on overflow, mirroring COBOL high-order truncation).
    if ep.int_digits:
        int_part = int_part.rjust(ep.int_digits, "0")[-ep.int_digits :]
    else:
        int_part = ""
    return int_part, frac_part


def format_edited(value: str, pic: str) -> str:
    """Format a numeric ``value`` string per the numeric-edited ``pic``.

    ``value`` is a decimal string such as ``"123.45"``, ``"-0.5"``, ``"0"``.
    Returns the edited display string, exactly ``width`` characters wide.
    """
    ep = parse_edit_picture(pic)
    try:
        dec = Decimal(str(value).strip() or "0")
    except (InvalidOperation, ValueError):
        dec = Decimal(0)

    negative = dec < 0
    is_zero = dec == 0

    # All-Z picture with a zero value: the entire item (including the decimal
    # point, commas, and a fixed sign) is blanked (IBM zero-suppression rule).
    if ep.all_suppressible and is_zero:
        return " " * ep.width

    int_part, frac_part = _digit_strings(dec, ep)

    out: list[str] = []
    suppressing = True  # within the leading-zero zone (left of decimal only)
    int_idx = 0
    frac_idx = 0
    past_decimal = False

    for sym in ep.template:
        if sym in _SIGN_SYMS:
            out.append(_sign_char(sym, negative))
        elif sym == "9":
            if past_decimal:
                out.append(frac_part[frac_idx])
                frac_idx += 1
            else:
                out.append(int_part[int_idx])
                int_idx += 1
                suppressing = False
        elif sym == "Z":
            if past_decimal:
                # value is non-zero here (all-zero handled above); show digit.
                out.append(frac_part[frac_idx])
                frac_idx += 1
            else:
                digit = int_part[int_idx]
                int_idx += 1
                if suppressing and digit == "0":
                    out.append(" ")
                else:
                    suppressing = False
                    out.append(digit)
        elif sym == ",":
            out.append(" " if suppressing else ",")
        elif sym == ".":
            out.append(".")
            past_decimal = True
            suppressing = False
        else:
            # Unsupported symbol — emit verbatim so the failure is visible.
            out.append(sym)

    return "".join(out)


def _sign_char(symbol: str, negative: bool) -> str:
    """Resolve a fixed sign symbol to its emitted character.

    '+' shows '+' for non-negative, '-' for negative.
    '-' shows ' ' for non-negative, '-' for negative.
    """
    if symbol == "+":
        return "-" if negative else "+"
    return "-" if negative else " "
