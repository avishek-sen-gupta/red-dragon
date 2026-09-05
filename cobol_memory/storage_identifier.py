# pyright: standard
"""StorageIdentifier — protocol for named storage locations (variables and registers)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cobol_memory.abstract_location import AbstractLocation


@runtime_checkable
class StorageIdentifier(AbstractLocation, Protocol):
    """A named location where a value can live — either a variable or a register.

    Both VarName and Register satisfy this protocol structurally.
    Use isinstance(x, StorageIdentifier) for runtime checks.
    """

    def is_present(self) -> bool: ...

    def __str__(self) -> str: ...

    def __hash__(self) -> int: ...
