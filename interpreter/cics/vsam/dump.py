"""Copybook-driven decoder/dumper for VSAM flat-file dataset images.

Reads a fixed-length-record flat file (see interpreter/cics/vsam/format.py) and
decodes each record field-by-field using a COBOL record layout parsed from a
copybook, emitting JSON-lines (default) or a human-readable block format.

Pure orchestration over existing primitives: build_data_layout (copybook ->
DataLayout) and the COBOL pure decoders. No new decode logic, no new format.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from interpreter.cics.vsam.format import read_flat_file
from interpreter.cobol.binary import decode_binary
from interpreter.cobol.comp3 import decode_comp3
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.cobol_types import CobolDataCategory
from interpreter.cobol.data_layout import DataLayout, FieldLayout, build_data_layout
from interpreter.cobol.ebcdic_table import EbcdicTable
from interpreter.cobol.subprocess_runner import SubprocessRunner
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


def select_record_layout(root: DataLayout, record_name: str | None) -> DataLayout:
    """Pick the 01-level record layout to decode.

    - Root has group children: select by ``record_name``; if exactly one group and
      no name given, use it; if multiple and no name, raise listing the names.
    - Root has no group children (the 01 is elementary): decode the root itself.
    """
    groups = root.groups
    if not groups:
        return root
    if record_name is not None:
        for name, sub in groups.items():
            if name.upper() == record_name.upper():
                return sub
        raise ValueError(
            f"record {record_name!r} not found; available: {sorted(groups)}"
        )
    if len(groups) == 1:
        return next(iter(groups.values()))
    raise ValueError(
        f"copybook declares multiple records; pass --record (one of {sorted(groups)})"
    )


_SKELETON_HEAD = (
    "       IDENTIFICATION DIVISION.\n"
    "       PROGRAM-ID. VSAMDUMP.\n"
    "       DATA DIVISION.\n"
    "       WORKING-STORAGE SECTION.\n"
)


def load_record_layout(
    copybook: Path,
    record_name: str | None,
    jar: str,
    extra_dirs: list[Path],
) -> DataLayout:
    """Parse a copybook (wrapped in a minimal program) into the selected layout."""
    member = copybook.stem
    source = (_SKELETON_HEAD + f"       COPY {member}.\n").encode("ascii")
    copybook_dirs = [copybook.parent, *extra_dirs]
    parser = ProLeapCobolParser(SubprocessRunner(), jar, copybook_dirs=copybook_dirs)
    asg = parser.parse(source)
    root = build_data_layout(asg.data_fields)
    return select_record_layout(root, record_name)


def render_jsonl(layout: DataLayout, records: list[bytes]) -> str:
    """One compact JSON object per record, newline-terminated."""
    lines = [json.dumps(decode_record(layout, rec)) for rec in records]
    return "\n".join(lines) + ("\n" if lines else "")


def render_block(layout: DataLayout, records: list[bytes]) -> str:
    """Human-readable per-field block: @offset NAME value 0xRAW, for each record."""
    chunks: list[str] = []
    for idx, rec in enumerate(records, start=1):
        chunks.append(f"=== record {idx} ===")
        chunks.extend(_block_lines(layout, rec, layout.offset, prefix=""))
    return "\n".join(chunks) + ("\n" if chunks else "")


def _block_lines(
    layout: DataLayout, record: bytes, base: int, prefix: str
) -> list[str]:
    lines: list[str] = []
    for name, fl in layout.fields.items():
        start = fl.offset - base
        raw = record[start : start + fl.byte_length]
        value = _decode_leaf(fl, raw) if fl.occurs_count == 0 else "<occurs>"
        lines.append(
            f"  @{fl.offset:<5} {prefix}{name:<28} {value!r:<24} 0x{raw.hex()}"
        )
    for name, sub in layout.groups.items():
        lines.append(f"  @{sub.offset:<5} {prefix}{name}:")
        lines.extend(_block_lines(sub, record, base, prefix + "  "))
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m interpreter.cics.vsam.dump",
        description="Decode a VSAM flat-file dataset via a COBOL copybook.",
    )
    parser.add_argument("--data", required=True, type=Path, help="flat-file .dat path")
    parser.add_argument("--copybook", required=True, type=Path, help="record copybook")
    parser.add_argument(
        "--record", default=None, help="01-level record name (if multiple)"
    )
    parser.add_argument("--format", choices=["jsonl", "block"], default="jsonl")
    parser.add_argument("--copybook-dir", action="append", default=[], type=Path)
    parser.add_argument(
        "--jar",
        default=os.environ.get("PROLEAP_BRIDGE_JAR"),
        help="ProLeap bridge JAR (defaults to $PROLEAP_BRIDGE_JAR)",
    )
    args = parser.parse_args(argv)
    if not args.jar:
        parser.error("no JAR: pass --jar or set PROLEAP_BRIDGE_JAR")

    layout = load_record_layout(args.copybook, args.record, args.jar, args.copybook_dir)
    record_length = layout.total_bytes
    records = read_flat_file(args.data, record_length)
    renderer = render_jsonl if args.format == "jsonl" else render_block
    sys.stdout.write(renderer(layout, records))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
