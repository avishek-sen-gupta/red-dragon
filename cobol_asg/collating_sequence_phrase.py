"""A COLLATING SEQUENCE phrase as written: the alphabet-names it gives, unresolved."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cobol_asg.alphabet import Alphabet


@dataclass(frozen=True)
class CollatingSequencePhrase:
    """The phrase's alphabet-names, and the ones it gives FOR ALPHANUMERIC and FOR NATIONAL."""

    alphabet_names: tuple[str, ...] = ()
    alphanumeric: str = ""
    national: str = ""

    @classmethod
    def from_dict(cls, data: Mapping) -> CollatingSequencePhrase:
        return cls(
            alphabet_names=tuple(data.get("alphabet_names", ())),
            alphanumeric=data.get("alphanumeric", ""),
            national=data.get("national", ""),
        )

    def to_dict(self) -> dict[str, str | list[str]]:
        return (
            {"alphabet_names": list(self.alphabet_names)}
            | ({"alphanumeric": self.alphanumeric} if self.alphanumeric else {})
            | ({"national": self.national} if self.national else {})
        )

    def alphanumeric_alphabet(self, alphabets: Sequence[Alphabet]) -> Alphabet:
        """The alphabet that orders alphanumeric data: the FOR ALPHANUMERIC name, else the first.

        PROGRAM COLLATING SEQUENCE IS alphabet-name-1 without FOR names the
        alphanumeric sequence (IBM Enterprise COBOL LR, OBJECT-COMPUTER).
        """
        name = self.alphanumeric or self.alphabet_names[0]
        named = [a for a in alphabets if a.name == name]
        if not named:
            raise ValueError(
                f"COLLATING SEQUENCE names alphabet {name}, "
                f"which SPECIAL-NAMES does not declare"
            )
        return named[0]
