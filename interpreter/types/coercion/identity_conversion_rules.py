"""IdentityConversionRules — null-object TypeConversionRules that never coerces."""

from __future__ import annotations

from typing import Any, Callable

from interpreter.types.coercion.conversion_rules import TypeConversionRules
from interpreter.types.coercion.conversion_result import (
    ConversionResult,
    IDENTITY_CONVERSION,
    _identity,
)
from interpreter.types.type_expr import TypeExpr


class IdentityConversionRules(TypeConversionRules):
    """Always returns identity coercers with no operator override.

    This is the null-object implementation: when the VM has no type
    awareness configured, all operations use Python's native semantics.
    """

    def resolve(
        self, operator: str, left_type: TypeExpr, right_type: TypeExpr
    ) -> ConversionResult:
        return IDENTITY_CONVERSION

    def coerce_assignment(
        self, value_type: TypeExpr, target_type: TypeExpr
    ) -> Callable[[Any], Any]:
        return _identity
