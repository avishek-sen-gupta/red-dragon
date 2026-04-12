# pyright: standard
"""PathName — typed wrapper for file/module path identifiers.

Follows the VarName/FuncName/FieldName pattern: frozen dataclass,
__post_init__ validation, is_present() protocol, null-object singleton.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PathName:
    """A source-level or resolved module path."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise TypeError(
                f"PathName.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def is_present(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PathName):
            return self.value == other.value
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, PathName):
            return self.value < other.value
        return NotImplemented


@dataclass(frozen=True, eq=False)
class NoPathName(PathName):
    """Null object: no path name."""

    value: str = ""

    def is_present(self) -> bool:
        return False


NO_PATH_NAME = NoPathName()
