"""A relative file's RELATIVE KEY: which verbs address by it and which report into it."""

from __future__ import annotations

from cobol_asg.asg_types import CobolASG
from cobol_asg.cobol_statements import FileControlEntry
from cobol_asg.file_enums import AccessMode, FileOrganization
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.global_names import visible_file_entries

NO_KEY = RefModOperand(name="")
_ADDRESSED_ACCESS = frozenset({AccessMode.RANDOM, AccessMode.DYNAMIC})


def _entry(asg: CobolASG, file_name: str) -> FileControlEntry:
    return visible_file_entries(asg).get(
        file_name, FileControlEntry(file_name=file_name)
    )


def _relative_key(entry: FileControlEntry) -> RefModOperand:
    relative = entry.organization is FileOrganization.RELATIVE
    return entry.relative_key if relative else NO_KEY


def _addressed(entry: FileControlEntry, next_record: bool) -> bool:
    return entry.access_mode in _ADDRESSED_ACCESS and not next_record


def addressing_key(asg: CobolASG, file_name: str, next_record: bool) -> RefModOperand:
    """The RELATIVE KEY a random-access verb addresses its record by."""
    entry = _entry(asg, file_name)
    return _relative_key(entry) if _addressed(entry, next_record) else NO_KEY


def reported_key(asg: CobolASG, file_name: str, next_record: bool) -> RefModOperand:
    """The RELATIVE KEY a sequential READ or WRITE sets to the record number it used."""
    entry = _entry(asg, file_name)
    return NO_KEY if _addressed(entry, next_record) else _relative_key(entry)
