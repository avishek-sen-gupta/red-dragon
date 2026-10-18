"""One storage area of the run unit that a program shares by name: an EXTERNAL record,
or the record area of an EXTERNAL file."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from interpreter.var_name import VarName


class ExternalKind(Enum):
    RECORD = "record"
    FILE = "file"


_DIRECTORIES = {
    ExternalKind.RECORD: VarName("__cobol_external_records"),
    ExternalKind.FILE: VarName("__cobol_external_files"),
}


def external_directory(kind: ExternalKind) -> VarName:
    """The run unit's object holding each area of this kind under its name."""
    return _DIRECTORIES[kind]


@dataclass(frozen=True)
class ExternalArea:
    """An area as one program describes it: its name, upper-cased, and where its
    description lies in the program's EXTERNAL layout."""

    name: str
    kind: ExternalKind
    start: int
    length: int
