"""A SORT or MERGE with no COLLATING SEQUENCE phrase: it collates by the program
collating sequence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProgramCollation:
    pass


PROGRAM_COLLATION = ProgramCollation()
