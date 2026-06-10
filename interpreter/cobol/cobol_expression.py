# pyright: standard
"""COBOL arithmetic expression tokenizer and recursive-descent parser.

Parses expressions emitted by the ProLeap bridge for COMPUTE statements.
Expressions are space-separated tokens like "WS-A + WS-B * 2" or
"(WS-A + WS-B) * 100 / WS-C".

Grammar (operator precedence, left-associative):
    expr   → term (('+' | '-') term)*
    term   → factor (('*' | '/') factor)*
    factor → '(' expr ')' | atom
    atom   → NUMBER | IDENTIFIER
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Matches parentheses, operators, decimal numbers, and COBOL identifiers
# (which may contain hyphens, e.g. WS-A, WS-TOTAL-AMOUNT).
# Also captures subscripted field references like WS-TABLE(WS-IDX) as single tokens.
_TOKEN_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9-]*\([A-Za-z0-9-]+\)"  # subscripted field: WS-TBL(IDX)
    r"|[()]"  # plain parentheses
    r"|[+\-*/]"  # operators
    r"|[0-9]+(?:\.[0-9]+)?"  # decimal numbers
    r"|[A-Za-z][A-Za-z0-9-]*"  # plain identifiers
)

_ADDITIVE_OPS = frozenset({"+", "-"})
_MULTIPLICATIVE_OPS = frozenset({"*", "/"})


# ── Expression tree nodes (frozen, immutable) ────────────────────


@dataclass(frozen=True)
class LiteralNode:
    """Numeric literal (integer or decimal)."""

    value: str


@dataclass(frozen=True)
class FieldRefNode:
    """Reference to a COBOL data field by name."""

    name: str
    subscripts: tuple["ExprNode", ...] = ()


@dataclass(frozen=True)
class RefModNode:
    """Reference modification: field reference with start position and optional length."""

    name: str
    ref_mod_start: "ExprNode"
    ref_mod_length: "ExprNode | None" = None
    subscripts: tuple["ExprNode", ...] = ()


@dataclass(frozen=True)
class BinOpNode:
    """Binary arithmetic operation."""

    op: str  # "+", "-", "*", "/"
    left: "ExprNode"
    right: "ExprNode"


@dataclass(frozen=True)
class FunctionNode:
    """Intrinsic FUNCTION call used as an expression operand.

    Appears in COMPUTE expressions and IF relation operands, e.g.
    COMPUTE X = FUNCTION TRIM(WS-A) or
    IF FUNCTION UPPER-CASE(A) = FUNCTION UPPER-CASE(B). The bridge serializes
    it as {"kind":"function","name":..,"args":[<expr>, ...]} (red-dragon-ge72).
    """

    name: str
    args: tuple["ExprNode", ...] = ()


ExprNode = LiteralNode | FieldRefNode | RefModNode | BinOpNode | FunctionNode


def expr_from_dict(d: dict) -> ExprNode:
    """Deserialize a structured JSON expression tree (emitted by the Java bridge) into an ExprNode.

    The JSON uses "kind" as the discriminant with values:
    - {"kind": "lit", "value": "5"} — literal
    - {"kind": "ref", "name": "WS-FIELD"} — plain field reference
    - {"kind": "ref", "name": "WS-FIELD", "ref_mod_start": {...}, "ref_mod_length": {...}} — reference modification
    - {"kind": "binop", "op": "+", "left": {...}, "right": {...}} — binary operation
    - {"kind": "neg", "expr": {...}} — unary negation (folded into binop * -1)
    """
    kind = d["kind"]
    if kind == "lit":
        return LiteralNode(value=d["value"])
    if kind == "ref":
        subscripts = tuple(expr_from_dict(s) for s in d.get("subscripts", []))
        if "ref_mod_start" in d:
            return RefModNode(
                name=d["name"],
                ref_mod_start=expr_from_dict(d["ref_mod_start"]),
                ref_mod_length=(
                    expr_from_dict(d["ref_mod_length"])
                    if "ref_mod_length" in d
                    else None
                ),
                subscripts=subscripts,
            )
        return FieldRefNode(name=d["name"], subscripts=subscripts)
    if kind == "binop":
        return BinOpNode(
            op=d["op"],
            left=expr_from_dict(d["left"]),
            right=expr_from_dict(d["right"]),
        )
    if kind == "neg":
        return BinOpNode(
            op="*",
            left=LiteralNode(value="-1"),
            right=expr_from_dict(d["expr"]),
        )
    if kind == "function":
        return FunctionNode(
            name=d.get("name", ""),
            args=tuple(expr_from_dict(a) for a in d.get("args", []) or []),
        )
    raise ValueError(f"Unknown expression node kind: {kind!r}")


def expr_to_dict(node: ExprNode) -> dict:
    """Serialize an ExprNode back to its structured JSON dict form.

    Inverse of :func:`expr_from_dict`. Used to round-trip subscript interiors
    (red-dragon-l445). ``neg`` is not re-emitted — a folded negation already
    lives as a ``binop`` after deserialization.
    """
    if isinstance(node, LiteralNode):
        return {"kind": "lit", "value": node.value}
    if isinstance(node, FieldRefNode):
        d: dict = {"kind": "ref", "name": node.name}
        if node.subscripts:
            d["subscripts"] = [expr_to_dict(s) for s in node.subscripts]
        return d
    if isinstance(node, RefModNode):
        d = {"kind": "ref", "name": node.name}
        d["ref_mod_start"] = expr_to_dict(node.ref_mod_start)
        if node.ref_mod_length is not None:
            d["ref_mod_length"] = expr_to_dict(node.ref_mod_length)
        if node.subscripts:
            d["subscripts"] = [expr_to_dict(s) for s in node.subscripts]
        return d
    if isinstance(node, BinOpNode):
        return {
            "kind": "binop",
            "op": node.op,
            "left": expr_to_dict(node.left),
            "right": expr_to_dict(node.right),
        }
    if isinstance(node, FunctionNode):
        return {
            "kind": "function",
            "name": node.name,
            "args": [expr_to_dict(a) for a in node.args],
        }
    raise ValueError(f"Unknown expression node type: {type(node).__name__}")


# ── Tokenizer ────────────────────────────────────────────────────


def tokenize_expression(expression: str) -> list[str]:
    """Tokenize a COBOL arithmetic expression string into a list of tokens.

    Handles parentheses, arithmetic operators, decimal numbers, and
    COBOL identifiers (including hyphenated names like WS-TOTAL-AMOUNT).
    """
    return _TOKEN_RE.findall(expression)


# ── Recursive-descent parser ─────────────────────────────────────


def parse_expression(expression: str) -> ExprNode:
    """Parse a COBOL arithmetic expression string into an expression tree.

    Respects standard arithmetic precedence:
    - Parentheses (highest)
    - Multiplication and division
    - Addition and subtraction (lowest)

    All operators are left-associative.
    """
    tokens = tokenize_expression(expression)
    if not tokens:
        logger.warning("Empty COMPUTE expression: %r", expression)
        return LiteralNode(value="0")

    node, pos = _parse_expr(tokens, 0)
    if pos < len(tokens):
        logger.warning(
            "Unparsed tokens in COMPUTE expression at position %d: %s",
            pos,
            tokens[pos:],
        )
    return node


def _parse_expr(tokens: list[str], pos: int) -> tuple[ExprNode, int]:
    """Parse additive expression: term (('+' | '-') term)*."""
    left, pos = _parse_term(tokens, pos)
    while pos < len(tokens) and tokens[pos] in _ADDITIVE_OPS:
        op = tokens[pos]
        right, pos = _parse_term(tokens, pos + 1)
        left = BinOpNode(op=op, left=left, right=right)
    return left, pos


def _parse_term(tokens: list[str], pos: int) -> tuple[ExprNode, int]:
    """Parse multiplicative expression: factor (('*' | '/') factor)*."""
    left, pos = _parse_factor(tokens, pos)
    while pos < len(tokens) and tokens[pos] in _MULTIPLICATIVE_OPS:
        op = tokens[pos]
        right, pos = _parse_factor(tokens, pos + 1)
        left = BinOpNode(op=op, left=left, right=right)
    return left, pos


def _parse_factor(tokens: list[str], pos: int) -> tuple[ExprNode, int]:
    """Parse factor: '(' expr ')' | atom."""
    if pos < len(tokens) and tokens[pos] == "(":
        node, pos = _parse_expr(tokens, pos + 1)
        if pos < len(tokens) and tokens[pos] == ")":
            pos += 1
        else:
            logger.warning("Missing closing parenthesis in COMPUTE expression")
        return node, pos
    return _parse_atom(tokens, pos)


def _parse_atom(tokens: list[str], pos: int) -> tuple[ExprNode, int]:
    """Parse atom: NUMBER | IDENTIFIER."""
    if pos >= len(tokens):
        logger.warning("Unexpected end of COMPUTE expression")
        return LiteralNode(value="0"), pos

    token = tokens[pos]
    if token[0].isdigit():
        return LiteralNode(value=token), pos + 1
    return FieldRefNode(name=token), pos + 1
