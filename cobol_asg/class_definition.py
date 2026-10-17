"""A SPECIAL-NAMES CLASS clause: a class-name and the literals that define its set."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cobol_asg.alphabet_item import AlphabetItem


@dataclass(frozen=True)
class ClassDefinition:
    """CLASS name IS literal [THRU literal] ...: each literal tagged NONE, or THRU
    when it ends a range begun by the literal before it."""

    name: str
    items: tuple[AlphabetItem, ...]

    @classmethod
    def from_parts(
        cls, name: str, items: Sequence[Mapping[str, str]]
    ) -> ClassDefinition:
        return cls(name=name, items=tuple(AlphabetItem.from_dict(i) for i in items))

    def to_dict(self) -> dict[str, str | list[dict[str, str]]]:
        return {"name": self.name, "items": [i.to_dict() for i in self.items]}
