"""A MOVE sender as each receiver takes it, chosen once from the sending item."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.cobol_types import CobolDataCategory
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.data_layout import FieldLayout
from interpreter.register import Register


@dataclass(frozen=True)
class MoveSource:
    """The sender's value; what a character receiver takes (a numeric sender's
    digit image); what a numeric receiver takes (a numeric-edited sender's
    de-edited value); and whether the sender is a group item, whose move fills
    the receiver as characters. A reference-modified receiver takes the value."""

    value: Register
    characters: Register
    number: Register
    group: bool

    def value_for(self, target: RefModOperand, fl: FieldLayout) -> Register:
        if target.is_reference_modified:
            return self.value
        if fl.type_descriptor.holds_characters:
            return self.characters
        return self.number

    def storage_for(self, target: RefModOperand, fl: FieldLayout) -> FieldLayout:
        if not self.group or target.is_reference_modified:
            return fl
        if fl.type_descriptor.category == CobolDataCategory.ALPHANUMERIC:
            return fl
        return fl.as_characters()


def plain_move_source(value: Register) -> MoveSource:
    return MoveSource(value=value, characters=value, number=value, group=False)
