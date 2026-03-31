# pyright: standard
"""UnopCoercionStrategy — injectable language-specific pre-operation type coercion for unary ops."""

from __future__ import annotations

from typing import Protocol

from interpreter.types.type_expr import UNKNOWN, ScalarType, TypeExpr, scalar
from interpreter.types.typed_value import TypedValue


class UnopCoercionStrategy(Protocol):
    """Pre-coerce operand and infer result type for unary operations."""

    def coerce(self, op: str, operand: TypedValue) -> TypedValue:
        """Pre-coerce operand before operator application.

        Contract: will never be called with SymbolicValue operands — the UNOP
        handler short-circuits symbolic operands before calling coerce().
        """
        ...

    def result_type(self, op: str, operand: TypedValue) -> TypeExpr:
        """Infer result type from operator and operand type."""
        ...


_NEGATION_OPS = frozenset({"-", "+"})
_LOGICAL_NOT_OPS = frozenset({"not", "!"})
_BITWISE_NOT_OPS = frozenset({"~"})
_LENGTH_OPS = frozenset({"#"})
_IDENTITY_OPS = frozenset({"!!"})


def _scalar_name(t: TypeExpr) -> str:
    """Extract scalar name from TypeExpr, or empty string."""
    return t.name if isinstance(t, ScalarType) else ""


class DefaultUnopCoercion:
    """No-op coercion with basic result type inference."""

    def coerce(self, op: str, operand: TypedValue) -> TypedValue:
        return operand

    def result_type(self, op: str, operand: TypedValue) -> TypeExpr:
        if op in _LOGICAL_NOT_OPS:
            return scalar("Bool")
        if op in _LENGTH_OPS:
            return scalar("Int")
        if op in _IDENTITY_OPS:
            return operand.type

        operand_name = _scalar_name(operand.type)
        if op in _NEGATION_OPS and operand_name in ("Int", "Float"):
            return operand.type
        if op in _BITWISE_NOT_OPS and operand_name == "Int":
            return scalar("Int")
        return UNKNOWN
