# pyright: standard
"""AbstractLocation — the alias relation between storage locations.

Reaching definitions asks one question of two accesses: do they touch the
same storage? For named locations (registers, variables) the answer is name
equality. For COBOL fields — byte slices of a shared region buffer — it is
byte-range overlap. Both are instances of this protocol, so one analysis
serves both.
"""

from __future__ import annotations

from collections.abc import Hashable
from typing import Protocol, runtime_checkable


@runtime_checkable
class AbstractLocation(Protocol):
    """A storage location that knows how it aliases other locations.

    Combined contract: ``must_cover(x)`` implies ``may_alias(x)`` — a write
    that definitely overwrites another location necessarily might be observed
    by a read of it. Anything that keys off ``must_cover`` for correctness
    (e.g. KILL) therefore stays sound only if ``alias_key`` buckets
    must-covering locations together too (see ``alias_key`` below).
    """

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
        """A coarse bucket key.

        Any two locations where EITHER ``may_alias`` OR ``must_cover`` holds
        MUST share a key — not just may-aliasing pairs. Since
        ``must_cover(x)`` implies ``may_alias(x)``, this is really one
        requirement, but it is worth stating explicitly: a KILL lookup keyed
        by ``alias_key()`` and filtered by ``must_cover`` is only sound if a
        must-covered location can never fall outside the bucket. For COBOL
        ``FieldExtent``, this means bucketing by REGION, not by byte offset.

        Lets the analysis narrow candidates by dict lookup before doing the
        pairwise overlap test.
        """
        ...
