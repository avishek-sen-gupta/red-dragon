# pyright: standard
"""ClosureId — typed closure environment identifier."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ClosureId:
    """A closure environment identifier (e.g., 'closure_42')."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(
                f"ClosureId.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def is_present(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ClosureId):
            return self.value == other.value
        return NotImplemented

    def __bool__(self) -> bool:
        return bool(self.value)

    def __contains__(self, item: str) -> bool:
        return item in self.value


@dataclass(frozen=True, eq=False)
class NoClosureId(ClosureId):
    """Null object: no closure binding."""

    value: str = ""

    def is_present(self) -> bool:
        return False


NO_CLOSURE_ID = NoClosureId()
