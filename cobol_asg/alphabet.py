"""A SPECIAL-NAMES ALPHABET clause: a named collating sequence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cobol_asg.alphabet_item import AlphabetItem
from cobol_asg.alphabet_kind import AlphabetKind


@dataclass(frozen=True)
class Alphabet:
    """An alphabet-name and the character set or literal phrase it names."""

    name: str
    kind: AlphabetKind
    items: tuple[AlphabetItem, ...] = ()

    @classmethod
    def from_parts(
        cls, name: str, kind: str, items: Sequence[Mapping[str, str]]
    ) -> Alphabet:
        return cls(
            name=name,
            kind=AlphabetKind(kind),
            items=tuple(AlphabetItem.from_dict(i) for i in items),
        )

    def to_dict(self) -> dict[str, str | list[dict[str, str]]]:
        return {
            "name": self.name,
            "kind": self.kind,
            "items": [i.to_dict() for i in self.items],
        }


NATIVE_ALPHABET = Alphabet(name="", kind=AlphabetKind.NATIVE)
