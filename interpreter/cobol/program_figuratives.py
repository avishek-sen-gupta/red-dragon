"""The figurative constants of one program, under its collating sequence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ProgramFiguratives:
    """Each figurative constant's character, and HIGH-VALUE's and LOW-VALUE's bytes.

    HIGH-VALUE and LOW-VALUE are the highest and lowest characters of the
    program collating sequence, so they differ between programs.
    """

    characters: Mapping[str, str]
    raw_bytes: Mapping[str, int]

    def translate(self, value: str) -> str:
        return self.characters.get(value, value)

    def is_raw(self, value: str) -> bool:
        return value.upper() in self.raw_bytes

    def raw_byte(self, value: str) -> int:
        return self.raw_bytes[value.upper()]
