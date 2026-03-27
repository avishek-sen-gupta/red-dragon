"""FieldName — typed field/property name with access-pattern tag."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FieldKind(Enum):
    PROPERTY = "property"
    INDEX = "index"
    SPECIAL = "special"


@dataclass(frozen=True)
class FieldName:
    """A field/property name, tagged with its access pattern."""

    value: str
    kind: FieldKind = FieldKind.PROPERTY

    def __post_init__(self):
        if not isinstance(self.value, str):
            raise TypeError(
                f"FieldName.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def is_present(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash((self.value, self.kind))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FieldName):
            return self.value == other.value and self.kind == other.kind
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, FieldName):
            return (self.value, self.kind.value) < (other.value, other.kind.value)
        return NotImplemented

    def __contains__(self, item: str) -> bool:
        return item in self.value

    def startswith(self, prefix: str) -> bool:
        return self.value.startswith(prefix)


@dataclass(frozen=True, eq=False)
class NoFieldName(FieldName):
    """Null object: no field name. Use .is_present() for null checks."""

    value: str = ""
    kind: FieldKind = FieldKind.PROPERTY

    def is_present(self) -> bool:
        return False


NO_FIELD_NAME = NoFieldName()
