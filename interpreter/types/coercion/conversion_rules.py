"""TypeConversionRules — ABC for type-driven operator and assignment coercion."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from interpreter.types.coercion.conversion_result import ConversionResult
from interpreter.types.type_expr import TypeExpr


class TypeConversionRules(ABC):
    """Abstract base for rules that map (operator, left_type, right_type)
    to a ConversionResult describing operand coercion and operator overrides,
    and (value_type, target_type) to an assignment coercer.
    """

    @abstractmethod
    def resolve(
        self, operator: str, left_type: TypeExpr, right_type: TypeExpr
    ) -> ConversionResult: ...

    @abstractmethod
    def coerce_assignment(
        self, value_type: TypeExpr, target_type: TypeExpr
    ) -> Callable[[Any], Any]:
        """Return a function that coerces a value of value_type into target_type.

        For example, Float → Int returns math.trunc, Int → Float returns float().
        When no coercion is needed (same type, unknown types), returns identity.
        """
        ...
