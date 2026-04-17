# pyright: standard
"""TypeName — typed wrapper for any type name (user-defined or built-in)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TypeName:
    """A type name, wrapping a string with domain semantics.

    Used for both foundation type names (via FoundationTypeName constants)
    and user-defined type names (e.g. 'Celsius', 'Meters').
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(
                f"TypeName.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TypeName):
            return self.value == other.value
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, TypeName):
            return self.value < other.value
        return NotImplemented
