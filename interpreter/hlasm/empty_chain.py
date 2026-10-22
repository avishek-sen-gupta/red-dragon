# pyright: standard
"""The null chain: no items, and its own predecessor."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmptyChain[T]:
    """The chain before the first item."""

    @property
    def length(self) -> int:
        return 0

    @property
    def previous(self) -> EmptyChain[T]:
        return self

    def items(self) -> tuple[T, ...]:
        return ()
