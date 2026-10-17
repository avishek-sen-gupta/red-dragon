# pyright: standard
"""The program's decimal point character for numeric literals, which DECIMAL-POINT IS COMMA sets."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_PROCEDURE_DIVISION = frozenset(
    {"sections", "paragraphs", "statements", "declaratives"}
)
_COMMA_POINT_LITERAL = re.compile(r"[+-]?[0-9]*,[0-9]+([eE][+-]?[0-9]+)?")


@dataclass(frozen=True)
class DecimalPoint:
    """Rewrites a program's numeric literals as written into the period form lowering reads."""

    is_comma: bool

    def numeric_literal(self, text: str) -> str:
        return text.replace(",", ".") if self.is_comma else text

    def operand(self, text: str) -> str:
        if self.is_comma and _COMMA_POINT_LITERAL.fullmatch(text):
            return text.replace(",", ".")
        return text

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
                return self.operand(node)
            case Mapping():
                return {name: self._operands(value) for name, value in node.items()}
            case _:
                return self._items(node)

    def _items(self, node: Sequence | int | float) -> list | int | float:
        match node:
            case Sequence():
                return [self._operands(value) for value in node]
            case _:
                return node


PERIOD_POINT = DecimalPoint(is_comma=False)
