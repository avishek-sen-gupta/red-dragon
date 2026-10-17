"""One position of a numeric edit picture, with the facts its PICTURE fixes."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.edit_cell_kind import EditCellKind
from cobol_asg.edit_slot import EditSlot


@dataclass(frozen=True)
class EditCell:
    """``char`` is a FIXED or INSERTION cell's character, or the character a
    SIGN cell shows for a value that is not negative. ``digits_before`` counts
    the digit positions left of this one, so a DIGIT or SUPPRESSED cell shows
    digit number ``digits_before``. ``slot_digit`` is the digit a BEFORE_DIGIT
    slot waits for."""

    kind: EditCellKind
    char: str = ""
    digits_before: int = 0
    slot: EditSlot = EditSlot.NONE
    slot_digit: int = 0
