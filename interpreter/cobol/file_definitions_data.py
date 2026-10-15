# pyright: standard
"""The file-definitions Data: each SELECT's FILE-CONTROL facts and its FD's format."""

from __future__ import annotations

from functools import singledispatch

from cobol_asg.asg_types import CobolASG, CobolField
from cobol_asg.cobol_statements import (
    FileControlEntry,
    FileDescription,
    NoRecordClause,
    RecordClause,
    RecordContains,
    RecordContainsRange,
    RecordVarying,
)
from interpreter.cobol.data_layout import record_length
from interpreter.cobol.data_literals import boolean, integer, named, text
from interpreter.cobol.program_object import program_name
from interpreter.data_value import DataList, DataRecord
from interpreter.instructions import Data
from interpreter.var_name import VarName

FILE_DEFINITIONS = VarName("__cobol_file_definitions")


@singledispatch
def _clause(clause: RecordClause) -> DataRecord:
    raise TypeError(f"no Data form for record clause {clause!r}")


@_clause.register
def _no_clause(clause: NoRecordClause) -> DataRecord:
    return DataRecord((named("kind", text("none")),))


@_clause.register
def _contains(clause: RecordContains) -> DataRecord:
    return DataRecord(
        (named("kind", text("contains")), named("size", integer(clause.size)))
    )


@_clause.register
def _range(clause: RecordContainsRange) -> DataRecord:
    return DataRecord(
        (
            named("kind", text("range")),
            named("minimum", integer(clause.minimum)),
            named("maximum", integer(clause.maximum)),
        )
    )


@_clause.register
def _varying(clause: RecordVarying) -> DataRecord:
    return DataRecord(
        (
            named("kind", text("varying")),
            named("minimum", integer(clause.minimum)),
            named("maximum", integer(clause.maximum)),
            named("depending_on", text(clause.depending_on)),
        )
    )


def _depends(field: CobolField) -> bool:
    return bool(field.occurs_depending_on) or any(_depends(c) for c in field.children)


def _records(asg: CobolASG, file_name: str) -> tuple[CobolField, ...]:
    return tuple(
        f
        for f in asg.file_fields
        if f.level == 1 and asg.file_record_to_select.get(f.name.upper()) == file_name
    )


def _fd(asg: CobolASG, description: FileDescription) -> DataRecord:
    records = _records(asg, description.fd_name.upper())
    return DataRecord(
        (
            named("recording_mode", text(description.recording_mode.value)),
            named("record_clause", _clause(description.record_clause)),
            named(
                "record_lengths",
                DataList(tuple(integer(record_length(r)) for r in records)),
            ),
            named("depending", boolean(any(_depends(r) for r in records))),
        )
    )


def _fds(asg: CobolASG, entry: FileControlEntry) -> DataList:
    return DataList(
        tuple(
            _fd(asg, d)
            for d in asg.file_descriptions
            if d.fd_name.upper() == entry.file_name.upper()
        )
    )


def _file(asg: CobolASG, entry: FileControlEntry) -> DataRecord:
    return DataRecord(
        (
            named("program", text(program_name(asg))),
            named("file_name", text(entry.file_name)),
            named("assign_to", text(entry.assign_to)),
            named("organization", text(entry.organization.value)),
            named("access_mode", text(entry.access_mode.value)),
            named("record_key", text(entry.record_key)),
            named("relative_key", text(entry.relative_key)),
            named("file_status", text(entry.file_status_var)),
            named("fd", _fds(asg, entry)),
        )
    )


def file_definitions_data(asg: CobolASG) -> Data:
    files = DataList(tuple(_file(asg, e) for e in asg.file_control))
    return Data(name=FILE_DEFINITIONS, value=DataRecord((named("files", files),)))
