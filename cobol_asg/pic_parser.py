"""PIC clause parser — full PICTURE grammar plus a semantic pass.

Parses COBOL PIC strings into :class:`CobolTypeDescriptor` instances. The
grammar lives in :mod:`cobol_asg.picture` (``picture.lark``) and covers
every single-byte USAGE DISPLAY data category of the PICTURE clause, so the
*category* is decided by which top-level alternative parses — nothing is
classified by symbol-set membership beforehand. Sizes, digit counts, scale and
the spec's non-context-free rules come from ``picture.analyse``.

Repeat counts ``(N)`` are a parser rule over a real integer terminal, so a count
is read STRUCTURALLY — there is no regex / string slicing anywhere. Counts are
also never expanded: ``X(32767)`` parses as one token with a count, not as 32767
symbols.

This module maps the spec's categories onto :class:`CobolDataCategory`, which is
coarser (alphabetic and alphanumeric share one member) and also carries the
non-DISPLAY USAGE categories (COMP-3, binary, COMP-1/2). USAGE wins for those: a
``numeric`` picture under ``USAGE COMP-3`` is packed decimal.

Edited pictures — numeric-edited and alphanumeric-edited — keep their original PIC
string, because :mod:`cobol_asg.edit_picture` needs it to build the
MOVE-time edit mask, and a numeric-edited one keeps the currency symbol beside
it for the same reason. Categorisation itself no longer goes through
``is_numeric_edited``.

The currency symbol is a grammar TERMINAL, so a compilation unit whose
SPECIAL-NAMES declares CURRENCY SIGN IS needs its own parser rather than an
extra parse-time argument; ``_parser_for`` caches one per symbol.

One category the grammar recognises is refused here rather than described, because
RedDragon has no way to store it: external floating-point, which would need an
encoder and a decoder of its own for the display float form. Refusing at field
ingestion is the stance red-dragon-0599 took for edit symbols the formatter could
not yet honour — a loud failure instead of a well-formed but wrong field.
"""

from __future__ import annotations

from functools import cache

from lark import Lark, Tree
from lark.exceptions import UnexpectedInput

from cobol_asg import picture
from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from cobol_asg.edit_picture import (
    UnsupportedEditPictureError,
)
from cobol_asg.index_types import INDEX_ITEM
from cobol_asg.item_clauses import NO_ITEM_CLAUSES, ItemClauses
from cobol_asg.program_conventions import DEFAULT_CONVENTIONS, ProgramConventions

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

# The grammar's top-level alternatives, in the spec's own naming, mapped onto the
# descriptor categories. The spec's alphabetic category maps onto ALPHANUMERIC:
# storage and MOVE behaviour are identical, and the distinctions the spec draws
# (legal senders, class checking) are not modelled — see CobolDataCategory.
_PICTURE_CATEGORY = {
    "alphabetic": CobolDataCategory.ALPHANUMERIC,
    "alphanumeric": CobolDataCategory.ALPHANUMERIC,
    "alphanumeric_edited": CobolDataCategory.ALPHANUMERIC_EDITED,
    "numeric_edited": CobolDataCategory.NUMERIC_EDITED,
    # "numeric" is deliberately absent: its descriptor category comes from USAGE
    # (zoned decimal, packed decimal or binary), not from the picture.
}

# Categories the grammar recognises and sizes correctly but that no encode /
# decode path can represent, mapped to the spec's name for the diagnostic.
_PICTURELESS_USAGES = frozenset({"POINTER", "INDEX"})
_FLOAT_CATEGORIES = frozenset({CobolDataCategory.COMP1, CobolDataCategory.COMP2})

_UNSUPPORTED_CATEGORIES = {
    "external_float": "external floating-point",
}

# Categories for which total_digits carries the item's character width rather
# than a digit count. Nothing reads total_digits as a digit count for these —
# the encoders treat the formatted characters as the content — but the two stay
# equal so the field keeps meaning "how long is this thing" for character data.
_WIDTH_AS_TOTAL_DIGITS = frozenset(
    {
        CobolDataCategory.ALPHANUMERIC,
        CobolDataCategory.ALPHANUMERIC_EDITED,
        CobolDataCategory.NUMERIC_EDITED,
    }
)

# BLANK WHEN ZERO makes an otherwise numeric picture numeric-edited (p. 218), but
# that reclassification is deliberately NOT applied to the descriptor: the flag
# has its own encode-time wrapper (emit_context._emit_blank_when_zero_wrap) over
# the ordinary numeric encoders, and routing such a field through the
# numeric-edited encoder instead would drop the blanking altogether. The clause
# is only meaningful on a numeric or numeric-edited item, so it is dropped for
# every other category.
_BLANK_WHEN_ZERO_CATEGORIES = frozenset(
    {
        CobolDataCategory.ZONED_DECIMAL,
        CobolDataCategory.COMP3,
        CobolDataCategory.BINARY,
        CobolDataCategory.COMP1,
        CobolDataCategory.COMP2,
        CobolDataCategory.NUMERIC_EDITED,
    }
)


# One parser per currency symbol, built on first use. A compilation unit's
# CURRENCY SIGN clause changes a TERMINAL of the grammar, so it cannot be a
# parse-time argument; asg_types threads the symbol down from SPECIAL-NAMES
# (red-dragon-3o5f). Building a Lark parser is expensive enough to be worth
# caching, and a program has at most a handful of currency symbols.
#
# DECIMAL-POINT IS COMMA swaps two terminals the same way, so it selects the
# parser too.
@cache
def _parser_for(currency: str, decimal_point_is_comma: bool) -> Lark:
    return picture.build_parser(
        currency_symbols=currency, decimal_point_is_comma=decimal_point_is_comma
    )


