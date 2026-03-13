"""BinopCoercionStrategy — injectable language-specific pre-operation type coercion."""

from __future__ import annotations

from typing import Protocol

from interpreter.type_expr import UNKNOWN, ScalarType, TypeExpr, scalar
from interpreter.typed_value import TypedValue, typed

_COMPARISON_OPS = frozenset({"==", "!=", "<", ">", "<=", ">=", "===", "~="})
_C_FAMILY_LOGICAL_OPS = frozenset({"&&", "||"})
_CONCAT_OPS = frozenset({"..", "."})
_ARITHMETIC_OPS = frozenset({"+", "-", "*", "/", "//", "%", "**", "mod"})
_BITWISE_OPS = frozenset({"&", "|", "^", "~", "<<", ">>"})


class BinopCoercionStrategy(Protocol):
    """Pre-coerce operands and infer result type for binary operations."""

    def coerce(
        self, op: str, lhs: TypedValue, rhs: TypedValue
    ) -> tuple[TypedValue, TypedValue]:
        """Pre-coerce operands before operator application. Returns TypedValue.

        Contract: will never be called with SymbolicValue operands — the BINOP
        handler short-circuits symbolic operands before calling coerce().
        """
        ...

    def result_type(self, op: str, lhs: TypedValue, rhs: TypedValue) -> TypeExpr:
        """Infer result type from operator and operand types."""
        ...


def _scalar_name(t: TypeExpr) -> str:
    """Extract scalar name from TypeExpr, or empty string."""
    return t.name if isinstance(t, ScalarType) else ""


def _arithmetic_result(lhs_name: str, rhs_name: str) -> TypeExpr:
    """Infer arithmetic result type from operand type names."""
    if not lhs_name or not rhs_name:
        return UNKNOWN
    if lhs_name == "Float" or rhs_name == "Float":
        return scalar("Float")
    if lhs_name == "Int" and rhs_name == "Int":
        return scalar("Int")
    return UNKNOWN


class DefaultBinopCoercion:
    """No-op coercion with basic result type inference."""

    def coerce(
        self, op: str, lhs: TypedValue, rhs: TypedValue
    ) -> tuple[TypedValue, TypedValue]:
        return lhs, rhs

    def result_type(self, op: str, lhs: TypedValue, rhs: TypedValue) -> TypeExpr:
        if op in _COMPARISON_OPS:
            return scalar("Bool")
        if op in _C_FAMILY_LOGICAL_OPS:
            return scalar("Bool")
        if op in _CONCAT_OPS:
            return scalar("String")

        lhs_name = _scalar_name(lhs.type)
        rhs_name = _scalar_name(rhs.type)

        if op in _ARITHMETIC_OPS:
            # String + String -> String
            if lhs_name == "String" and rhs_name == "String" and op == "+":
                return scalar("String")
            return _arithmetic_result(lhs_name, rhs_name)
        if op in _BITWISE_OPS:
            return _arithmetic_result(lhs_name, rhs_name)
        # and/or, ?:, in, etc. — unknown
        return UNKNOWN


class JavaBinopCoercion:
    """Java-style coercion: auto-stringify for String + non-String."""

    def __init__(self) -> None:
        self._default = DefaultBinopCoercion()

    def coerce(
        self, op: str, lhs: TypedValue, rhs: TypedValue
    ) -> tuple[TypedValue, TypedValue]:
        if op == "+":
            string_type = scalar("String")
            lhs_str = _scalar_name(lhs.type) == "String"
            rhs_str = _scalar_name(rhs.type) == "String"
            if lhs_str and not rhs_str:
                return lhs, typed(str(rhs.value), string_type)
            if rhs_str and not lhs_str:
                return typed(str(lhs.value), string_type), rhs
        return lhs, rhs

    def result_type(self, op: str, lhs: TypedValue, rhs: TypedValue) -> TypeExpr:
        if op == "+":
            lhs_name = _scalar_name(lhs.type)
            rhs_name = _scalar_name(rhs.type)
            if lhs_name == "String" or rhs_name == "String":
                return scalar("String")
        return self._default.result_type(op, lhs, rhs)
