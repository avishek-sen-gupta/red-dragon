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
    layout: DataLayout,
    record: bytes,
    base_offset: int | None = None,
    root: DataLayout | None = None,
) -> dict[str, object]:
    """Decode one record's bytes into a nested dict, per the DataLayout.

    Leaf fields decode via _decode_leaf; group children recurse. Fields/groups with
    occurs_count > 0 become lists (stride element_size). OCCURS DEPENDING ON honors
    the counter field (resolved from ``root``) clamped to [occurs_min or 1,
    occurs_count]. ``base_offset`` rebases absolute offsets to the record start; it
    defaults to the layout's own offset so a sub-01 group selected from a multi-01
    copybook (sitting at a non-zero absolute offset) slices correctly.
    """
    base = layout.offset if base_offset is None else base_offset
    top = layout if root is None else root
    out: dict[str, object] = {}
    for name, fl in layout.fields.items():
        out[name] = _decode_field(fl, record, base, top)
    for name, sub in layout.groups.items():
        out[name] = _decode_group(sub, record, base, top)
    return out


def _live_count(
    node: FieldLayout | DataLayout, record: bytes, base: int, root: DataLayout
) -> int:
    """Resolve the occurrence count for an OCCURS node, honoring ODO.

    Group nodes (DataLayout) carry no occurs_depending_on attribute, so a
    fixed-OCCURS group simply uses its declared occurs_count.
    """
    odo = getattr(node, "occurs_depending_on", "")
    if not odo:
        return node.occurs_count
    counter = root.lookup(odo)
    if counter is None:
        return node.occurs_count  # unresolved counter: fall back to declared max
    start = counter.offset - base
    raw = _decode_leaf(counter, record[start : start + counter.byte_length])
    n = int(raw)
    low = getattr(node, "occurs_min", 0) or 1
    return max(low, min(n, node.occurs_count))


def _decode_field(
    fl: FieldLayout, record: bytes, base: int, root: DataLayout
) -> list[int | float | str] | int | float | str:
    if fl.occurs_count > 0:
        n = _live_count(fl, record, base, root)
        result = []
        for i in range(n):
            start = fl.offset - base + i * fl.element_size
            result.append(_decode_leaf(fl, record[start : start + fl.byte_length]))
        return result
    start = fl.offset - base
    return _decode_leaf(fl, record[start : start + fl.byte_length])


def _decode_group(
    sub: DataLayout, record: bytes, base: int, root: DataLayout
) -> list[dict[str, object]] | dict[str, object]:
    if sub.occurs_count > 0:
        n = _live_count(sub, record, base, root)
        return [_decode_group_element(sub, record, base, root, i) for i in range(n)]
    return decode_record(sub, record, base, root)


def _decode_group_element(
    sub: DataLayout, record: bytes, base: int, root: DataLayout, index: int
) -> dict[str, object]:
    """Decode the index-th element of an OCCURS group (shift base by stride)."""
    # Subtracting from base is equivalent to adding index*element_size to every
    # child's (offset - base) in the recursive call; children store the
    # first-element absolute offset, so this maps them to element #index.
    shifted_base = base - index * sub.element_size
    return decode_record(sub, record, shifted_base, root)
