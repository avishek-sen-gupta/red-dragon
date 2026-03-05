"""ConversionRules — ABC for type-driven operator coercion."""

from __future__ import annotations

from abc import ABC, abstractmethod

from interpreter.conversion_result import ConversionResult


class ConversionRules(ABC):
    """Abstract base for rules that map (operator, left_type, right_type)
    to a ConversionResult describing operand coercion and operator overrides.
    """

    @abstractmethod
    def resolve(
        self, operator: str, left_type: str, right_type: str
    ) -> ConversionResult: ...
