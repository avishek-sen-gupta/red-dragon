# pyright: standard
"""AbstractLocation — the alias relation between storage locations.

Reaching definitions asks one question of two accesses: do they touch the
same storage? For named locations (registers, variables) the answer is name
equality. For COBOL fields — byte slices of a shared region buffer — it is
byte-range overlap. Both are instances of this protocol, so one analysis
serves both.
"""

from __future__ import annotations

from typing import Hashable, Protocol, runtime_checkable


@runtime_checkable
class AbstractLocation(Protocol):
    """A storage location that knows how it aliases other locations."""

    def may_alias(self, other: AbstractLocation) -> bool:
        """True if a write here MIGHT be observed by a read of ``other``.

        Over-approximating: when in doubt, return True. Used to build GEN and
        to match uses against reaching definitions.
        """
        ...

    def must_cover(self, other: AbstractLocation) -> bool:
        """True if a write here DEFINITELY overwrites all of ``other``.

        Under-approximating: when in doubt, return False. Only a must-cover
        write may KILL a definition; returning True wrongly silently drops
        dependencies.
        """
        ...

    def alias_key(self) -> Hashable:
        """A coarse bucket key. Two locations that may alias MUST share a key.

        Lets the analysis narrow candidates by dict lookup before doing the
        pairwise overlap test.
        """
        ...
