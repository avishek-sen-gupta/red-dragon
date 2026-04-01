# pyright: standard
"""VarName — typed variable name with domain semantics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VarName:
    """A variable name, wrapping a string with domain semantics."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(
                f"VarName.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def is_present(self) -> bool:
        return True

    @property
    def is_self(self) -> bool:
        # "self" — Python, Ruby, Lua, Scala
        # "this" — Java, C#, C++, Kotlin, JS/TS
        # "$this" — PHP
        return self.value in ("self", "this", "$this")

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, VarName):
            return self.value == other.value
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, VarName):
            return self.value < other.value
        return NotImplemented

    def __contains__(self, item: str) -> bool:
        return item in self.value

    def startswith(self, prefix: str) -> bool:
        return self.value.startswith(prefix)


@dataclass(frozen=True, eq=False)
class NoVarName(VarName):
    """Null object: no variable name."""

    value: str = ""

    def is_present(self) -> bool:
        return False


NO_VAR_NAME = NoVarName()
