# pyright: standard
"""Condition name types for COBOL level-88 condition names.

A level-88 entry defines named conditions on a parent field. Each condition
has one or more values (discrete or THRU ranges) that the parent field can
match. For example:

    05 WS-STATUS   PIC X(1).
       88 STATUS-ACTIVE   VALUE 'A'.
       88 STATUS-VALID    VALUE 'A' 'B' 'C'.
       88 STATUS-ALPHA    VALUE 'A' THRU 'Z'.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cobol_asg.decimal_point import PERIOD_POINT, DecimalPoint
from cobol_asg.nonnumeric_literal import literal_characters, written_literal


@dataclass(frozen=True)
class ConditionValue:
    """A single value or range in a level-88 condition.

    Attributes:
        from_val: The starting (or only) value: a nonnumeric literal's
            characters, a numeric literal's digits, a figurative constant's name.
        to_val: The ending value for a THRU range, or empty string if discrete.
        numeric / figurative: which kind of literal the value is written with.
    """

    from_val: str
    to_val: str = ""
    is_all: bool = False
    numeric: bool = False
    figurative: bool = False

    @classmethod
    def from_dict(
        cls, data: dict, decimal_point: DecimalPoint = PERIOD_POINT
    ) -> ConditionValue:
        numeric = data.get("numeric", False)
        figurative = data.get("figurative", False)
        literal = (
            decimal_point.numeric_literal
            if numeric
            else str if figurative else literal_characters
        )
        return cls(
            from_val=literal(data.get("from", "")),
            to_val=literal(data.get("to", "")),
            is_all=data.get("all", False),
            numeric=numeric,
            figurative=figurative,
        )

    def to_dict(self) -> dict:
        written = written_literal if self._nonnumeric else str
        return {
            "from": written(self.from_val),
            "to": written(self.to_val) if self.to_val else "",
            **({"all": True} if self.is_all else {}),
            **({"numeric": True} if self.numeric else {}),
            **({"figurative": True} if self.figurative else {}),
        }

    @property
    def _nonnumeric(self) -> bool:
        return not (self.numeric or self.figurative)

    @property
    def is_range(self) -> bool:
        return self.to_val != ""


@dataclass(frozen=True)
class ConditionName:
    """A named condition (level-88) attached to a parent field.

    Attributes:
        name: The condition name (e.g. "STATUS-ACTIVE").
        values: List of discrete values and/or THRU ranges.
    """

    name: str
    values: list[ConditionValue] = field(default_factory=list)

    @classmethod
    def from_dict(
        cls, data: dict, decimal_point: DecimalPoint = PERIOD_POINT
    ) -> ConditionName:
        return cls(
            name=data.get("name", ""),
            values=[
                ConditionValue.from_dict(v, decimal_point)
                for v in data.get("values", [])
            ],
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            **({"values": [v.to_dict() for v in self.values]} if self.values else {}),
        }
