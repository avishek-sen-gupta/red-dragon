"""PIC clause parser — Lark grammar + transformer.

Parses COBOL PIC strings (e.g. "S9(5)V99", "X(8)") into
:class:`CobolTypeDescriptor` instances. The repeat count ``(N)`` is a
PARSER rule over a real integer terminal, so the count is read
STRUCTURALLY — there is no regex / string slicing anywhere.

Grammar shape (ported from the retired ANTLR grammar):
  - numeric "fraction": optional ``S`` sign, optional leading ``P*``
    scaling, then digits (each ``9`` or ``Z``, optionally ``(N)``)
    possibly split by a single ``V`` into integer/fraction parts, then
    optional trailing ``P*`` scaling.
  - alphanumeric: any sequence containing at least one ``X`` (with
    ``9``/``Z`` digit positions allowed mixed on either side).
  - ``POINTER`` USAGE.
Editing characters (commas, '.', '-', currency) are ignored, matching the
hidden-channel treatment of the old grammar.
"""

from __future__ import annotations

import logging

from dataclasses import dataclass

from lark import Lark, Transformer
from lark.exceptions import UnexpectedInput

from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor

logger = logging.getLogger(__name__)

_USAGE_TO_CATEGORY = {
    "COMP-3": CobolDataCategory.COMP3,
    "COMP3": CobolDataCategory.COMP3,
    "PACKED-DECIMAL": CobolDataCategory.COMP3,
    "COMP": CobolDataCategory.BINARY,
    "COMP-4": CobolDataCategory.BINARY,
    "BINARY": CobolDataCategory.BINARY,
    "COMP-5": CobolDataCategory.BINARY,
    "COMP5": CobolDataCategory.BINARY,
    "COMP-1": CobolDataCategory.COMP1,
    "COMP1": CobolDataCategory.COMP1,
    "COMP-2": CobolDataCategory.COMP2,
    "COMP2": CobolDataCategory.COMP2,
}


# A digit position is either a bare digit symbol (9 or Z) or one carrying a
# repeat count `(N)`. The count is matched as a real INT terminal — the
# transformer reads int(token), never a regex/slice. POINTER is matched before
# the digit symbols so the leading 'P' of "POINTER" is not mistaken for scaling.
_GRAMMAR = r"""
    start: pointer | alphanumeric | fraction

    pointer: POINTER

    fraction: SIGN? scaling* body scaling*

    body: integer_part DECPOINT fraction_part -> both_sides
        | integer_part DECPOINT               -> only_left
        | DECPOINT fraction_part              -> only_right
        | integer_part                        -> integer_only

    integer_part: digit+
    fraction_part: digit+

    // Alphanumeric: at least one X, with digit positions allowed on either side.
    alphanumeric: alnum_pos* ALPHA_X count? alnum_pos*
    alnum_pos: ALPHA_X count? | digit

    digit: DIGIT_SYM count?
    count: "(" INT ")"

    POINTER: "POINTER"i
    SIGN: "S"i
    DECPOINT: "V"i
    DIGIT_SYM: "9" | "Z"i
    ALPHA_X: "X"i
    SCALE: "P"i
    scaling: SCALE

    INT: /[0-9]+/

    // Editing / display characters carry no stored-digit semantics — ignore them
    // exactly as the old grammar's HIDDEN channel did.
    %ignore /[ \t\f\r\n]+/
    %ignore ","
    %ignore "."
    %ignore "-"
    %ignore "+"
"""

_parser = Lark(_GRAMMAR, parser="earley")


@dataclass(frozen=True)
class _Count:
    """A repeat count `(N)` read structurally from a real INT terminal."""

    n: int


