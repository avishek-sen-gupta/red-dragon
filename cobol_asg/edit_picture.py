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

Still NOT supported: ``P`` scaling semantics (``P`` positions are correctly
excluded from the byte width, but the implied decimal-point shift they denote
is not applied to the value), and the ``CURRENCY SIGN IS`` /
``DECIMAL-POINT IS COMMA`` clauses (red-dragon-3o5f), so ``$`` and ``.`` are
hardcoded.

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

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_SIGN_SYMS = frozenset("+-")

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


def format_edited(value: str, pic: str, currency: str = DEFAULT_CURRENCY) -> str:
    """Format a numeric ``value`` string per the numeric-edited ``pic``.

    ``value`` is a decimal string such as ``"123.45"``, ``"-0.5"``, ``"0"``.
    Returns the edited display string, exactly ``width`` characters wide.
    """
    ep = parse_edit_picture(pic, currency)
    try:
        dec = Decimal(str(value).strip() or "0")
    except (InvalidOperation, ValueError):
        dec = Decimal(0)

    negative = dec < 0
    is_zero = dec == 0

    # Every digit position suppressible and the value zero: the whole item is
    # blanked (IBM zero-suppression rule) — decimal point, commas and fixed
    # sign included. Check protection is the ONE exception: '*' FILLS rather
    # than blanks, and the decimal point SURVIVES. NIST-85 NC124A:
    # "ZZ.ZZ" -> '     ' but "**.**" -> '**.**' and "*,***.**" -> '*****.**'.
    if ep.all_suppressible and is_zero:
        if ep.fill_char == "*":
            return "".join("." if sym == "." else "*" for sym in ep.template)
        return " " * ep.width

    int_part, frac_part = _digit_strings(dec, ep)
    body = ep.template[:-2] if ep.trailing_sign else ep.template
    float_slot = _float_slot(ep, int_part)

    out: list[str] = []
    suppressing = True  # within the leading-zero zone (left of decimal only)
    int_idx = 0
    frac_idx = 0
    past_decimal = False
    float_digits = frozenset(ep.float_positions[1:])

    for index, sym in enumerate(body):
        is_float_pos = index in float_digits or (
            bool(ep.float_symbol) and index == ep.float_positions[0]
        )
        if index == float_slot:
            # The floating symbol lands here — immediately left of the first
            # significant digit. Its own digit (if it had one) is suppressed.
            out.append(
                _sign_char(ep.float_symbol, negative)
                if ep.float_symbol in _SIGN_SYMS
                else ep.float_symbol
            )
            if index in float_digits and not past_decimal:
                int_idx += 1
        elif is_float_pos:
            if index not in float_digits:
                out.append(ep.fill_char)  # reserved slot, symbol went elsewhere
            elif past_decimal:
                out.append(frac_part[frac_idx])
                frac_idx += 1
            else:
                digit = int_part[int_idx]
                int_idx += 1
                if suppressing and digit == "0":
                    out.append(ep.fill_char)
                else:
                    suppressing = False
                    out.append(digit)
        elif sym in _SIGN_SYMS:
            out.append(_sign_char(sym, negative))
        elif sym == "9":
            if past_decimal:
                out.append(frac_part[frac_idx])
                frac_idx += 1
            else:
                out.append(int_part[int_idx])
                int_idx += 1
                suppressing = False
        elif sym in ("Z", "*"):
            if past_decimal:
                # value is non-zero here (all-zero handled above); show digit.
                out.append(frac_part[frac_idx])
                frac_idx += 1
            else:
                digit = int_part[int_idx]
                int_idx += 1
                if suppressing and digit == "0":
                    out.append(ep.fill_char)
                else:
                    suppressing = False
                    out.append(digit)
        elif sym == ",":
            out.append(ep.fill_char if suppressing else ",")
        elif sym == ".":
            out.append(".")
            past_decimal = True
            suppressing = False
        elif sym == "B":
            out.append(" ")
        else:
            # Insertion symbol (0, /) or unknown — emit verbatim.
            out.append(sym)

    if ep.trailing_sign:
        # CR / DB report ONLY a negative value; non-negative emits two spaces.
        out.append(ep.trailing_sign if negative else "  ")

    return "".join(out)


def _float_slot(ep: EditPicture, int_part: str) -> int:
    """Return the template index where the floating symbol is emitted.

    The symbol sits immediately to the LEFT of the first significant digit, so
    its position depends on the value, not just the picture. Deciding this up
    front (rather than writing left-to-right and patching backwards) is what
    keeps the awkward cases honest — in ``"$$$$$.99"`` at zero and
    ``"$$,$$$.$$"`` at ``.02`` the symbol lands against the DECIMAL POINT
    rather than against a digit, which a backward patch would have to
    special-case.

    Returns -1 when the picture has no floating string.
    """
    if not ep.float_symbol:
        return -1
    positions = ep.float_positions
    decimal_index = ep.template.index(".") if "." in ep.template else len(ep.template)
    float_digits = frozenset(positions[1:])

    # Every INTEGER digit position in template order, whatever its symbol —
    # the float-hosted ones and any '9'/'Z'/'*' that follow the float string.
    int_slots = [
        i
        for i, sym in enumerate(ep.template)
        if i < decimal_index and (sym in ("9", "Z", "*") or i in float_digits)
    ]

    for slot, digit in zip(int_slots, int_part):
        if digit == "0":
            continue
        # Suppression ends here. If this digit sits in a float position the
        # symbol goes immediately to its left — which may be an insertion
        # character inside the floating string, e.g. the ',' of "--,---.--"
        # rendering -123 as '  -123.00'.
        if slot in float_digits:
            return slot - 1
        # The first significant digit is past the floating string entirely
        # (e.g. "$$99" at 12): the symbol takes the last float position.
        break

    before_point = [p for p in positions if p < decimal_index]
    return before_point[-1] if before_point else positions[-1]


def _sign_char(symbol: str, negative: bool) -> str:
    """Resolve a fixed sign symbol to its emitted character.

    '+' shows '+' for non-negative, '-' for negative.
    '-' shows ' ' for non-negative, '-' for negative.
    """
    if symbol == "+":
        return "-" if negative else "+"
    return "-" if negative else " "
