"""What a program declares about one of its files to the provider, once: how the driver
frames its records and indexes them by each alternate record key."""

from __future__ import annotations

from dataclasses import dataclass

from cobol_asg.file_enums import FileOrganization
from interpreter.data_literals import boolean, integer, named, text
from interpreter.data_value import DataList, DataRecord, DataScalar, DataValue
from interpreter.field_name import FieldName
from interpreter.record_io.alternate_key import AlternateKey
from interpreter.record_io.prime_key import PrimeKey
from interpreter.record_io.record_shape import RecordShape


@dataclass(frozen=True)
class FileFrame:
    file_name: str
    organization: FileOrganization
    prime_key: PrimeKey
    variable: bool
    record_length: int
    alternate_keys: tuple[AlternateKey, ...] = ()

    def shape(self) -> RecordShape:
        return RecordShape(
            self.organization, self.record_length, self.prime_key, self.alternate_keys
        )

    def data(self) -> DataRecord:
        return DataRecord(
            (
                named("file_name", text(self.file_name)),
                named("organization", text(self.organization.value)),
                named("key_offset", integer(self.prime_key.offset)),
                named("key_length", integer(self.prime_key.length)),
                named("variable", boolean(self.variable)),
                named("record_length", integer(self.record_length)),
                named(
                    "alternate_keys",
                    DataList(tuple(_alternate_data(k) for k in self.alternate_keys)),
                ),
            )
        )


def _alternate_data(key: AlternateKey) -> DataRecord:
    return DataRecord(
        (
            named("key_offset", integer(key.key.offset)),
            named("key_length", integer(key.key.length)),
            named("unique", boolean(key.unique)),
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


def _records(record: DataRecord, name: str) -> tuple[DataRecord, ...]:
    match _value(record, name):
        case DataList(items=items):
            return tuple(_record(item, name) for item in items)
        case other:
            raise TypeError(f"file frame field {name} is not a list: {other!r}")


def _record(value: DataValue, name: str) -> DataRecord:
    match value:
        case DataRecord() as item:
            return item
        case other:
            raise TypeError(f"file frame field {name} holds a non-record: {other!r}")


def _alternate_of(record: DataRecord) -> AlternateKey:
    return AlternateKey(
        PrimeKey(_integer(record, "key_offset"), _integer(record, "key_length")),
        _boolean(record, "unique"),
    )


def frame_of(record: DataRecord) -> FileFrame:
    """The frame a declaration's record states."""
    return FileFrame(
        file_name=_text(record, "file_name"),
        organization=FileOrganization(_text(record, "organization")),
        prime_key=PrimeKey(
            _integer(record, "key_offset"), _integer(record, "key_length")
        ),
        variable=_boolean(record, "variable"),
        record_length=_integer(record, "record_length"),
        alternate_keys=tuple(
            _alternate_of(key) for key in _records(record, "alternate_keys")
        ),
    )