class _PicTransformer(Transformer):
    """Reduces the parse tree to (integer_digits, decimal_digits, ...) facts."""

    def count(self, items: list) -> _Count:
        # INT terminal -> a real integer; structural, no regex/slice.
        return _Count(int(items[0]))

    def digit(self, items: list) -> int:
        # items: [DIGIT_SYM] or [DIGIT_SYM, count]; Z counts as a digit position.
        if len(items) == 2:
            return items[1].n
        return 1

    def integer_part(self, items: list) -> int:
        return sum(items)

    def fraction_part(self, items: list) -> int:
        return sum(items)

    # body alternatives -> (integer_digits, decimal_digits)
    def both_sides(self, items: list) -> tuple[int, int]:
        # items: [integer_digits, DECPOINT, fraction_digits]
        return (items[0], items[2])

    def only_left(self, items: list) -> tuple[int, int]:
        return (items[0], 0)

    def only_right(self, items: list) -> tuple[int, int]:
        # items: [DECPOINT, fraction_digits]
        return (0, items[1])

    def integer_only(self, items: list) -> tuple[int, int]:
        return (items[0], 0)

    def fraction(self, items: list) -> dict:
        signed = any(getattr(t, "type", None) == "SIGN" for t in items)
        body = next(i for i in items if isinstance(i, tuple))
        integer_digits, decimal_digits = body
        return {
            "alphanumeric": False,
            "integer_digits": integer_digits,
            "decimal_digits": decimal_digits,
            "signed": signed,
        }

    def alnum_pos(self, items: list) -> int:
        # ALPHA_X (with optional count) or a digit position.
        if isinstance(items[0], int):  # digit subtree already reduced to its count
            return items[0]
        if len(items) == 2:  # ALPHA_X count
            return items[1].n
        return 1  # bare ALPHA_X

    def alphanumeric(self, items: list) -> dict:
        # items are a mix of: ints (each a reduced alnum_pos / digit), the central
        # ALPHA_X token, and a _Count (only when that central X carried `(N)`).
        length = 0
        for item in items:
            if isinstance(item, int):
                length += item
            elif isinstance(item, _Count):
                # A bare X counts 1; its trailing count replaces that 1.
                length += item.n - 1
            else:  # the central ALPHA_X token
                length += 1
        return {
            "alphanumeric": True,
            "alphanumeric_length": length,
        }

    def pointer(self, items: list) -> dict:
        # POINTER is a USAGE keyword with no stored digits; treat as zero-size
        # numeric so usage handling in parse_pic governs the result.
        return {
            "alphanumeric": False,
            "integer_digits": 0,
            "decimal_digits": 0,
            "signed": False,
        }

    def start(self, items: list) -> dict:
        return items[0]


_transformer = _PicTransformer()


def parse_pic(
    pic: str,
    usage: str = "DISPLAY",
    sign_leading: bool = False,
    sign_separate: bool = False,
    justified_right: bool = False,
    blank_when_zero: bool = False,
) -> CobolTypeDescriptor:
    """Parse a COBOL PIC clause string into a CobolTypeDescriptor.

    Args:
        pic: The PIC string (e.g. "9(5)", "S9(5)V99", "X(8)").
        usage: USAGE clause value ("DISPLAY", "COMP-3", "COMP").

    Returns:
        A CobolTypeDescriptor describing the field's type and layout.
    """
    category = _USAGE_TO_CATEGORY.get(usage, CobolDataCategory.ZONED_DECIMAL)

    # COMP-1 and COMP-2 have no PIC clause — return immediately with fixed size.
    if category in (CobolDataCategory.COMP1, CobolDataCategory.COMP2):
        return CobolTypeDescriptor(
            category=category,
            total_digits=0,
            decimal_digits=0,
            signed=False,
        )

    if not pic:
        return CobolTypeDescriptor(
            category=category,
            total_digits=0,
            decimal_digits=0,
            signed=False,
        )

    try:
        tree = _parser.parse(pic)
    except UnexpectedInput as exc:
        raise ValueError(f"Cannot parse PIC clause: {pic!r}") from exc
    facts: dict = _transformer.transform(tree)

    if facts["alphanumeric"]:
        return CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC,
            total_digits=facts["alphanumeric_length"],
            decimal_digits=0,
            signed=False,
            justified_right=justified_right,
        )

    total_digits = facts["integer_digits"] + facts["decimal_digits"]

    logger.debug(
        "parse_pic(%r, %r) -> category=%s, total=%d, dec=%d, signed=%s",
        pic,
        usage,
        category,
        total_digits,
        facts["decimal_digits"],
        facts["signed"],
    )

    return CobolTypeDescriptor(
        category=category,
        total_digits=total_digits,
        decimal_digits=facts["decimal_digits"],
        signed=facts["signed"],
        sign_separate=sign_separate,
        sign_leading=sign_leading,
        blank_when_zero=blank_when_zero,
    )
