"""PIC clause parser — ANTLR visitor that walks the parse tree.

Parses COBOL PIC strings (e.g. "S9(5)V99", "X(8)") into
CobolTypeDescriptor instances using the ANTLR grammar ported
from smojol's CobolDataTypes.g4.
"""

from __future__ import annotations

import logging
import re

from antlr4 import CommonTokenStream, InputStream

from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
from interpreter.cobol.grammars.CobolDataTypes import CobolDataTypes
from interpreter.cobol.grammars.CobolDataTypesLexer import CobolDataTypesLexer
from interpreter.cobol.grammars.CobolDataTypesVisitor import CobolDataTypesVisitor

logger = logging.getLogger(__name__)

_NUMBEROF_PATTERN = re.compile(r"\((\d+)\)")

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


def _extract_repeat_count(numberof_text: str) -> int:
    """Extract the integer from a NUMBEROF token like '(5)'."""
    match = _NUMBEROF_PATTERN.search(numberof_text)
    return int(match.group(1)) if match else 1


class _PicVisitor(CobolDataTypesVisitor):
    """Walks the ANTLR parse tree to extract PIC components."""

    def __init__(self):
        self.is_signed = False
        self.integer_digits = 0
        self.decimal_digits = 0
        self.is_alphanumeric = False
        self.alphanumeric_length = 0
        self.has_decimal_point = False

    def visitFraction(self, ctx: CobolDataTypes.FractionContext):
        if ctx.SIGN_SYMBOL():
            self.is_signed = True
        return self.visitChildren(ctx)

    def visitAlphanumeric(self, ctx: CobolDataTypes.AlphanumericContext):
        self.is_alphanumeric = True
        return self.visitChildren(ctx)

    def visitInteger(self, ctx: CobolDataTypes.IntegerContext):
        self.integer_digits += self._count_digits(ctx)
        return None

    def visitIntegerPart(self, ctx: CobolDataTypes.IntegerPartContext):
        self.integer_digits += self._count_digits(ctx)
        return None

    def visitFractionalPart(self, ctx: CobolDataTypes.FractionalPartContext):
        self.has_decimal_point = True
        self.decimal_digits += self._count_digits(ctx)
        return None

    def visitOnlyLeftOfDecimalPoint(
        self, ctx: CobolDataTypes.OnlyLeftOfDecimalPointContext
    ):
        self.has_decimal_point = True
        return self.visitChildren(ctx)

    def visitOnlyRightOfDecimalPoint(
        self, ctx: CobolDataTypes.OnlyRightOfDecimalPointContext
    ):
        self.has_decimal_point = True
        return self.visitChildren(ctx)

    def visitBothSidesOfDecimalPoint(
        self, ctx: CobolDataTypes.BothSidesOfDecimalPointContext
    ):
        self.has_decimal_point = True
        return self.visitChildren(ctx)

    def visitAlphaNumericIndicator(
        self, ctx: CobolDataTypes.AlphaNumericIndicatorContext
    ):
        if ctx.charTypeIndicator():
            self.alphanumeric_length += 1
        elif ctx.nchars():
            numberof_ctx = ctx.nchars().numberOf()
            self.alphanumeric_length += _extract_repeat_count(numberof_ctx.getText())
        return None

    def visitLeftSideAlphanumericIndicator(
        self, ctx: CobolDataTypes.LeftSideAlphanumericIndicatorContext
    ):
        if ctx.alphaNumericIndicator():
            return self.visitAlphaNumericIndicator(ctx.alphaNumericIndicator())
        if ctx.digitIndicator():
            self.alphanumeric_length += self._count_single_digit_indicator(
                ctx.digitIndicator()
            )
        return None

    def visitRightSideAlphanumericIndicator(
        self, ctx: CobolDataTypes.RightSideAlphanumericIndicatorContext
    ):
        if ctx.alphaNumericIndicator():
            return self.visitAlphaNumericIndicator(ctx.alphaNumericIndicator())
        if ctx.digitIndicator():
            self.alphanumeric_length += self._count_single_digit_indicator(
                ctx.digitIndicator()
            )
        return None

    def _count_digits(self, ctx) -> int:
        """Count total digit positions from digitIndicator children."""
        return sum(
            self._count_single_digit_indicator(di) for di in ctx.digitIndicator()
        )

    def _count_single_digit_indicator(self, di_ctx) -> int:
        """Count digits from a single digitIndicator (bare 9 or 9(N))."""
        if di_ctx.ndigits():
            numberof_ctx = di_ctx.ndigits().numberOf()
            return _extract_repeat_count(numberof_ctx.getText())
        return 1


def parse_pic(
    pic: str,
    usage: str = "DISPLAY",
    sign_leading: bool = False,
    sign_separate: bool = False,
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

    input_stream = InputStream(pic)
    lexer = CobolDataTypesLexer(input_stream)
    token_stream = CommonTokenStream(lexer)
    parser = CobolDataTypes(token_stream)
    tree = parser.startRule()

    visitor = _PicVisitor()
    visitor.visit(tree)

    if visitor.is_alphanumeric:
        return CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC,
            total_digits=visitor.alphanumeric_length,
            decimal_digits=0,
            signed=False,
        )

    total_digits = visitor.integer_digits + visitor.decimal_digits

    logger.debug(
        "parse_pic(%r, %r) -> category=%s, total=%d, dec=%d, signed=%s",
        pic,
        usage,
        category,
        total_digits,
        visitor.decimal_digits,
        visitor.is_signed,
    )

    return CobolTypeDescriptor(
        category=category,
        total_digits=total_digits,
        decimal_digits=visitor.decimal_digits,
        signed=visitor.is_signed,
        sign_separate=sign_separate,
        sign_leading=sign_leading,
    )
