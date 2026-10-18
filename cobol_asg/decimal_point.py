# pyright: standard
"""The program's decimal point character for numeric literals, which DECIMAL-POINT IS COMMA sets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_PROCEDURE_DIVISION = frozenset(
    {"sections", "paragraphs", "statements", "declaratives"}
)
_LITERAL_TEXT = ("name", "value")


@dataclass(frozen=True)
class DecimalPoint:
    """Rewrites a program's numeric literals as written into the period form lowering reads."""

    is_comma: bool

    def numeric_literal(self, text: str) -> str:
        return text.replace(",", ".") if self.is_comma else text

    def program(self, data: Mapping) -> dict:
        if not self.is_comma:
            return dict(data)
        return {
            name: self._operands(value) if name in _PROCEDURE_DIVISION else value
            for name, value in data.items()
        }

    def _operands(
        self, node: Mapping | Sequence | int | float
    ) -> dict | list | str | int | float:
        match node:
            case str():
                return node
            case Mapping():
                return self._operand(node)
            case _:
                return self._items(node)

    def _operand(self, node: Mapping) -> dict:
        """A node the bridge marks ``"numeric"`` holds a numeric literal as written."""
        walked = {name: self._operands(value) for name, value in node.items()}
        if not node.get("numeric", False):
            return walked
        return walked | {
            name: self.numeric_literal(walked[name])
            for name in _LITERAL_TEXT
            if name in walked
        }

    def _items(self, node: Sequence | int | float) -> list | int | float:
        match node:
            case Sequence():
                return [self._operands(value) for value in node]
            case _:
                return node


PERIOD_POINT = DecimalPoint(is_comma=False)
