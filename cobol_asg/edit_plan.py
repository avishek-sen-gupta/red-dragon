"""Everything a numeric edit picture fixes about the image it shows, leaving only the value to run time."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.edit_cell import EditCell


@dataclass(frozen=True)
class EditPlan:
    """The picture's cells, left to right, before any CR / DB; its digit counts;
    the image of a zero value when every digit position is suppressible; the
    fill character; the floating symbol with the digits that can carry it; and
    the trailing CR / DB."""

    cells: tuple[EditCell, ...]
    digit_count: int
    fraction_digits: int
    integer_digits: int
    signed: bool
    all_suppressible: bool
    zero_image: str
    fill: str
    float_symbol: str
    float_digits: tuple[int, ...]
    trailing_sign: str
