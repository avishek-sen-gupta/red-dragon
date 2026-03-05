"""DefaultConversionRules — sensible type coercion for the default type ontology."""

from __future__ import annotations

import logging
import math
from typing import Any, Callable

from interpreter.constants import TypeName
from interpreter.conversion_rules import ConversionRules
from interpreter.conversion_result import (
    ConversionResult,
    IDENTITY_CONVERSION,
    _identity,
)

logger = logging.getLogger(__name__)

_ARITHMETIC_OPS = frozenset({"+", "-", "*"})
_COMPARISON_OPS = frozenset({"==", "!=", "<", ">", "<=", ">="})


def _to_float(x: Any) -> float:
    return float(x)


def _to_int(x: Any) -> int:
    return int(x)


def _truncate_to_int(x: Any) -> int:
    """Truncate toward zero — matches C/Java/COBOL integer assignment semantics."""
    return math.trunc(x)


class DefaultConversionRules(ConversionRules):
    """Default coercion table for the standard type ontology.

    Handles Int/Float promotion, Int division → floor division,
    Bool→Int promotion, and comparison result typing.
    """

    def resolve(
        self, operator: str, left_type: str, right_type: str
    ) -> ConversionResult:
        if operator in _COMPARISON_OPS:
            return ConversionResult(result_type=TypeName.BOOL)

        if operator in _ARITHMETIC_OPS:
            return self._resolve_arithmetic(operator, left_type, right_type)

        if operator == "/":
            return self._resolve_division(left_type, right_type)

        if operator == "%":
            return self._resolve_modulo(left_type, right_type)

        return IDENTITY_CONVERSION

    def _resolve_arithmetic(
        self, operator: str, left_type: str, right_type: str
    ) -> ConversionResult:
        pair = (left_type, right_type)

        if pair == (TypeName.INT, TypeName.INT):
            return ConversionResult(result_type=TypeName.INT)

        if pair == (TypeName.INT, TypeName.FLOAT):
            return ConversionResult(result_type=TypeName.FLOAT, left_coercer=_to_float)

        if pair == (TypeName.FLOAT, TypeName.INT):
            return ConversionResult(result_type=TypeName.FLOAT, right_coercer=_to_float)

        if pair == (TypeName.FLOAT, TypeName.FLOAT):
            return ConversionResult(result_type=TypeName.FLOAT)

        # Bool promotion
        if pair == (TypeName.BOOL, TypeName.INT):
            return ConversionResult(result_type=TypeName.INT, left_coercer=_to_int)

        if pair == (TypeName.INT, TypeName.BOOL):
            return ConversionResult(result_type=TypeName.INT, right_coercer=_to_int)

        return IDENTITY_CONVERSION

    def _resolve_division(self, left_type: str, right_type: str) -> ConversionResult:
        pair = (left_type, right_type)

        if pair == (TypeName.INT, TypeName.INT):
            return ConversionResult(result_type=TypeName.INT, operator_override="//")

        if pair == (TypeName.INT, TypeName.FLOAT):
            return ConversionResult(result_type=TypeName.FLOAT, left_coercer=_to_float)

        if pair == (TypeName.FLOAT, TypeName.INT):
            return ConversionResult(result_type=TypeName.FLOAT, right_coercer=_to_float)

        if pair == (TypeName.FLOAT, TypeName.FLOAT):
            return ConversionResult(result_type=TypeName.FLOAT)

        return IDENTITY_CONVERSION

    def _resolve_modulo(self, left_type: str, right_type: str) -> ConversionResult:
        pair = (left_type, right_type)

        if pair == (TypeName.INT, TypeName.INT):
            return ConversionResult(result_type=TypeName.INT)

        return IDENTITY_CONVERSION

    def coerce_assignment(
        self, value_type: str, target_type: str
    ) -> Callable[[Any], Any]:
        if value_type == target_type:
            return _identity

        pair = (value_type, target_type)

        # Narrowing: Float → Int (truncate toward zero)
        if pair == (TypeName.FLOAT, TypeName.INT):
            return _truncate_to_int

        # Widening: Int → Float
        if pair == (TypeName.INT, TypeName.FLOAT):
            return _to_float

        # Bool → Int promotion
        if pair == (TypeName.BOOL, TypeName.INT):
            return _to_int

        return _identity
