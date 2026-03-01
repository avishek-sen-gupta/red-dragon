# Generated from CobolDataTypes.g4 by ANTLR 4.13.1
from antlr4 import *

if "." in __name__:
    from .CobolDataTypes import CobolDataTypes
else:
    from CobolDataTypes import CobolDataTypes

# This class defines a complete generic visitor for a parse tree produced by CobolDataTypes.


class CobolDataTypesVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by CobolDataTypes#startRule.
    def visitStartRule(self, ctx: CobolDataTypes.StartRuleContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#dataTypeSpec.
    def visitDataTypeSpec(self, ctx: CobolDataTypes.DataTypeSpecContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#pointer.
    def visitPointer(self, ctx: CobolDataTypes.PointerContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#fraction.
    def visitFraction(self, ctx: CobolDataTypes.FractionContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#alphanumeric.
    def visitAlphanumeric(self, ctx: CobolDataTypes.AlphanumericContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#leftSideAlphanumericIndicator.
    def visitLeftSideAlphanumericIndicator(
        self, ctx: CobolDataTypes.LeftSideAlphanumericIndicatorContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#rightSideAlphanumericIndicator.
    def visitRightSideAlphanumericIndicator(
        self, ctx: CobolDataTypes.RightSideAlphanumericIndicatorContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#onlyLeftOfDecimalPoint.
    def visitOnlyLeftOfDecimalPoint(
        self, ctx: CobolDataTypes.OnlyLeftOfDecimalPointContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#onlyRightOfDecimalPoint.
    def visitOnlyRightOfDecimalPoint(
        self, ctx: CobolDataTypes.OnlyRightOfDecimalPointContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#bothSidesOfDecimalPoint.
    def visitBothSidesOfDecimalPoint(
        self, ctx: CobolDataTypes.BothSidesOfDecimalPointContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#integer.
    def visitInteger(self, ctx: CobolDataTypes.IntegerContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#integerPart.
    def visitIntegerPart(self, ctx: CobolDataTypes.IntegerPartContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#fractionalPart.
    def visitFractionalPart(self, ctx: CobolDataTypes.FractionalPartContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#alphaNumericIndicator.
    def visitAlphaNumericIndicator(
        self, ctx: CobolDataTypes.AlphaNumericIndicatorContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#digitIndicator.
    def visitDigitIndicator(self, ctx: CobolDataTypes.DigitIndicatorContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#ndigits.
    def visitNdigits(self, ctx: CobolDataTypes.NdigitsContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#nchars.
    def visitNchars(self, ctx: CobolDataTypes.NcharsContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#numberOf.
    def visitNumberOf(self, ctx: CobolDataTypes.NumberOfContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#decimalPointLocator.
    def visitDecimalPointLocator(self, ctx: CobolDataTypes.DecimalPointLocatorContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#leadingScalingIndicator.
    def visitLeadingScalingIndicator(
        self, ctx: CobolDataTypes.LeadingScalingIndicatorContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#trailingScalingIndicator.
    def visitTrailingScalingIndicator(
        self, ctx: CobolDataTypes.TrailingScalingIndicatorContext
    ):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#numberTypeIndicator.
    def visitNumberTypeIndicator(self, ctx: CobolDataTypes.NumberTypeIndicatorContext):
        return self.visitChildren(ctx)

    # Visit a parse tree produced by CobolDataTypes#charTypeIndicator.
    def visitCharTypeIndicator(self, ctx: CobolDataTypes.CharTypeIndicatorContext):
        return self.visitChildren(ctx)


del CobolDataTypes
