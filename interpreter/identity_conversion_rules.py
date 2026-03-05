"""IdentityConversionRules — null-object ConversionRules that never coerces."""

from __future__ import annotations

from interpreter.conversion_rules import ConversionRules
from interpreter.conversion_result import ConversionResult, IDENTITY_CONVERSION


class IdentityConversionRules(ConversionRules):
    """Always returns identity coercers with no operator override.

    This is the null-object implementation: when the VM has no type
    awareness configured, all operations use Python's native semantics.
    """

    def resolve(
        self, operator: str, left_type: str, right_type: str
    ) -> ConversionResult:
        return IDENTITY_CONVERSION
