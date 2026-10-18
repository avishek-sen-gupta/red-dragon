# pyright: standard
"""Figurative constants as written, read as the one name lowering knows each by."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

_PROCEDURE_DIVISION = frozenset(
    {"sections", "paragraphs", "statements", "declaratives"}
)
_FIGURATIVE = "figurative"

_CANONICAL = MappingProxyType(
    {
        "SPACE": "SPACES",
        "ZERO": "ZEROS",
        "ZEROES": "ZEROS",
        "LOW-VALUE": "LOW-VALUES",
        "HIGH-VALUE": "HIGH-VALUES",
        "QUOTE": "QUOTES",
        "NULLS": "NULL",
    }
)


def canonical_figurative(written: str) -> str:
    """SPACE and SPACES, ZERO, ZEROS and ZEROES, and so on, are one constant each
    (ANSI X3.23-1985 figurative constants); the plural form names it."""
    return _CANONICAL.get(written, written)


def with_canonical_figuratives(data: Mapping) -> dict:
    """The ASG with each procedure-division figurative-constant node named canonically."""
    return {
        name: _walked(value) if name in _PROCEDURE_DIVISION else value
        for name, value in data.items()
    }


def _walked(node: Mapping | Sequence | int | float) -> dict | list | str | int | float:
    match node:
        case str():
            return node
        case Mapping():
            return _node(node)
        case _:
            return _items(node)


def _items(node: Sequence | int | float) -> list | int | float:
    match node:
        case Sequence():
            return [_walked(value) for value in node]
        case _:
            return node


def _node(node: Mapping) -> dict:
    walked = {name: _walked(value) for name, value in node.items()}
    if node.get("kind") != _FIGURATIVE or "value" not in node:
        return walked
    return walked | {"value": canonical_figurative(node["value"])}
