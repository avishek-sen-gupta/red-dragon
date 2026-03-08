"""ConversionResult — describes how to coerce operands and override operators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from interpreter.type_expr import TypeExpr, UNKNOWN


def _identity(x: Any) -> Any:
    return x


@dataclass(frozen=True)
class ConversionResult:
    """The outcome of resolving type coercion for a binary operation.

    Fields:
        result_type: The type of the result as a TypeExpr (e.g.,
                     ``ScalarType("Float")``). ``UNKNOWN`` means
                     "use Python's native type".
        left_coercer: Applied to the left operand before evaluation.
        right_coercer: Applied to the right operand before evaluation.
        operator_override: If non-empty, replaces the original operator
                          (e.g. "/" becomes "//" for Int/Int division).
    """

    result_type: TypeExpr = UNKNOWN
    left_coercer: Callable[[Any], Any] = _identity
    right_coercer: Callable[[Any], Any] = _identity
    operator_override: str = ""


IDENTITY_CONVERSION = ConversionResult()
