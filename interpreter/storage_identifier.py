"""StorageIdentifier — protocol for named storage locations (variables and registers)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageIdentifier(Protocol):
    """A named location where a value can live — either a variable or a register.

    Both VarName and Register satisfy this protocol structurally.
    Use isinstance(x, StorageIdentifier) for runtime checks.
    """

    @property
    def value(self) -> str: ...

    def is_present(self) -> bool: ...

    def __str__(self) -> str: ...

    def __hash__(self) -> int: ...
