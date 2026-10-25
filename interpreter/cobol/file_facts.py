"""What a program's SELECT entries and FDs fix about each file at lowering time: its record
area, its prime and alternate keys' places in that area, which key a KEY phrase names,
and its RELATIVE KEY's size."""

from __future__ import annotations

from collections.abc import Sequence

from cobol_asg.asg_types import CobolASG
from cobol_asg.cobol_statements import FileControlEntry
from cobol_asg.file_enums import FileOrganization
from cobol_asg.ref_mod import RefModOperand
from infrastructure.zos.access_methods.alternate_key import AlternateKey
from infrastructure.zos.access_methods.prime_key import PrimeKey
from interpreter.cobol.data_layout import FieldLayout
from interpreter.cobol.fd_record_format import records_vary
from interpreter.cobol.global_names import visible_record_files
from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout
from interpreter.record_io.file_frame import FileFrame


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


def _key_in(
    record: Sequence[FieldLayout],
    materialised: MaterialisedSectionedLayout,
    key: RefModOperand,
) -> tuple[PrimeKey, ...]:
    return tuple(
        PrimeKey(fl.offset - area.offset, fl.byte_length)
        for area in record
        for fl in declared_key(materialised, key)
    )


def prime_key(
    record: Sequence[FieldLayout],
    materialised: MaterialisedSectionedLayout,
    entry: FileControlEntry,
) -> PrimeKey:
    return next(iter(_key_in(record, materialised, entry.record_key)), PrimeKey())


def alternate_keys(
    record: Sequence[FieldLayout],
    materialised: MaterialisedSectionedLayout,
    entry: FileControlEntry,
) -> tuple[AlternateKey, ...]:
    return tuple(
        AlternateKey(key, not alternate.duplicates)
        for alternate in entry.alternate_keys
        for key in _key_in(record, materialised, alternate.key)
    )


def key_number(
    asg: CobolASG,
    entry: FileControlEntry,
    materialised: MaterialisedSectionedLayout,
    key: RefModOperand,
) -> int:
    record = record_area(asg, entry.file_name, materialised)
    keys = (
        prime_key(record, materialised, entry),
        *(a.key for a in alternate_keys(record, materialised, entry)),
    )
    return next(
        (
            number
            for named in _key_in(record, materialised, key)
            for number, declared in enumerate(keys)
            if declared.offset == named.offset
        ),
        0,
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
        alternate_keys=alternate_keys(record, materialised, entry),
    )
