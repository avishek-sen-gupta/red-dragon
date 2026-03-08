"""FunctionSignature — immutable record of a function's parameter types and return type."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.type_expr import TypeExpr


@dataclass(frozen=True)
class FunctionSignature:
    """Complete type signature for a function.

    params: tuple of (name, type) pairs, e.g. (("a", ScalarType("Int")), ...)
    return_type: canonical return type as TypeExpr, or ScalarType("") if unknown

    TypeExpr values compare equal to their string representations, so
    existing code like ``sig.return_type == "Int"`` continues to work.
    """

    params: tuple[tuple[str, TypeExpr], ...]
    return_type: TypeExpr
