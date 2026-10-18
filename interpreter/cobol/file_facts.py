"""What a program's SELECT entries and FDs fix about each file at lowering time: its record
area, its prime key's place in that area and its RELATIVE KEY's size."""

from __future__ import annotations

from collections.abc import Sequence

from cobol_asg.asg_types import CobolASG
from cobol_asg.cobol_statements import FileControlEntry
from cobol_asg.file_enums import FileOrganization
from cobol_asg.ref_mod import RefModOperand
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.fd_record_format import records_vary
from interpreter.cobol.file_frame import FileFrame
from interpreter.cobol.global_names import visible_record_files
from interpreter.cobol.prime_key import PrimeKey
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout


def largest_record(
    asg: CobolASG, filename: str, materialised: MaterialisedSectionedLayout
) -> str:
    records = [
        materialised.resolve(record)[0]
        for record, selected in visible_record_files(asg).items()
        if selected == filename.upper() and materialised.has_field(record)
    ]
    return max(records, key=lambda fl: fl.byte_length).name if records else ""


def record_area(
    asg: CobolASG, filename: str, materialised: MaterialisedSectionedLayout
) -> tuple[FieldLayout, ...]:
    rec_name = largest_record(asg, filename, materialised)
    if not rec_name:
        return ()
    fl, _ = materialised.resolve(rec_name)
    return (fl,)


def declared_key(
    materialised: MaterialisedSectionedLayout, key: RefModOperand
) -> tuple[FieldLayout, ...]:
    if not (key.name and materialised.has_field(key.name)):
        return ()
    fl, _ = materialised.resolve(key.name, key.qualifiers)
    return (fl,)


def prime_key(
    record: Sequence[FieldLayout],
    materialised: MaterialisedSectionedLayout,
    entry: FileControlEntry,
) -> PrimeKey:
    return next(
        (
            PrimeKey(key.offset - area.offset, key.byte_length)
            for area in record
            for key in declared_key(materialised, entry.record_key)
        ),
        PrimeKey(),
    )


def relative_key_digits(
    materialised: MaterialisedSectionedLayout, entry: FileControlEntry
) -> int:
    if entry.organization is not FileOrganization.RELATIVE:
        return 0
    return next(
        (
            fl.type_descriptor.total_digits
            for fl in declared_key(materialised, entry.relative_key)
        ),
        0,
    )


def file_frame(
    asg: CobolASG, entry: FileControlEntry, materialised: MaterialisedSectionedLayout
) -> FileFrame:
    record = record_area(asg, entry.file_name, materialised)
    return FileFrame(
        file_name=entry.file_name,
        organization=entry.organization,
        prime_key=prime_key(record, materialised, entry),
        variable=records_vary(asg, entry.file_name),
        record_length=next((area.byte_length for area in record), 0),
    )
