"""COBOL edit-picture formatting.

Applies COBOL editing rules when a value is MOVEd into an edited receiving item.
Two categories are edited: numeric-edited (e.g. ``PIC +99999999.99``,
``+ZZZ,ZZZ,ZZZ.99``, ``Z(9).99-``), handled by :func:`format_edited`, and
alphanumeric-edited (e.g. ``PIC XXBXXBXX``, ``XX/XX/XXXX``), handled by
:func:`format_alphanumeric_edited`. This is the software analogue of GnuCOBOL's
``cob_move_edited`` (libcob) and IBM's hardware ``ED``/``EDMK`` instructions: a
precompiled edit mask is applied to the source at runtime.

The numeric rules are the intricate ones and are what the rest of this docstring
describes; alphanumeric editing is only insertion, with no suppression, sign or
scaling to reason about.

Supported edit constructs:
  - Digit positions: ``9`` (always shown), ``Z`` (suppressible), ``*``
    (suppressible, filled with ``*``)
  - Fixed sign insertion: leading or trailing ``+`` / ``-``
  - Floating insertion: ``$$$``, ``++++``, ``----`` — a run of N of the same
    symbol is N-1 digit positions plus one reserved slot, and the symbol is
    emitted immediately left of the first significant digit
  - Check protection: ``*`` (leading zeros -> ``*``)
  - Trailing sign: ``CR`` / ``DB``, emitted only when the value is negative
  - Simple insertion: ``,`` ``.`` ``B`` ``0`` ``/``

``P`` positions occupy no width; the scaling they denote reaches
:func:`format_edited` as its ``scale`` argument. Still NOT supported: the
``DECIMAL-POINT IS COMMA`` clause, so ``.`` is hardcoded.

Two rules here are counter-intuitive and are taken from the NIST-85
conformance suite rather than from a reading of the standard — see
tests/unit/cobol/test_edit_picture_nist.py, which asserts the standard's own
expected values:

  - A zero value blanks the ENTIRE item only when every digit position is
    suppressible. ``"ZZ.ZZ"`` -> five spaces, decimal point included. But
    check protection is the exception: ``"**.**"`` -> ``'**.**'`` and
    ``"*,***.**"`` -> ``'*****.**'`` — the comma becomes ``*`` while the
    DECIMAL POINT SURVIVES.
  - A floating string may have ``,`` and ``.`` interspersed, so ``"$$,$$$.$$"``
    is ONE floating string of seven ``$`` (six digit positions), not three
    adjacent runs. That is what makes it render ``'$1,234.00'``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import takewhile

from cobol_asg.edit_picture_shape import EditPicture
from cobol_asg.edit_render import EditRender
from cobol_numeric.number import (
    CobolNumber,
    digits_for_encode,
    from_digits,
    from_literal,
    scale_by,
)

_SIGN_SYMS = frozenset("+-")
_SIMPLE_INSERTIONS = frozenset(",B0/")

# The default currency symbol. A program may replace it via
# SPECIAL-NAMES CURRENCY SIGN IS <literal> (red-dragon-3o5f), so every entry
# point takes a `currency` parameter defaulting to this.
DEFAULT_CURRENCY = "$"


def _float_syms(currency: str) -> tuple[str, ...]:
    """Edit symbols that can FLOAT, in deterministic precedence order.

    A run of two or more is a floating insertion (n-1 digit positions plus one
    reserved symbol slot); a run of exactly ONE is fixed insertion.

    Ordered, not a set: iteration order decides which symbol wins when a
    picture somehow contains runs of two different float symbols, and a
    frozenset would make that arbitrary between runs.
    """
    return (currency, "+", "-")


# Trailing two-character sign tokens. Valid only as the last two positions.
_TRAILING_SIGN_TOKENS = ("CR", "DB")


class UnsupportedEditPictureError(ValueError):
    """A picture RedDragon cannot store or format (red-dragon-0599).

    Raised by ``parse_pic`` for a picture whose category the runtime has no
    representation for. Subclasses ValueError because ``parse_pic`` has always
    raised ValueError for unparseable pictures; existing ``except ValueError``
    handling keeps working while callers that care can catch this precisely.

    The symbol-scan guard this class was introduced for (floating currency/sign,
    ``*`` check protection, ``CR``/``DB``) is gone: red-dragon-5f4g implemented
    all of them, and the PICTURE grammar now decides the category, so the refusal
    is expressed per category in ``pic_parser`` instead of per symbol here.
    """


def find_float_string(
    template: list[str] | tuple[str, ...],
    currency: str = DEFAULT_CURRENCY,
) -> tuple[str, tuple[int, ...]]:
    """Locate the floating insertion string in an expanded template.

    A floating string is a run of TWO OR MORE of the same float symbol
    (``$``, ``+``, ``-``) which may have simple insertion characters (``,``
    and ``.``) interspersed. ``"$$,$$$.$$"`` is therefore ONE floating string
    of seven ``$``, not three adjacent runs — which is what lets it render
    ``'$1,234.00'`` with four integer digit positions.

    A run of exactly ONE is FIXED insertion (``"$ZZZ,ZZZ.99"``,
    ``"+99999999.99"``) and is deliberately not matched here: the fixed-sign
    and verbatim paths already handle those correctly.

    Returns ``(symbol, positions)`` where positions are the template indices
    of the float symbols in order, or ``("", ())`` if there is none.
    """
    for sym in _float_syms(currency):
        idxs = tuple(i for i, t in enumerate(template) if t == sym)
        if len(idxs) < 2:
            continue
        span = template[idxs[0] : idxs[-1] + 1]
        if all(c == sym or c in ",." for c in span):
            return sym, idxs
    return "", ()


def _trailing_sign_token(template: list[str] | tuple[str, ...]) -> str:
    """Return 'CR'/'DB' if the template ends with that two-character token.

    Must be read as ONE token before per-character dispatch: the ``B`` of
    ``DB`` would otherwise be consumed by the ``B`` blank-insertion branch
    (added by red-dragon-r9s9) and the field would render ``'D '``.
    """
    if len(template) >= 2:
        tail = "".join(template[-2:])
        if tail in _TRAILING_SIGN_TOKENS:
            return tail
    return ""


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


_DATA_POSITIONS = frozenset("AX9")

# B emits a space; 0 and / emit themselves. "The insertion characters are counted
# in the size of the item" (Table 12) — every position here is one byte.
_ALPHANUMERIC_INSERTIONS = {"B": " ", "0": "0", "/": "/"}


def format_alphanumeric_edited(
    value: str, pic: str, justified_right: bool = False
) -> str:
    """Place ``value``'s characters into the ``pic``'s A / X / 9 positions.

    An alphanumeric-edited receiving item takes its sender as alphanumeric: the
    characters fill the data positions left to right, space-filled if the sender
    is shorter and truncated on the right if it is longer, while every B / 0 /
    '/' position emits its insertion character. JUSTIFIED RIGHT reverses which
    end is filled and which is truncated (LR p. 407, and "JUSTIFIED clause",
    p. 189). Returns exactly the picture's character-position count.
    """
    template = _expand(pic.upper())
    slots = sum(1 for sym in template if sym in _DATA_POSITIONS)
    chars = str(value)
    if justified_right:
        chars = chars[max(len(chars) - slots, 0) :].rjust(slots)
    else:
        chars = chars[:slots].ljust(slots)

    out: list[str] = []
    taken = 0
    for sym in template:
        if sym in _DATA_POSITIONS:
            out.append(chars[taken])
            taken += 1
        else:
            out.append(_ALPHANUMERIC_INSERTIONS.get(sym, sym))
    return "".join(out)


def parse_edit_picture(pic: str, currency: str = DEFAULT_CURRENCY) -> EditPicture:
    """Parse a numeric-edited PIC string into an :class:`EditPicture`."""
    # S (operational sign), V (implied decimal point) and P (decimal scaling)
    # occupy NO storage, so they are dropped before anything downstream sees
    # the template: width is len(template), and width is the record byte
    # length. Keeping them made 'PIC ZZZPP' 5 bytes here while the bridge —
    # which excludes S/V/P by its uniform rule — allocated 3, so Python read
    # two bytes into the following field (red-dragon-ilb6 follow-up).
    template = [sym for sym in _expand(pic.upper()) if sym not in "SVP"]
    float_symbol, float_positions = find_float_string(template, currency)
    trailing_sign = _trailing_sign_token(template)
    # The first float position is reserved for the symbol itself, not a digit.
    float_digit_positions = frozenset(float_positions[1:])

    seen_decimal = False
    int_digits = 0
    frac_digits = 0
    has_nine = False
    for index, sym in enumerate(template):
        if sym == ".":
            seen_decimal = True
            continue
        # '*' and the non-reserved float positions are digit positions exactly
        # as Z is — they are suppressible digits with a different fill/emission.
        is_digit = sym in ("9", "Z", "*") or index in float_digit_positions
        if not is_digit:
            continue
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
    # A floating sign is emitted by the float machinery, not the fixed-sign
    # path — otherwise "----9" would emit a sign at position 0 as well.
    if float_symbol in _SIGN_SYMS:
        sign_symbol = ""

    return EditPicture(
        template=tuple(template),
        width=len(template),
        int_digits=int_digits,
        frac_digits=frac_digits,
        signed=bool(sign_symbol)
        or bool(float_symbol in _SIGN_SYMS)
        or bool(trailing_sign),
        sign_symbol=sign_symbol,
        sign_leading=sign_leading,
        all_suppressible=not has_nine and (int_digits + frac_digits) > 0,
        fill_char="*" if "*" in template else " ",
        float_symbol=float_symbol,
        float_positions=float_positions,
        trailing_sign=trailing_sign,
    )


def _digit_string(value: CobolNumber, ep: EditPicture) -> str:
    """The picture's digits, zero-padded/truncated to its digit-position counts.
    Truncates toward zero (no ROUNDED); on overflow the low-order integer digits
    win (COBOL high-order truncation)."""
    _, digits = digits_for_encode(value, ep.int_digits + ep.frac_digits, ep.frac_digits)
    return digits


def format_edited(
    value: str, pic: str, currency: str = DEFAULT_CURRENCY, scale: int = 0
) -> str:
    """Format a numeric ``value`` string per the numeric-edited ``pic``.

    ``value`` is a decimal string such as ``"123.45"``, ``"-0.5"``, ``"0"``.
    ``scale`` is the picture's P scaling: the edited digits are the value
    divided by ``10**scale``.
    Returns the edited display string, exactly ``width`` characters wide.
    """
    ep = parse_edit_picture(pic, currency)
    dec = _edited_value(value, scale)
    if ep.all_suppressible and dec == 0:
        return _zero_image(ep)
    body = ep.template[:-2] if ep.trailing_sign else ep.template
    digits = _position_digits(ep, body, _digit_string(dec, ep))
    render = EditRender(
        picture=ep,
        body=body,
        digits=digits,
        float_slot=_float_slot(ep, digits),
        negative=dec < 0,
    )
    return render.image() + _trailing_sign_image(ep, dec < 0)


def _edited_value(value: str, scale: int) -> CobolNumber:
    try:
        return scale_by(from_literal(str(value).strip() or "0"), -scale)
    except ValueError:
        return from_digits(0, 0)


def _zero_image(ep: EditPicture) -> str:
    """Every digit position suppressible and the value zero: the whole item is
    blanked (IBM zero-suppression rule). Check protection is the exception: '*'
    FILLS rather than blanks, and the decimal point SURVIVES (NIST-85 NC124A)."""
    if ep.fill_char == "*":
        return "".join("." if sym == "." else "*" for sym in ep.template)
    return " " * ep.width


def _position_digits(
    ep: EditPicture, body: Sequence[str], digits: str
) -> Mapping[int, str]:
    float_digits = frozenset(ep.float_positions[1:])
    positions = [
        index
        for index, sym in enumerate(body)
        if sym in ("9", "Z", "*") or index in float_digits
    ]
    return dict(zip(positions, digits, strict=True))


def _trailing_sign_image(ep: EditPicture, negative: bool) -> str:
    if not ep.trailing_sign:
        return ""
    return ep.trailing_sign if negative else "  "


def _float_slot(ep: EditPicture, digits: Mapping[int, str]) -> int:
    """Return the template index where the floating symbol is emitted.

    The symbol sits immediately to the LEFT of the first significant integer
    digit when that digit is in the floating string. Otherwise it takes the
    floating string's rightmost position, and "any simple-insertion symbols
    (B 0 / ,) within or to the immediate right of the string of floating
    insertion symbols are considered part of the floating character-string"
    (IBM LR, "Floating insertion editing"): "$$$,999.99" holding 987.65 is
    "   $987.65" (NIST-85 NC105A). Returns -1 when there is no floating string.
    """
    if not ep.float_symbol:
        return -1
    point = ep.template.index(".") if "." in ep.template else len(ep.template)
    first = next(
        (i for i, digit in sorted(digits.items()) if i < point and digit != "0"), -1
    )
    if first in ep.float_positions[1:]:
        return first - 1
    return _float_string_end(ep, point)


def _float_string_end(ep: EditPicture, point: int) -> int:
    before_point = [p for p in ep.float_positions if p < point]
    last = before_point[-1] if before_point else ep.float_positions[-1]
    trailing = takewhile(lambda sym: sym in _SIMPLE_INSERTIONS, ep.template[last + 1 :])
    return last + len(tuple(trailing))


_DE_EDIT_DIGITS = frozenset("9Z*P")
_POINT_SYMBOLS = frozenset(".V")
_NEGATIVE_MARKS = frozenset({("+", "-"), ("-", "-"), ("C", "C"), ("D", "D")})


def _de_edit_cells(image: str, template: Sequence[str]) -> tuple[tuple[str, str], ...]:
    stored = iter(image.ljust(len(template)))
    return tuple(
        (sym, "0" if sym == "P" else "" if sym == "V" else next(stored))
        for sym in template
    )


def _integer_digit_count(cells: tuple[tuple[str, str], ...], digit_syms: str) -> int:
    symbols = [sym for sym, _ in cells]
    point = next(
        (i for i, sym in enumerate(symbols) if sym in _POINT_SYMBOLS), len(symbols)
    )
    leading_p = next((sym for sym in symbols if sym in digit_syms), "") == "P"
    integer_end = 0 if point == len(symbols) and leading_p else point
    return sum(1 for sym in symbols[:integer_end] if sym in digit_syms)


def de_edit(image: str, pic: str, currency: str = DEFAULT_CURRENCY) -> CobolNumber:
    """The numeric value a numeric-edited ``image`` of ``pic`` represents.

    De-editing (ANSI X3.23-1985 MOVE; IBM Enterprise COBOL LR, "Elementary
    moves"): each digit position contributes its digit, a suppressed or
    check-protected one contributes zero, insertion characters are dropped, and
    the value is negative when a sign position shows '-' or CR / DB is present.
    """
    template = [sym for sym in _expand(pic.upper()) if sym != "S"]
    float_symbol, _ = find_float_string(template, currency)
    digit_syms = "".join(_DE_EDIT_DIGITS) + float_symbol
    cells = _de_edit_cells(image, template)
    digits = "".join(
        char if char.isdigit() else "0" for sym, char in cells if sym in digit_syms
    )
    negative = any(cell in _NEGATIVE_MARKS for cell in cells)
    magnitude = int(digits or "0")
    return from_digits(
        -magnitude if negative else magnitude,
        len(digits) - _integer_digit_count(cells, digit_syms),
    )
