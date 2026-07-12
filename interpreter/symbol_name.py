# pyright: standard
"""SymbolName — untyped lookup key for named symbols at module boundaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolName:
    """A symbol name used as a lookup key at module-import boundaries.

    Intentionally unrelated to ClassName/FuncName/VarName — it serves as a
    neutral translation target when the symbol kind is not known at lookup
    time (e.g. a LOAD_FIELD field_name that could be a class or a function).
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(
                f"SymbolName.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SymbolName):
            return self.value == other.value
        return NotImplemented
