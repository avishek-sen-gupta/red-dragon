# pyright: standard
"""DefaultTypeConversionRules — sensible type coercion for the default type ontology."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from typing import Any

from interpreter.constants import FoundationTypeName
from interpreter.types.coercion.conversion_result import (
    IDENTITY_CONVERSION,
    ConversionResult,
    _identity,
)
from interpreter.types.coercion.conversion_rules import TypeConversionRules
from interpreter.types.type_expr import TypeExpr, scalar

logger = logging.getLogger(__name__)

_ARITHMETIC_OPS = frozenset({"+", "-", "*"})
_COMPARISON_OPS = frozenset({"==", "!=", "<", ">", "<=", ">="})


def _to_float(
    x: Any,
) -> float:  # Any: display boundary — coerces heterogeneous runtime values
    return float(x)


def _to_int(
    x: Any,
) -> int:  # Any: display boundary — coerces heterogeneous runtime values
    return int(x)


def _truncate_to_int(
    x: Any,
) -> int:  # Any: display boundary — coerces heterogeneous runtime values
    """Truncate toward zero — matches C/Java/COBOL integer assignment semantics."""
    return math.trunc(x)


class DefaultTypeConversionRules(TypeConversionRules):
    """Default coercion table for the standard type ontology.

    Handles Int/Float promotion, Int division → floor division,
    Bool→Int promotion, and comparison result typing.
    """

    def resolve(
        self, operator: str, left_type: TypeExpr, right_type: TypeExpr
    ) -> ConversionResult:
        if operator in _COMPARISON_OPS:
            return ConversionResult(result_type=scalar(FoundationTypeName.BOOL))

        if operator in _ARITHMETIC_OPS:
            return self._resolve_arithmetic(operator, left_type, right_type)

        if operator == "/":
            return self._resolve_division(left_type, right_type)

        if operator == "%":
            return self._resolve_modulo(left_type, right_type)

        return IDENTITY_CONVERSION

    def _resolve_arithmetic(
        self, operator: str, left_type: TypeExpr, right_type: TypeExpr
    ) -> ConversionResult:
        pair = (left_type, right_type)

        if pair == (FoundationTypeName.INT, FoundationTypeName.INT):
            return ConversionResult(result_type=scalar(FoundationTypeName.INT))

        if pair == (FoundationTypeName.INT, FoundationTypeName.FLOAT):
            return ConversionResult(
                result_type=scalar(FoundationTypeName.FLOAT), left_coercer=_to_float
            )

        if pair == (FoundationTypeName.FLOAT, FoundationTypeName.INT):
            return ConversionResult(
                result_type=scalar(FoundationTypeName.FLOAT), right_coercer=_to_float
            )

        if pair == (FoundationTypeName.FLOAT, FoundationTypeName.FLOAT):
            return ConversionResult(result_type=scalar(FoundationTypeName.FLOAT))

        # Bool promotion
        if pair == (FoundationTypeName.BOOL, FoundationTypeName.INT):
            return ConversionResult(
                result_type=scalar(FoundationTypeName.INT), left_coercer=_to_int
            )

        if pair == (FoundationTypeName.INT, FoundationTypeName.BOOL):
            return ConversionResult(
                result_type=scalar(FoundationTypeName.INT), right_coercer=_to_int
            )

        return IDENTITY_CONVERSION

    def _resolve_division(
        self, left_type: TypeExpr, right_type: TypeExpr
    ) -> ConversionResult:
        pair = (left_type, right_type)

        if pair == (FoundationTypeName.INT, FoundationTypeName.INT):
            return ConversionResult(
                result_type=scalar(FoundationTypeName.INT), operator_override="//"
            )

        if pair == (FoundationTypeName.INT, FoundationTypeName.FLOAT):
            return ConversionResult(
                result_type=scalar(FoundationTypeName.FLOAT), left_coercer=_to_float
            )

        if pair == (FoundationTypeName.FLOAT, FoundationTypeName.INT):
            return ConversionResult(
                result_type=scalar(FoundationTypeName.FLOAT), right_coercer=_to_float
            )

        if pair == (FoundationTypeName.FLOAT, FoundationTypeName.FLOAT):
            return ConversionResult(result_type=scalar(FoundationTypeName.FLOAT))

        return IDENTITY_CONVERSION

    def _resolve_modulo(
        self, left_type: TypeExpr, right_type: TypeExpr
    ) -> ConversionResult:
        pair = (left_type, right_type)

        if pair == (FoundationTypeName.INT, FoundationTypeName.INT):
            return ConversionResult(result_type=scalar(FoundationTypeName.INT))

        return IDENTITY_CONVERSION

    def coerce_assignment(
        self, value_type: TypeExpr, target_type: TypeExpr
    ) -> Callable[[Any], Any]:  # Any: display boundary — see pre_triage issue
        if value_type == target_type:
            return _identity

        pair = (value_type, target_type)

        # Narrowing: Float → Int (truncate toward zero)
        if pair == (FoundationTypeName.FLOAT, FoundationTypeName.INT):
            return _truncate_to_int

        # Widening: Int → Float
        if pair == (FoundationTypeName.INT, FoundationTypeName.FLOAT):
            return _to_float

        # Bool → Int promotion
        if pair == (FoundationTypeName.BOOL, FoundationTypeName.INT):
            return _to_int

        return _identity
