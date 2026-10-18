"""One literal of an ALPHABET clause's literal phrase, in source order."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from cobol_asg.alphabet_link import AlphabetLink
from cobol_asg.alphabet_literal_kind import AlphabetLiteralKind
from cobol_asg.nonnumeric_literal import literal_characters, written_literal


@dataclass(frozen=True)
class AlphabetItem:
    """A literal and what links it to the literal written before it.

    ``value`` is a nonnumeric literal's characters, a numeric literal's digits,
    or a figurative constant's name.
    """

    link: AlphabetLink
    kind: AlphabetLiteralKind
    value: str

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> AlphabetItem:
        kind = AlphabetLiteralKind(data["kind"])
        return cls(
            link=AlphabetLink(data["link"]),
            kind=kind,
            value=(
                literal_characters(data["value"])
                if kind is AlphabetLiteralKind.NONNUMERIC
                else data["value"]
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "link": self.link,
            "kind": self.kind,
            "value": (
                written_literal(self.value)
                if self.kind is AlphabetLiteralKind.NONNUMERIC
                else self.value
            ),
        }
