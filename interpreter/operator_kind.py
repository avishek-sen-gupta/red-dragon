# pyright: standard
"""Typed operator enums for BINOP and UNOP instructions."""

from __future__ import annotations

from enum import Enum


class BinopKind(str, Enum):
    """Binary operator — the superset of operators across all 15 frontends + COBOL."""

    # Arithmetic
    ADD = "+"
    SUB = "-"
    MUL = "*"
    DIV = "/"
    FLOOR_DIV = "//"
    MOD = "%"
    MOD_WORD = "mod"
    POWER = "**"
    # Comparison
    EQ = "=="
    NE = "!="
    NE_LUA = "~="
    LT = "<"
    GT = ">"
    LE = "<="
    GE = ">="
    STRICT_EQ = "==="
    # Logical
    AND = "and"
    OR = "or"
    IN = "in"
    # Bitwise
    BIT_AND = "&"
    BIT_OR = "|"
    BIT_XOR = "^"
    BIT_XOR_LUA = "~"
    LSHIFT = "<<"
    RSHIFT = ">>"
    UNSIGNED_RSHIFT = ">>>"
    # String concat
    CONCAT_LUA = ".."
    CONCAT_PASCAL = "."
    # Null coalescing / ternary
    NULLISH_COALESCE = "?:"
    NULLISH_COALESCE_CSHARP = "??"
    LOGICAL_OR_SYM = "||"
    LOGICAL_AND_SYM = "&&"


class UnopKind(str, Enum):
    """Unary operator — the superset of operators across all 15 frontends + COBOL."""

    NEG = "-"
    POS = "+"
    NOT = "not"
    BIT_NOT = "~"
    LEN = "#"
    BANG = "!"
    DOUBLE_BANG = "!!"
    ADDR_OF = "&"
    CHAN_RECEIVE = "<-"


_BINOP_LOOKUP: dict[str, BinopKind] = {k.value: k for k in BinopKind}
_UNOP_LOOKUP: dict[str, UnopKind] = {k.value: k for k in UnopKind}


def resolve_binop(op: str) -> BinopKind:
    """Convert a string operator to BinopKind. Raises ValueError if not found."""
    result = _BINOP_LOOKUP.get(op)
    if result is None:
        raise ValueError(f"Unknown binary operator: {op!r}")
    return result


def resolve_unop(op: str) -> UnopKind:
    """Convert a string operator to UnopKind. Raises ValueError if not found."""
    result = _UNOP_LOOKUP.get(op)
    if result is None:
        raise ValueError(f"Unknown unary operator: {op!r}")
    return result
