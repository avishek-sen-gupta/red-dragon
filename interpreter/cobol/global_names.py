"""The names a contained program sees in the programs that contain it: their GLOBAL
data items, and their GLOBAL files.

IBM Enterprise COBOL LR, scope of names: a referenced name is searched for in the
program's own declarations, then "only global declarations are searched in
successive outer containing programs", and "the search ends when the first matching
name is found"."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from cobol_asg.asg_types import CobolASG, CobolField
from cobol_asg.cobol_statements import FileControlEntry


def global_file_names(asg: CobolASG) -> frozenset[str]:
    """The upper-cased names of the files whose FD is GLOBAL."""
    return frozenset(fd.fd_name.upper() for fd in asg.file_descriptions if fd.is_global)


def _declares(asg: CobolASG, file_name: str) -> bool:
    return any(e.file_name.upper() == file_name.upper() for e in asg.file_control)


def file_owner(asg: CobolASG, file_name: str) -> CobolASG:
    """The program whose SELECT declares the file ``asg``'s statements name: its own,
    else the nearest containing program that declares it GLOBAL."""
    if _declares(asg, file_name):
        return asg
    return next(
        (
            outer
            for outer in asg.enclosing
            if _declares(outer, file_name)
            and file_name.upper() in global_file_names(outer)
        ),
        asg,
    )


def visible_file_entries(asg: CobolASG) -> dict[str, FileControlEntry]:
    """The SELECT of every file ``asg`` can name, by file-name: its own, then the
    GLOBAL ones of its containing programs, the nearest winning."""
    inherited = (
        (entry.file_name, entry)
        for outer in reversed(asg.enclosing)
        for entry in outer.file_control
        if entry.file_name.upper() in global_file_names(outer)
    )
    return dict(inherited) | {entry.file_name: entry for entry in asg.file_control}


def visible_record_files(asg: CobolASG) -> dict[str, str]:
    """The file each record ``asg`` can name belongs to: its own FDs' records, then
    those of its containing programs' GLOBAL FDs, the nearest winning."""
    inherited = (
        (record, selected)
        for outer in reversed(asg.enclosing)
        for record, selected in outer.file_record_to_select.items()
        if selected in global_file_names(outer)
    )
    return dict(inherited) | dict(asg.file_record_to_select)


def global_records(
    asg: CobolASG,
    working_storage: Sequence[CobolField],
    file: Sequence[CobolField],
) -> tuple[list[CobolField], list[CobolField]]:
    """The 01 entries of ``asg`` that are global, as laid out in its WORKING-STORAGE
    and its FILE SECTION: those with the GLOBAL clause, and every record of a GLOBAL
    FD."""
    shared = global_file_names(asg)
    return (
        [item for item in working_storage if item.is_global],
        [
            record
            for record in file
            if record.is_global
            or _record_file(asg.file_record_to_select, record) in shared
        ],
    )


def _record_file(record_files: Mapping[str, str], record: CobolField) -> str:
    return record_files.get(record.name.upper(), "")
