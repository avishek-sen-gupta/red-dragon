# pyright: standard
"""FieldExtent — a COBOL field as a byte range, and how ranges alias.

A COBOL field is not a variable: it is a slice of a section's region buffer.
Two fields alias exactly when their byte ranges intersect within the same
region, which subsumes group/elementary containment, REDEFINES, RENAMES,
OCCURS elements and reference modification without a rule for each.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from interpreter.cobol.region_id import RegionId


class Precision(Enum):
    """How exactly the extent locates the access."""

    EXACT = auto()
    """The access covers precisely this range (literal or absent subscript)."""

    CLAMPED = auto()
    """The access lands somewhere inside this range (computed subscript).

    A CLAMPED extent can never must_cover anything: we know where it might
    be, not where it is.
    """


@dataclass(frozen=True)
class FieldExtent:
    """A byte range within one COBOL region buffer.

    Contract (mirrors ``AbstractLocation``): ``must_cover(x)`` implies
    ``may_alias(x)`` — a write that definitely overwrites another extent
    necessarily might be observed by a read of it. ``must_cover`` is an
    under-approximation (False when unsure, never a false killer);
    ``may_alias`` is an over-approximation (True when unsure).
    """

    region: RegionId
    start: int
    length: int
    precision: Precision
    field_name: str

    @property
    def end(self) -> int:
        """Exclusive end offset."""
        return self.start + self.length

    def may_alias(self, other: object) -> bool:
        if not isinstance(other, FieldExtent) or other.region is not self.region:
            return False
        if self.length <= 0 or other.length <= 0:
            return False
        return self.start < other.end and other.start < self.end

    def must_cover(self, other: object) -> bool:
        if not isinstance(other, FieldExtent) or other.region is not self.region:
            return False
        if self.precision is not Precision.EXACT:
            return False
        if self.length <= 0 or other.length <= 0:
            return False
        return self.start <= other.start and other.end <= self.end

    def alias_key(self) -> tuple[str, str]:
        """Bucket by REGION only — never by byte offset.

        The KILL step narrows candidates by this key and then filters with
        must_cover. If this bucketed by offset, a must-covering extent at a
        different offset could fall outside the bucket and escape KILL
        entirely — a silently dropped dependency. See
        ``interpreter.abstract_location.AbstractLocation.alias_key``.
        """
        return ("extent", self.region.value)

    def is_present(self) -> bool:
        """A FieldExtent always denotes concrete storage, once constructed."""
        return True

    def __str__(self) -> str:
        return f"{self.field_name}@{self.region.value}[{self.start}:{self.end}]"
