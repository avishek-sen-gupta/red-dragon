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
    # String concat
    CONCAT_LUA = ".."
    CONCAT_PASCAL = "."
    # Null coalescing / ternary
    NULLISH_COALESCE = "?:"
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


_BINOP_LOOKUP: dict[str, BinopKind] = {k.value: k for k in BinopKind}
_UNOP_LOOKUP: dict[str, UnopKind] = {k.value: k for k in UnopKind}


def resolve_binop(op: str) -> BinopKind | str:
    """Convert a string operator to BinopKind. Returns str as-is if not found (bridge period)."""
    return _BINOP_LOOKUP.get(op, op)


def resolve_unop(op: str) -> UnopKind | str:
    """Convert a string operator to UnopKind. Returns str as-is if not found (bridge period)."""
    return _UNOP_LOOKUP.get(op, op)
