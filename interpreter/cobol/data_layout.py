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
from interpreter.cobol.condition_name import ConditionName, ConditionValue
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
    occurs_count: int = 0
    element_size: int = 0
    conditions: list[ConditionName] = field(default_factory=list)
    values: list[ConditionValue] = field(default_factory=list)
    sign_separate: bool = False
    sign_leading: bool = False
    justified_right: bool = False
    occurs_depending_on: str = ""
    occurs_min: int = 0
    renames_from: str = ""
    renames_thru: str = ""


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
            occurs_count=cobol_field.occurs,
            element_size=cobol_field.element_size,
            conditions=cobol_field.conditions,
            values=cobol_field.values,
            sign_separate=cobol_field.sign_separate,
            sign_leading=cobol_field.sign_leading,
            justified_right=cobol_field.justified_right,
            occurs_depending_on=cobol_field.occurs_depending_on,
            occurs_min=cobol_field.occurs_min,
        )
        return child_layouts

    type_desc = parse_pic(
        cobol_field.pic,
        cobol_field.usage,
        sign_leading=cobol_field.sign_leading,
        sign_separate=cobol_field.sign_separate,
        justified_right=cobol_field.justified_right,
        blank_when_zero=cobol_field.blank_when_zero,
    )
    element_byte_length = type_desc.byte_length
    total_byte_length = (
        element_byte_length * cobol_field.occurs
        if cobol_field.occurs > 0
        else element_byte_length
    )
    accumulator[cobol_field.name] = FieldLayout(
        name=cobol_field.name,
        type_descriptor=type_desc,
        offset=absolute_offset,
        byte_length=total_byte_length,
        redefines=cobol_field.redefines,
        value=cobol_field.value,
        occurs_count=cobol_field.occurs,
        element_size=(
            cobol_field.element_size
            if cobol_field.element_size > 0
            else element_byte_length
        ),
        conditions=cobol_field.conditions,
        values=cobol_field.values,
        sign_separate=cobol_field.sign_separate,
        sign_leading=cobol_field.sign_leading,
        justified_right=cobol_field.justified_right,
        occurs_depending_on=cobol_field.occurs_depending_on,
        occurs_min=cobol_field.occurs_min,
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
    the group's total size. OCCURS fields multiply their element
    size by the occurrence count.
    """
    if not cobol_field.children:
        element_length = parse_pic(cobol_field.pic, cobol_field.usage).byte_length
        return (
            element_length * cobol_field.occurs
            if cobol_field.occurs > 0
            else element_length
        )

    non_redefines_children = [
        child for child in cobol_field.children if not child.redefines
    ]
    children_total = sum(
        _compute_group_length(child) for child in non_redefines_children
    )
    return (
        children_total * cobol_field.occurs
        if cobol_field.occurs > 0
        else children_total
    )


def _resolve_renames(
    renames_field: CobolField,
    all_layouts: dict[str, FieldLayout],
) -> FieldLayout:
    """Resolve a level-66 RENAMES field into a FieldLayout.

    RENAMES creates a read-only alias over a contiguous range of fields.
    Offset = from_field.offset. Byte length = span from from_field through
    thru_field (or from_field itself if no THRU).
    """
    from_name = renames_field.renames_from
    thru_name = renames_field.renames_thru if renames_field.renames_thru else from_name

    from_layout = all_layouts[from_name]
    thru_layout = all_layouts[thru_name]

    offset = from_layout.offset
    byte_length = (thru_layout.offset + thru_layout.byte_length) - from_layout.offset

    type_desc = parse_pic("X")  # RENAMES is always treated as ALPHANUMERIC

    logger.debug(
        "RENAMES %s: from=%s thru=%s offset=%d length=%d",
        renames_field.name,
        from_name,
        thru_name,
        offset,
        byte_length,
    )

    return FieldLayout(
        name=renames_field.name,
        type_descriptor=type_desc,
        offset=offset,
        byte_length=byte_length,
        renames_from=renames_field.renames_from,
        renames_thru=renames_field.renames_thru,
    )


def build_data_layout(fields: list[CobolField]) -> DataLayout:
    """Build a flat DataLayout from a list of top-level CobolField trees.

    Args:
        fields: Top-level DATA DIVISION fields (level 01/77 items).

    Returns:
        A DataLayout with all fields flattened and total_bytes computed.
    """
    # Pass 1: flatten all non-RENAMES fields
    non_renames_fields = [f for f in fields if not f.renames_from]
    all_layouts: dict[str, FieldLayout] = reduce(
        lambda acc, f: _flatten_field(f, 0, acc),
        non_renames_fields,
        {},
    )

    # Pass 2: resolve RENAMES fields (level 66)
    renames_fields = [f for f in fields if f.renames_from]
    for rf in renames_fields:
        all_layouts[rf.name] = _resolve_renames(rf, all_layouts)

    non_redefines_top = [f for f in non_renames_fields if not f.redefines]
    total = sum(_compute_group_length(f) for f in non_redefines_top)

    logger.info(
        "Data layout: %d fields, %d total bytes",
        len(all_layouts),
        total,
    )

    return DataLayout(fields=all_layouts, total_bytes=total)
