"""FunctionSignature — immutable record of a function's parameter types and return type."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FunctionSignature:
    """Complete type signature for a function.

    params: tuple of (name, type) pairs, e.g. (("a", "Int"), ("b", "Int"))
    return_type: canonical return type, e.g. "Int", or "" if unknown
    """

    params: tuple[tuple[str, str], ...]
    return_type: str
