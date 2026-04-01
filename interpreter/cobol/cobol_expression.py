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


@dataclass(frozen=True)
class BinOpNode:
    """Binary arithmetic operation."""

    op: str  # "+", "-", "*", "/"
    left: "ExprNode"
    right: "ExprNode"


ExprNode = LiteralNode | FieldRefNode | BinOpNode


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
