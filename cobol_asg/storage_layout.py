"""Where each DATA DIVISION item lies: offsets, OCCURS element sizes and FD record areas."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from functools import reduce
from itertools import accumulate

from cobol_asg.cobol_field import CobolField

_BINARY_USAGES = frozenset({"COMP", "COMP-4", "BINARY", "COMP-5"})


def element_size(item: CobolField) -> int:
    """One occurrence's bytes: its allocated children's, else its own picture's."""
    allocated = [c for c in item.children if _allocates(c)]
    if not allocated:
        return item.type_descriptor.byte_length
    return sum(byte_length(c) for c in allocated)


def byte_length(item: CobolField) -> int:
    return element_size(item) * max(item.occurs, 1)


def _allocates(item: CobolField) -> bool:
    return not item.redefines and not item.renames_from.name


def _alignment(item: CobolField) -> int:
    """SYNCHRONIZED aligns a binary item on its own size; any other item on a byte."""
    if not item.synchronized or item.usage not in _BINARY_USAGES:
        return 1
    return item.type_descriptor.byte_length


def _redefined_offset(siblings: Sequence[CobolField], item: CobolField) -> int:
    """Where the item a REDEFINES names starts among its allocated siblings."""
    starts = accumulate(
        (byte_length(s) if _allocates(s) else 0 for s in siblings), initial=0
    )
    target = item.redefines.upper()
    return next(
        (
            start
            for s, start in zip(siblings, starts, strict=False)
            if s.name.upper() == target
        ),
        0,
    )


def _placed(item: CobolField, offset: int) -> CobolField:
    return replace(
        item,
        offset=offset,
        children=_children(item.children),
        element_size=element_size(item) if item.occurs > 0 else 0,
    )


@dataclass(frozen=True)
class _Siblings:
    """Children placed so far, and where the next allocated one may start."""

    placed: tuple[CobolField, ...]
    next_offset: int

    def then(self, child: CobolField, siblings: Sequence[CobolField]) -> _Siblings:
        if child.renames_from.name:
            return _Siblings((*self.placed, child), self.next_offset)
        start = self.next_offset + (-self.next_offset % _alignment(child))
        if child.redefines:
            placed = _placed(child, _redefined_offset(siblings, child))
            return _Siblings((*self.placed, placed), start)
        return _Siblings(
            (*self.placed, _placed(child, start)), start + byte_length(child)
        )


def _children(children: Sequence[CobolField]) -> list[CobolField]:
    laid = reduce(
        lambda acc, child: acc.then(child, children), children, _Siblings((), 0)
    )
    return list(laid.placed)


@dataclass(frozen=True)
class _Section:
    """Top-level items placed so far, where the current area starts and storage ends."""

    placed: tuple[CobolField, ...]
    area_start: int
    end: int

    def then(self, item: CobolField) -> _Section:
        if item.renames_from.name:
            return _Section((*self.placed, item), self.area_start, self.end)
        placed = (*self.placed, _placed(item, self.end))
        if item.redefines:
            longest = max(self.end, self.area_start + byte_length(item))
            return _Section(placed, self.area_start, longest)
        return _Section(placed, self.end, self.end + byte_length(item))


def section_layout(items: Sequence[CobolField]) -> list[CobolField]:
    """A storage section's top-level items, each after the last area laid out.

    A redefining top-level item is placed after storage laid out so far, as the
    bridge placed it; lowering positions it over its target by name.
    """
    return list(reduce(_Section.then, items, _Section((), 0, 0)).placed)


def file_section_layout(
    descriptions: Sequence[Sequence[CobolField]],
) -> list[CobolField]:
    """Each FD's records over one area as long as its longest; the areas end to end."""
    bases = accumulate((_area_length(records) for records in descriptions), initial=0)
    return [
        record if record.renames_from.name else _placed(record, base)
        for records, base in zip(descriptions, bases, strict=False)
        for record in records
    ]


def _area_length(records: Sequence[CobolField]) -> int:
    return max((byte_length(r) for r in records if not r.renames_from.name), default=0)
