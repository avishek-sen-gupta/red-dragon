"""TypeResolver — composes TypeConversionRules to resolve BINOP and assignment coercion."""

from __future__ import annotations

import logging
from typing import Any, Callable

from interpreter.types.coercion.conversion_rules import TypeConversionRules
from interpreter.types.coercion.conversion_result import (
    ConversionResult,
    IDENTITY_CONVERSION,
    _identity,
)
from interpreter.types.type_expr import TypeExpr

logger = logging.getLogger(__name__)


class TypeResolver:
    """Resolves type coercion for binary operations and assignments.

    BINOP logic:
    - Both hints falsy (UNKNOWN) → identity (current VM behavior, no coercion).
    - One hint missing → assume the other's type (symmetric).
    - Both present → delegate to the injected TypeConversionRules.

    Assignment logic:
    - Either hint falsy → identity (no coercion without both types known).
    - Both present → delegate to TypeConversionRules.coerce_assignment().
    """

    def __init__(self, conversion_rules: TypeConversionRules) -> None:
        self._conversion_rules = conversion_rules

    def resolve_binop(
        self, operator: str, left_hint: TypeExpr, right_hint: TypeExpr
    ) -> ConversionResult:
        if not left_hint and not right_hint:
            return IDENTITY_CONVERSION

        effective_left = left_hint or right_hint
        effective_right = right_hint or left_hint

        logger.debug(
            "resolve_binop: %s %s %s → delegating to rules",
            effective_left,
            operator,
            effective_right,
        )
        return self._conversion_rules.resolve(operator, effective_left, effective_right)

    def resolve_assignment(
        self, value_hint: TypeExpr, target_hint: TypeExpr
    ) -> Callable[[Any], Any]:
        if not value_hint or not target_hint:
            return _identity

        logger.debug(
            "resolve_assignment: %s → %s, delegating to rules",
            value_hint,
            target_hint,
        )
        return self._conversion_rules.coerce_assignment(value_hint, target_hint)
