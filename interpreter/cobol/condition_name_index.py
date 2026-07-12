# pyright: standard
"""Condition name index — maps level-88 condition names to parent fields.

Builds a lookup from condition names to their parent field name and
associated values, enabling condition_lowering to expand bare condition
name references (e.g. IF STATUS-ACTIVE) into parent field comparisons.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from interpreter.cobol.condition_name import ConditionValue
from interpreter.cobol.data_layout import DataLayout

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConditionEntry:
    """A resolved condition name entry linking to its parent field.

    Attributes:
        parent_field_name: Name of the parent field this condition tests.
        values: List of discrete values and/or THRU ranges.
    """

    parent_field_name: str
    values: list[ConditionValue] = field(default_factory=list)


class ConditionNameIndex:
    """Index mapping condition names to their parent field and values.

    Provides O(1) lookup of condition names for use in condition lowering.
    """

    def __init__(self, entries: dict[str, ConditionEntry]) -> None:
        self._entries = entries

    def lookup(self, name: str) -> ConditionEntry:
        """Look up a condition name. Returns entry with empty parent if not found."""
        return self._entries.get(
            name,
            ConditionEntry(parent_field_name=""),
        )

    def has_condition(self, name: str) -> bool:
        return name in self._entries

    @property
    def entries(self) -> dict[str, ConditionEntry]:
        return dict(self._entries)


def build_condition_index(layout: DataLayout) -> ConditionNameIndex:
    """Build a condition name index from a recursive DataLayout.

    Iterates all leaf fields depth-first and collects their level-88
    conditions into a lookup keyed by condition name.

    Args:
        layout: DataLayout (from build_data_layout).

    Returns:
        A ConditionNameIndex for use in condition lowering.
    """
    entries: dict[str, ConditionEntry] = {}

    for fl in layout.all_leaves():
        for condition in fl.conditions:
            entries[condition.name] = ConditionEntry(
                parent_field_name=fl.name,
                values=condition.values,
            )

    for group_name, condition in layout.all_group_conditions():
        entries[condition.name] = ConditionEntry(
            parent_field_name=group_name,
            values=condition.values,
        )

    logger.debug("Condition name index: %d entries", len(entries))
    return ConditionNameIndex(entries)
