"""NullTypeResolver — always returns identity, preserving current VM behavior."""

from __future__ import annotations

from typing import Any, Callable

from interpreter.types.coercion.conversion_result import (
    ConversionResult,
    IDENTITY_CONVERSION,
    _identity,
)
from interpreter.types.coercion.identity_conversion_rules import IdentityConversionRules
from interpreter.types.type_expr import TypeExpr
from interpreter.types.type_resolver import TypeResolver


class NullTypeResolver(TypeResolver):
    """Null-object TypeResolver: ignores type hints entirely.

    The VM uses this by default. All operations use Python's native
    semantics with no coercion or operator overrides.
    """

    def __init__(self) -> None:
        super().__init__(IdentityConversionRules())

    def resolve_binop(
        self, operator: str, left_hint: TypeExpr, right_hint: TypeExpr
    ) -> ConversionResult:
        return IDENTITY_CONVERSION

    def resolve_assignment(
        self, value_hint: TypeExpr, target_hint: TypeExpr
    ) -> Callable[[Any], Any]:
        return _identity
