# pyright: standard
"""Condition name index — maps level-88 condition names to parent fields.

Builds a lookup from condition names to their qualified parent items and
associated values, enabling condition_lowering to expand condition-name
references (e.g. IF STATUS-ACTIVE, IF B OF D32) into parent comparisons.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from cobol_asg.condition_name import ConditionName, ConditionValue
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.data_layout import (
    CobolAmbiguousReferenceError,
    DataItemMatch,
    DataLayout,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConditionEntry:
    """A level-88 condition-name and the data item it is subordinate to.

    Attributes:
        parent: The parent item, qualified by every group enclosing it
            (innermost first), so it resolves to that one item.
        values: List of discrete values and/or THRU ranges.
    """

    parent: RefModOperand
    values: list[ConditionValue] = field(default_factory=list)

    def qualified_by(self, qualifiers: Sequence[str]) -> bool:
        enclosing = iter(
            name.upper() for name in (self.parent.name, *self.parent.qualifiers)
        )
        return all(qualifier.upper() in enclosing for qualifier in qualifiers)


_UNKNOWN = ConditionEntry(parent=RefModOperand(name=""))


class ConditionNameIndex:
    """Index mapping each condition-name to every declaration of it.

    A condition-name may be declared under several items; a reference written
    with OF/IN qualifiers selects among them as a data-name's qualifiers do.
    """

    def __init__(self, entries: Mapping[str, tuple[ConditionEntry, ...]]) -> None:
        self._entries = {name.upper(): found for name, found in entries.items()}

    def lookup(self, name: str, qualifiers: Sequence[str] = ()) -> ConditionEntry:
        """The one declaration ``name`` qualified by ``qualifiers`` denotes, or an
        entry with an empty parent when there is none; more than one raises
        :class:`CobolAmbiguousReferenceError`."""
        found = tuple(
            entry
            for entry in self._entries.get(name.upper(), ())
            if entry.qualified_by(qualifiers)
        )
        if len(found) > 1:
            raise CobolAmbiguousReferenceError(name)
        return found[0] if found else _UNKNOWN

    def has_condition(self, name: str) -> bool:
        return name.upper() in self._entries

    @property
    def entries(self) -> dict[str, tuple[ConditionEntry, ...]]:
        return dict(self._entries)


def build_condition_index(layout: DataLayout) -> ConditionNameIndex:
    """Index every level-88 declared on an elementary or group item of ``layout``."""
    declared = [
        (condition.name.upper(), _entry(match, condition))
        for match in layout.items()
        for condition in match.item.conditions
    ]
    logger.debug("Condition name index: %d entries", len(declared))
    return ConditionNameIndex(
        {
            name: tuple(entry for other, entry in declared if other == name)
            for name, _ in declared
        }
    )


def _entry(match: DataItemMatch, condition: ConditionName) -> ConditionEntry:
    return ConditionEntry(
        parent=RefModOperand(
            name=match.name,
            qualifiers=tuple(name for name, _ in reversed(match.ancestors)),
        ),
        values=condition.values,
    )


def build_condition_index_over(layouts: Sequence[DataLayout]) -> ConditionNameIndex:
    """One index over several sections' layouts; on a name declared in more than
    one, the later layout's entries win."""
    return ConditionNameIndex(
        {
            name: entries
            for layout in layouts
            for name, entries in build_condition_index(layout).entries.items()
        }
    )
