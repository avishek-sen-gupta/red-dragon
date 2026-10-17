"""What a program declares about one of its files to the provider, once: how the driver
frames its records, and the SELECT and FD facts the provider's status rules read."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.file_enums import AccessMode, FileOrganization
from interpreter.cobol.data_literals import boolean, integer, named, text
from interpreter.cobol.prime_key import PrimeKey
from interpreter.data_value import DataRecord, DataScalar, DataValue
from interpreter.field_name import FieldName


@dataclass(frozen=True)
class FileFrame:
    file_name: str
    organization: FileOrganization
    access: AccessMode
    prime_key: PrimeKey
    relative_key_digits: int
    optional: bool
    variable: bool
    minimum_record_length: int
    maximum_record_length: int

    def data(self) -> DataRecord:
        return DataRecord(
            (
                named("file_name", text(self.file_name)),
                named("organization", text(self.organization.value)),
                named("access_mode", text(self.access.value)),
                named("key_offset", integer(self.prime_key.offset)),
                named("key_length", integer(self.prime_key.length)),
                named("relative_key_digits", integer(self.relative_key_digits)),
                named("optional", boolean(self.optional)),
                named("variable", boolean(self.variable)),
                named("minimum_record_length", integer(self.minimum_record_length)),
                named("maximum_record_length", integer(self.maximum_record_length)),
            )
        )


def _value(record: DataRecord, name: str) -> DataValue:
    return next(f.value for f in record.fields if f.name == FieldName(name))


def _text(record: DataRecord, name: str) -> str:
    match _value(record, name):
        case DataScalar(value=str() as value):
            return value
        case other:
            raise TypeError(f"file frame field {name} is not text: {other!r}")


def _integer(record: DataRecord, name: str) -> int:
    match _value(record, name):
        case DataScalar(value=bool()) as flag:
            raise TypeError(f"file frame field {name} is not an integer: {flag!r}")
        case DataScalar(value=int() as value):
            return value
        case other:
            raise TypeError(f"file frame field {name} is not an integer: {other!r}")


def _boolean(record: DataRecord, name: str) -> bool:
    match _value(record, name):
        case DataScalar(value=bool() as value):
            return value
        case other:
            raise TypeError(f"file frame field {name} is not a boolean: {other!r}")


def frame_of(record: DataRecord) -> FileFrame:
    """The frame a declaration's record states."""
    return FileFrame(
        file_name=_text(record, "file_name"),
        organization=FileOrganization(_text(record, "organization")),
        access=AccessMode(_text(record, "access_mode")),
        prime_key=PrimeKey(
            _integer(record, "key_offset"), _integer(record, "key_length")
        ),
        relative_key_digits=_integer(record, "relative_key_digits"),
        optional=_boolean(record, "optional"),
        variable=_boolean(record, "variable"),
        minimum_record_length=_integer(record, "minimum_record_length"),
        maximum_record_length=_integer(record, "maximum_record_length"),
    )
