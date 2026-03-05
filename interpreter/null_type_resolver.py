"""NullTypeResolver — always returns identity, preserving current VM behavior."""

from __future__ import annotations

from interpreter.conversion_result import ConversionResult, IDENTITY_CONVERSION
from interpreter.identity_conversion_rules import IdentityConversionRules
from interpreter.type_resolver import TypeResolver


class NullTypeResolver(TypeResolver):
    """Null-object TypeResolver: ignores type hints entirely.

    The VM uses this by default. All operations use Python's native
    semantics with no coercion or operator overrides.
    """

    def __init__(self) -> None:
        super().__init__(IdentityConversionRules())

    def resolve_binop(
        self, operator: str, left_hint: str, right_hint: str
    ) -> ConversionResult:
        return IDENTITY_CONVERSION