def _digit_counts(
    category: CobolDataCategory, analysis: picture.PictureAnalysis
) -> tuple[int, int]:
    """The descriptor's (total_digits, decimal_digits) for one analysed picture.

    Character and numeric-edited items carry their width, because their content
    IS the character string. Every numeric category carries the STORED digit
    positions: a scaling position holds no digit in any USAGE — what a P-scaled
    item stores is the digits written as 9, with the Ps applied as
    CobolTypeDescriptor.scale — so total_digits stays equal to the number of
    digits the encoders actually write, packed and binary included.
    """
    if category in _WIDTH_AS_TOTAL_DIGITS:
        return analysis.char_positions, analysis.fraction_digits
    stored_digits = analysis.digit_positions - analysis.scaling_positions
    return stored_digits, min(analysis.fraction_digits, stored_digits)


def _has_no_picture(pic: str, usage: str) -> bool:
    return (
        not pic
        or usage in _PICTURELESS_USAGES
        or pic.upper() == "POINTER"
        or _USAGE_TO_CATEGORY.get(usage) in _FLOAT_CATEGORIES
    )


def _pictureless_descriptor(
    pic: str, usage: str, pointer_type: CobolTypeDescriptor
) -> CobolTypeDescriptor:
    """USAGE POINTER and INDEX have fixed types; COMP-1, COMP-2 and a group with
    no PICTURE carry only their USAGE category."""
    if usage == "POINTER" or pic.upper() == "POINTER":
        return pointer_type
    if usage == "INDEX":
        return INDEX_ITEM
    return CobolTypeDescriptor(
        category=_USAGE_TO_CATEGORY.get(usage, CobolDataCategory.ZONED_DECIMAL),
        total_digits=0,
    )


def _parse_tree(pic: str, currency: str, decimal_point_is_comma: bool) -> Tree:
    try:
        return _parser_for(currency, decimal_point_is_comma).parse(pic)
    except UnexpectedInput as exc:
        raise ValueError(f"Cannot parse PIC clause: {pic!r}") from exc


def _checked_analysis(
    pic: str, tree: Tree, sign_separate: bool
) -> picture.PictureAnalysis:
    """The picture's analysis, refusing a string that breaks a rule depending on
    a repeat count or a run's length (see picture.analyse), and a category with
    no runtime representation."""
    analysis = picture.analyse(tree, sign_separate=sign_separate)
    if analysis.errors:
        raise ValueError(f"Invalid PIC clause: {pic!r}: " + "; ".join(analysis.errors))
    if analysis.category in _UNSUPPORTED_CATEGORIES:
        raise UnsupportedEditPictureError(
            f"{_UNSUPPORTED_CATEGORIES[analysis.category]} PICTURE is not supported: "
            f"{pic!r}"
        )
    return analysis


@cache
def parse_pic(
    pic: str,
    usage: str = "DISPLAY",
    clauses: ItemClauses = NO_ITEM_CLAUSES,
    conventions: ProgramConventions = DEFAULT_CONVENTIONS,
) -> CobolTypeDescriptor:
    """Parse a COBOL PIC clause string into a CobolTypeDescriptor.

    Args:
        pic: The PIC string (e.g. "9(5)", "S9(5)V99", "X(8)", "$$$,$$9.99CR").
        usage: USAGE clause value ("DISPLAY", "COMP-3", "COMP").
        clauses: the entry's SIGN, JUSTIFIED and BLANK WHEN ZERO clauses. SIGN
            IS SEPARATE CHARACTER adds a character position.
        conventions: the program's currency symbol ('$' unless SPECIAL-NAMES
            declared CURRENCY SIGN IS otherwise, red-dragon-3o5f), DECIMAL-POINT
            IS COMMA, and the addressing mode's pointer type. The currency
            symbol and the decimal point are grammar terminals, so they select
            the parser rather than being arguments to the parse.

    Returns:
        A CobolTypeDescriptor describing the field's type and layout.

    Raises:
        ValueError: if the string is not a legal PICTURE character-string, or
            parses but breaks a digit-count / run-length rule.
        UnsupportedEditPictureError: if the picture's category has no runtime
            representation (a ValueError subclass, so existing handling holds).
    """
    if _has_no_picture(pic, usage):
        return _pictureless_descriptor(pic, usage, conventions.pointer_type)
    analysis = _checked_analysis(
        pic,
        _parse_tree(pic, conventions.currency, conventions.decimal_point_is_comma),
        clauses.sign_separate,
    )
    usage_category = _USAGE_TO_CATEGORY.get(usage, CobolDataCategory.ZONED_DECIMAL)
    # USAGE governs the category for numeric pictures; the picture governs it for
    # every other category, because those are DISPLAY-only.
    category = _PICTURE_CATEGORY.get(analysis.category, usage_category)

    total_digits, decimal_digits = _digit_counts(category, analysis)

    return CobolTypeDescriptor(
        category=category,
        total_digits=total_digits,
        decimal_digits=decimal_digits,
        signed=analysis.signed,
        char_positions=analysis.char_positions,
        sign_separate=clauses.sign_separate,
        sign_leading=clauses.sign_leading,
        justified_right=clauses.justified_right,
        blank_when_zero=clauses.blank_when_zero
        and category in _BLANK_WHEN_ZERO_CATEGORIES,
        scale=analysis.point_shift,
        currency=conventions.currency,
        decimal_point_is_comma=conventions.decimal_point_is_comma,
        pic_string=pic,
        alphabetic=analysis.category == "alphabetic",
    )
