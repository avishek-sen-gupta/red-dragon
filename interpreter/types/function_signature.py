"""FunctionSignature — immutable record of a function's parameter types and return type."""

from __future__ import annotations

from dataclasses import dataclass

from interpreter.types.function_kind import FunctionKind
from interpreter.types.type_expr import TypeExpr

_THIS_NAMES = frozenset(("this", "$this"))


@dataclass(frozen=True)
class FunctionSignature:
    """Complete type signature for a function.

    params: tuple of (name, type) pairs, e.g. (("a", ScalarType("Int")), ...)
    return_type: canonical return type as TypeExpr, or ScalarType("") if unknown
    kind: classification as UNBOUND, INSTANCE, or STATIC

    TypeExpr values compare equal to their string representations, so
    existing code like ``sig.return_type == "Int"`` continues to work.
    """

    params: tuple[tuple[str, TypeExpr], ...]
    return_type: TypeExpr
    kind: FunctionKind = FunctionKind.UNBOUND

    @property
    def callable_params(self) -> tuple[tuple[str, TypeExpr], ...]:
        """User-facing params, excluding the implicit 'this'/'$this' receiver."""
        if self.kind is not FunctionKind.INSTANCE:
            return self.params
        return tuple((n, t) for n, t in self.params if n not in _THIS_NAMES)
