"""TypeResolver — composes ConversionRules to resolve BINOP type coercion."""

from __future__ import annotations

import logging

from interpreter.conversion_rules import ConversionRules
from interpreter.conversion_result import ConversionResult, IDENTITY_CONVERSION

logger = logging.getLogger(__name__)


class TypeResolver:
    """Resolves binary operation type coercion by delegating to ConversionRules.

    Logic:
    - Both hints empty → identity (current VM behavior, no coercion).
    - One hint missing → assume the other's type (symmetric).
    - Both present → delegate to the injected ConversionRules.
    """

    def __init__(self, conversion_rules: ConversionRules) -> None:
        self._conversion_rules = conversion_rules

    def resolve_binop(
        self, operator: str, left_hint: str, right_hint: str
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
