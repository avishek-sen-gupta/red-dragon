"""Data layout builder — computes byte layouts from COBOL field trees.

Pure function: takes a list of CobolField trees and produces a flat
FieldLayout map with computed type descriptors and byte lengths.
The ProLeap bridge provides byte offsets; this module validates them
and attaches CobolTypeDescriptor via parse_pic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import reduce

from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.cobol_types import CobolTypeDescriptor
from interpreter.cobol.pic_parser import parse_pic

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FieldLayout:
    """Byte-level layout for a single COBOL field.

    Attributes:
        name: Field name (e.g. "WS-AMOUNT").
        type_descriptor: Parsed PIC type info.
        offset: Absolute byte offset from start of record.
        byte_length: Storage size in bytes.
        redefines: Name of redefined field, or empty string.
        value: Initial VALUE clause content, or empty string.
    """

    name: str
    type_descriptor: CobolTypeDescriptor
    offset: int
    byte_length: int
    redefines: str = ""
    value: str = ""


@dataclass(frozen=True)
class DataLayout:
    """Complete data layout for a COBOL record.

    Attributes:
        fields: Name-to-FieldLayout mapping for all fields.
        total_bytes: Total record size in bytes.
    """

    fields: dict[str, FieldLayout] = field(default_factory=dict)
    total_bytes: int = 0


def _flatten_field(
    cobol_field: CobolField,
    base_offset: int,
    accumulator: dict[str, FieldLayout],
) -> dict[str, FieldLayout]:
    """Recursively flatten a CobolField tree into FieldLayout entries."""
    absolute_offset = base_offset + cobol_field.offset

    if cobol_field.children:
        child_layouts = reduce(
            lambda acc, child: _flatten_field(child, absolute_offset, acc),
            cobol_field.children,
            accumulator,
        )
        group_length = _compute_group_length(cobol_field)
        type_desc = CobolTypeDescriptor(
            category=(
                parse_pic("X").category
                if not cobol_field.pic
                else parse_pic(cobol_field.pic, cobol_field.usage).category
            ),
            total_digits=group_length,
        )
        child_layouts[cobol_field.name] = FieldLayout(
            name=cobol_field.name,
            type_descriptor=type_desc,
            offset=absolute_offset,
            byte_length=group_length,
            redefines=cobol_field.redefines,
            value=cobol_field.value,
        )
        return child_layouts

    type_desc = parse_pic(cobol_field.pic, cobol_field.usage)
    accumulator[cobol_field.name] = FieldLayout(
        name=cobol_field.name,
        type_descriptor=type_desc,
        offset=absolute_offset,
        byte_length=type_desc.byte_length,
        redefines=cobol_field.redefines,
        value=cobol_field.value,
    )
    logger.debug(
        "Field %s: offset=%d, length=%d, type=%s",
        cobol_field.name,
        absolute_offset,
        type_desc.byte_length,
        type_desc.category,
    )
    return accumulator


def _compute_group_length(cobol_field: CobolField) -> int:
    """Compute the byte length of a group item from its children.

    REDEFINES children share the same offset and do NOT increase
    the group's total size.
    """
    if not cobol_field.children:
        return parse_pic(cobol_field.pic, cobol_field.usage).byte_length

    non_redefines_children = [
        child for child in cobol_field.children if not child.redefines
    ]
    return sum(_compute_group_length(child) for child in non_redefines_children)


def build_data_layout(fields: list[CobolField]) -> DataLayout:
    """Build a flat DataLayout from a list of top-level CobolField trees.

    Args:
        fields: Top-level DATA DIVISION fields (level 01/77 items).

    Returns:
        A DataLayout with all fields flattened and total_bytes computed.
    """
    all_layouts: dict[str, FieldLayout] = reduce(
        lambda acc, f: _flatten_field(f, 0, acc),
        fields,
        {},
    )

    non_redefines_top = [f for f in fields if not f.redefines]
    total = sum(_compute_group_length(f) for f in non_redefines_top)

    logger.info(
        "Data layout: %d fields, %d total bytes",
        len(all_layouts),
        total,
    )

    return DataLayout(fields=all_layouts, total_bytes=total)
