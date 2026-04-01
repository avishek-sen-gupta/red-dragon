# pyright: standard
"""FuncName — typed function/method name."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class FuncName:
    """A function or method name."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(
                f"FuncName.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def is_present(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FuncName):
            return self.value == other.value
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, FuncName):
            return self.value < other.value
        return NotImplemented

    def startswith(self, prefix: str) -> bool:
        return self.value.startswith(prefix)

    def __contains__(self, item: str) -> bool:
        return item in self.value


@dataclass(frozen=True, eq=False)
class NoFuncName(FuncName):
    """Null object: no function name."""

    value: str = ""

    def is_present(self) -> bool:
        return False


NO_FUNC_NAME = NoFuncName()
