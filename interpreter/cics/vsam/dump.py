"""Copybook-driven decoder/dumper for VSAM flat-file dataset images.

Reads a fixed-length-record flat file (see interpreter/cics/vsam/format.py) and
decodes each record field-by-field using a COBOL record layout parsed from a
copybook, emitting JSON-lines (default) or a human-readable block format.

Pure orchestration over existing primitives: build_data_layout (copybook ->
DataLayout) and the COBOL pure decoders. No new decode logic, no new format.
"""

from __future__ import annotations

from interpreter.cobol.binary import decode_binary
from interpreter.cobol.comp3 import decode_comp3
from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.data_layout import DataLayout, FieldLayout
from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.zoned_decimal import decode_zoned


def _decode_leaf(field: FieldLayout, data: bytes) -> int | float | str:
    """Decode the bytes of one elementary field to a Python value.

    ``data`` must be exactly the field's bytes. Numeric fields with no implied
    decimals decode to int (matching the engine, red-dragon-4q25.42); fields with
    decimals decode to float. Alphanumeric fields decode EBCDIC -> ASCII text with
    trailing spaces trimmed.
    """
    td = field.type_descriptor
    cat = td.category
    if cat == CobolDataCategory.ALPHANUMERIC:
        return (
            EbcdicTable.ebcdic_to_ascii(data)
            .decode("ascii", errors="replace")
            .rstrip(" ")
        )
    if cat == CobolDataCategory.ZONED_DECIMAL:
        return _as_number(decode_zoned(data, td.decimal_digits), td.decimal_digits)
    if cat == CobolDataCategory.COMP3:
        return _as_number(decode_comp3(data, td.decimal_digits), td.decimal_digits)
    if cat == CobolDataCategory.BINARY:
        return _as_number(
            decode_binary(data, td.decimal_digits, td.signed), td.decimal_digits
        )
    raise NotImplementedError(
        f"VSAM dump does not support category {cat.value} (field {field.name!r})"
    )


def _as_number(value: float, decimal_digits: int) -> int | float:
    return int(round(value)) if decimal_digits == 0 else value


def decode_record(
    layout: DataLayout, record: bytes, base_offset: int | None = None
) -> dict:
    """Decode one record's bytes into a nested dict, per the DataLayout.

    Leaf fields decode via _decode_leaf; group children recurse into nested dicts.
    ``base_offset`` rebases absolute field offsets to the record start; it defaults
    to the layout's own offset so a sub-01 group selected from a multi-01 copybook
    (sitting at a non-zero absolute offset) slices correctly. OCCURS handling is
    added in a later task.
    """
    base = layout.offset if base_offset is None else base_offset
    out: dict = {}
    for name, fl in layout.fields.items():
        start = fl.offset - base
        out[name] = _decode_leaf(fl, record[start : start + fl.byte_length])
    for name, sub in layout.groups.items():
        out[name] = decode_record(sub, record, base)
    return out
