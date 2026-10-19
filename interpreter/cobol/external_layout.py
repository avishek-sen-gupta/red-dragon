"""A program's EXTERNAL records and EXTERNAL file record areas, taken out of
WORKING-STORAGE and the FILE SECTION and laid end to end in a layout of their own; what
is left of each section is laid out again without them."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from itertools import accumulate, pairwise

from cobol_asg.asg_types import CobolASG, CobolField
from cobol_asg.storage_layout import (
    byte_length,
    file_section_layout,
    record_areas,
    section_layout,
)
from interpreter.cobol.external_area import ExternalArea, ExternalKind

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Described:
    name: str
    kind: ExternalKind
    records: tuple[CobolField, ...]


@dataclass(frozen=True)
class ExternalPartition:
    """The items left in WORKING-STORAGE and the FILE SECTION, and each EXTERNAL area
    with its records as placed in the EXTERNAL layout, area by area."""

    working_storage: tuple[CobolField, ...]
    file: tuple[CobolField, ...]
    areas: tuple[ExternalArea, ...]
    groups: tuple[tuple[CobolField, ...], ...]


def partition_external(asg: CobolASG) -> ExternalPartition:
    described = (*_records(asg), *_files(asg))
    lengths = [_length(d.records) for d in described]
    placed = file_section_layout([d.records for d in described])
    shared = {(d.kind, record.name.upper()) for d in described for record in d.records}
    _warn_values(placed)
    return ExternalPartition(
        working_storage=tuple(
            section_layout(
                [
                    f
                    for f in asg.data_fields
                    if (ExternalKind.RECORD, f.name.upper()) not in shared
                ]
            )
        ),
        file=tuple(file_section_layout(_own_descriptions(asg, shared))),
        areas=tuple(
            ExternalArea(d.name, d.kind, start, length)
            for d, start, length in zip(
                described, accumulate(lengths, initial=0), lengths, strict=False
            )
        ),
        groups=_regrouped(placed, [len(d.records) for d in described]),
    )


def _own_descriptions(
    asg: CobolASG, shared: AbstractSet[tuple[ExternalKind, str]]
) -> list[list[CobolField]]:
    """The records of each record area that is not EXTERNAL, area by area: an FD's,
    or the FDs' a SAME RECORD AREA clause names."""
    own = [
        f for f in asg.file_fields if (ExternalKind.FILE, f.name.upper()) not in shared
    ]
    return record_areas(own, lambda f: asg.record_area(f.name))


def _records(asg: CobolASG) -> tuple[_Described, ...]:
    return tuple(
        _Described(
            record.name.upper(),
            ExternalKind.RECORD,
            (
                record,
                *(
                    item
                    for item in asg.data_fields
                    if item.redefines.upper() == record.name.upper()
                ),
            ),
        )
        for record in asg.data_fields
        if record.external
    )


def _files(asg: CobolASG) -> tuple[_Described, ...]:
    shared = asg.external_file_names()
    return tuple(
        _Described(
            fd.fd_name.upper(),
            ExternalKind.FILE,
            tuple(
                record
                for record in asg.file_fields
                if asg.file_record_to_select.get(record.name.upper())
                == fd.fd_name.upper()
            ),
        )
        for fd in asg.file_descriptions
        if fd.fd_name.upper() in shared
    )


def _length(records: Sequence[CobolField]) -> int:
    return max((byte_length(r) for r in records if not r.renames_from.name), default=0)


def _regrouped(
    placed: Sequence[CobolField], sizes: Sequence[int]
) -> tuple[tuple[CobolField, ...], ...]:
    ends = list(accumulate(sizes, initial=0))
    return tuple(tuple(placed[start:end]) for start, end in pairwise(ends))


def _warn_values(records: Sequence[CobolField]) -> None:
    valued = [item.name for item in _flattened(records) if item.value]
    if valued:
        logger.warning(
            "VALUE on EXTERNAL items %s is not applied: an EXTERNAL area starts"
            " zero-filled (ANSI X3.23-1985 forbids VALUE there)",
            valued,
        )


def _flattened(items: Sequence[CobolField]) -> list[CobolField]:
    return [each for item in items for each in (item, *_flattened(item.children))]
