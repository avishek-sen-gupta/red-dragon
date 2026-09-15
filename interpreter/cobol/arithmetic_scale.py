# pyright: standard
"""Static IBM ARITH(COMPAT) scale analysis for COBOL arithmetic expressions.

Before emitting an expression, lowering needs the decimal places each
intermediate carries (IBM "Fixed-point data and intermediate results") and
whether the whole expression is computed in floating point (IBM
"Floating-point data and intermediate results"). Both depend only on PIC
clauses, literals, intrinsic names and receivers, so they are computed here
without emitting IR.

Intrinsic classification is this project's reading of IBM's function types:
FLOAT_INTRINSICS keep today's floating behaviour; INTEGER_INTRINSICS are
integer-valued; ARGUMENT_SCALED_INTRINSICS carry their arguments' decimals.
"""

from __future__ import annotations

from collections.abc import Callable

from cobol_asg.cobol_expression import (
    BinOpNode,
    ExprNode,
    FieldRefNode,
    FunctionNode,
    LengthOfNode,
    LiteralNode,
    RefModNode,
)
from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from cobol_numeric.number import from_literal
from cobol_numeric.scale import (
    Scale,
    add_scale,
    carry,
    div_scale,
    literal_scale,
    mul_scale,
)

FieldTypes = Callable[[str], CobolTypeDescriptor | None]

FLOAT_INTRINSICS = frozenset(
    {
        "SIN",
        "COS",
        "TAN",
        "ASIN",
        "ACOS",
        "ATAN",
        "EXP",
        "EXP10",
        "LOG",
        "LOG10",
        "SQRT",
        "MEAN",
        "MEDIAN",
        "MIDRANGE",
        "VARIANCE",
        "ANNUITY",
        "PRESENT-VALUE",
        "RANDOM",
        "NUMVAL",
        "NUMVAL-C",
    }
)
INTEGER_INTRINSICS = frozenset(
    {
        "LENGTH",
        "INTEGER-OF-DATE",
        "DATE-OF-INTEGER",
        "MOD",
        "ORD-MAX",
        "ORD-MIN",
        "FACTORIAL",
        "INTEGER",
        "INTEGER-PART",
        "ORD",
        "DAY-OF-INTEGER",
        "INTEGER-OF-DAY",
        "DATE-TO-YYYYMMDD",
        "DAY-TO-YYYYDDD",
        "YEAR-TO-YYYY",
        "TEST-NUMVAL",
        "TEST-NUMVAL-C",
    }
)
ARGUMENT_SCALED_INTRINSICS = frozenset(
    {"MAX", "MIN", "SUM", "ABS", "RANGE", "REM", "FRACTION-PART"}
)

_FLOATING_CATEGORIES = frozenset({CobolDataCategory.COMP1, CobolDataCategory.COMP2})
_FUNCTION_INTEGER_PLACES = 18


def field_scale(td: CobolTypeDescriptor) -> Scale:
    return Scale(
        max(td.total_digits - td.decimal_digits + td.scale, 1),
        td.decimal_digits + max(-td.scale, 0),
    )


def is_floating_type(td: CobolTypeDescriptor) -> bool:
    return td.category in _FLOATING_CATEGORIES


def receiver_decimals(td: CobolTypeDescriptor, rounded: bool) -> int:
    """Decimal places a receiver contributes to dmax; ROUNDED needs one more digit."""
    return field_scale(td).decimal_places + (1 if rounded else 0)


def _numeric_literal_scale(text: str) -> Scale | None:
    try:
        from_literal(text)
    except ValueError:
        return None
    return literal_scale(text)


def expression_is_floating(node: ExprNode, field_types: FieldTypes) -> bool:
    if isinstance(node, (FieldRefNode, RefModNode)):
        td = field_types(node.name)
        return td is not None and is_floating_type(td)
    if isinstance(node, BinOpNode):
        return expression_is_floating(node.left, field_types) or expression_is_floating(
            node.right, field_types
        )
    if isinstance(node, FunctionNode):
        return node.name.upper() in FLOAT_INTRINSICS or any(
            expression_is_floating(arg, field_types) for arg in node.args
        )
    return False


def operand_dmax(node: ExprNode, field_types: FieldTypes) -> int:
    """Largest decimal places of any operand except divisors."""
    if isinstance(node, (FieldRefNode, RefModNode)):
        td = field_types(node.name)
        return field_scale(td).decimal_places if td is not None else 0
    if isinstance(node, LiteralNode):
        scale = _numeric_literal_scale(node.value)
        return scale.decimal_places if scale is not None else 0
    if isinstance(node, BinOpNode):
        right = 0 if node.op == "/" else operand_dmax(node.right, field_types)
        return max(operand_dmax(node.left, field_types), right)
    if isinstance(node, FunctionNode):
        return max((operand_dmax(arg, field_types) for arg in node.args), default=0)
    return 0


def node_scale(node: ExprNode, dmax: int, field_types: FieldTypes) -> Scale:
    if isinstance(node, (FieldRefNode, RefModNode)):
        td = field_types(node.name)
        return field_scale(td) if td is not None else Scale(1, 0)
    if isinstance(node, LiteralNode):
        return _numeric_literal_scale(node.value) or Scale(1, 0)
    if isinstance(node, LengthOfNode):
        return Scale(9, 0)
    if isinstance(node, BinOpNode):
        left = node_scale(node.left, dmax, field_types)
        right = node_scale(node.right, dmax, field_types)
        if node.op in ("+", "-"):
            combined = add_scale(left, right)
        elif node.op == "*":
            combined = mul_scale(left, right)
        else:
            combined = div_scale(left, right, dmax)
        return carry(combined, dmax)
    if isinstance(node, FunctionNode):
        name = node.name.upper()
        if name in ARGUMENT_SCALED_INTRINSICS:
            decimals = max(
                (
                    node_scale(arg, dmax, field_types).decimal_places
                    for arg in node.args
                ),
                default=0,
            )
            return Scale(_FUNCTION_INTEGER_PLACES, decimals)
        return Scale(_FUNCTION_INTEGER_PLACES, 0)
    return Scale(1, 0)
