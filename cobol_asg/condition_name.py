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


@dataclass(frozen=True)
class ConditionValue:
    """A single value or range in a level-88 condition.

    Attributes:
        from_val: The starting (or only) value.
        to_val: The ending value for a THRU range, or empty string if discrete.
    """

    from_val: str
    to_val: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> ConditionValue:
        return cls(
            from_val=data.get("from", ""),
            to_val=data.get("to", ""),
        )

    def to_dict(self) -> dict:
        return {"from": self.from_val, "to": self.to_val}

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
    def from_dict(cls, data: dict) -> ConditionName:
        return cls(
            name=data.get("name", ""),
            values=[ConditionValue.from_dict(v) for v in data.get("values", [])],
        )

    def to_dict(self) -> dict:
        result: dict = {"name": self.name}
        if self.values:
            result["values"] = [v.to_dict() for v in self.values]
        return result
