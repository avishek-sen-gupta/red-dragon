"""Whether an FD's records vary in length, by IBM Enterprise COBOL's rules: RECORDING
MODE when coded, else the RECORD clause, else whether its record descriptions differ in
length or hold an OCCURS DEPENDING ON table."""

from __future__ import annotations

from collections.abc import Sequence
from functools import singledispatch

from cobol_asg.asg_types import CobolASG, CobolField
from cobol_asg.cobol_statements import (
    FileDescription,
    NoRecordClause,
    RecordClause,
    RecordContains,
    RecordContainsRange,
    RecordVarying,
)
from cobol_asg.file_enums import RecordingMode
from interpreter.cobol.data_layout import record_length

_VARIABLE_MODES = frozenset({RecordingMode.V, RecordingMode.S})


def depends(field: CobolField) -> bool:
    return bool(field.occurs_depending_on.name) or any(
        depends(c) for c in field.children
    )


def fd_records(asg: CobolASG, file_name: str) -> tuple[CobolField, ...]:
    return tuple(
        f
        for f in asg.file_fields
        if f.level == 1 and asg.file_record_to_select.get(f.name.upper()) == file_name
    )


@singledispatch
def _clause_varies(clause: RecordClause, records: Sequence[CobolField]) -> bool:
    raise TypeError(f"no record format for record clause {clause!r}")


@_clause_varies.register
def _unsized(clause: NoRecordClause, records: Sequence[CobolField]) -> bool:
    lengths = {record_length(r) for r in records}
    return len(lengths) > 1 or any(depends(r) for r in records)


@_clause_varies.register
def _sized(clause: RecordContains, records: Sequence[CobolField]) -> bool:
    return False


@_clause_varies.register
def _ranged(clause: RecordContainsRange, records: Sequence[CobolField]) -> bool:
    return clause.minimum != clause.maximum


@_clause_varies.register
def _varying(clause: RecordVarying, records: Sequence[CobolField]) -> bool:
    return True


def _varies(description: FileDescription, records: Sequence[CobolField]) -> bool:
    if description.recording_mode is RecordingMode.NOT_CODED:
        return _clause_varies(description.record_clause, records)
    return description.recording_mode in _VARIABLE_MODES


def _descriptions(asg: CobolASG, file_name: str) -> tuple[FileDescription, ...]:
    return tuple(
        d for d in asg.file_descriptions if d.fd_name.upper() == file_name.upper()
    )


def records_vary(asg: CobolASG, file_name: str) -> bool:
    records = fd_records(asg, file_name.upper())
    return any(_varies(d, records) for d in _descriptions(asg, file_name))


def depending_on(asg: CobolASG, file_name: str) -> str:
    return next(
        (
            d.record_clause.depending_on
            for d in _descriptions(asg, file_name)
            if isinstance(d.record_clause, RecordVarying)
        ),
        "",
    )
