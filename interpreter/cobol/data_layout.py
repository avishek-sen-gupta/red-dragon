# pyright: standard
"""Data layout builder — computes byte layouts from COBOL field trees.

Pure function: takes a list of CobolField trees and produces a recursive
DataLayout with computed type descriptors and byte lengths.
The ProLeap bridge provides byte offsets; this module validates them
and attaches CobolTypeDescriptor via parse_pic.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field

from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.cobol_types import CobolDataCategory, CobolTypeDescriptor
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
    """Recursive data layout for a COBOL record.

    Attributes:
        fields: Direct elementary (leaf) children only.
        groups: Direct group children, keyed by group name.
        offset: Absolute byte offset of this group's start.
        total_bytes: Total record size in bytes (meaningful at root level).
        occurs_count: OCCURS count if this group is an OCCURS table.
        element_size: Per-element byte size for OCCURS group tables.
    """

    fields: dict[str, FieldLayout] = field(default_factory=dict)
    groups: dict[str, "DataLayout"] = field(default_factory=dict)
    offset: int = 0
    total_bytes: int = 0
    occurs_count: int = 0
    element_size: int = 0

    def lookup(self, name: str) -> FieldLayout | None:
        """Depth-first search for a leaf field by bare name.

        Returns the first match found. Field names should be unique across
        the record; duplicate names at different levels are a program error.
        """
        if name in self.fields:
            return self.fields[name]
        for sub in self.groups.values():
            found = sub.lookup(name)
            if found is not None:
                return found
        return None

    def lookup_or_raise(self, name: str) -> FieldLayout:
        result = self.lookup(name)
        if result is None:
            raise KeyError(f"Field not found in layout: {name!r}")
        return result

    def lookup_group(self, name: str) -> "DataLayout":
        """Return a nested DataLayout by group name; raises KeyError if not found."""
        if name in self.groups:
            return self.groups[name]
        for sub in self.groups.values():
            try:
                return sub.lookup_group(name)
            except KeyError:
                pass
        raise KeyError(f"Group not found in layout: {name!r}")

    def all_leaves(self) -> Iterator[FieldLayout]:
        """Yield all leaf FieldLayouts depth-first."""
        yield from self.fields.values()
        for sub in self.groups.values():
            yield from sub.all_leaves()

    def all_fields(self) -> Iterator[FieldLayout]:
        """Yield all FieldLayouts (leaf and synthesized group storage) depth-first.

        For groups, synthesizes alphanumeric FieldLayout with group's byte bounds.
        Used by the data_layout property to maintain backward compatibility.
        """
        yield from self.fields.values()
        for name, grp in self.groups.items():
            # Synthesize storage layout for the group itself
            type_desc = CobolTypeDescriptor(
                category=CobolDataCategory.ALPHANUMERIC,
                total_digits=grp.total_bytes,
            )
            elem_size = grp.element_size if grp.element_size > 0 else grp.total_bytes
            yield FieldLayout(
                name=name,
                type_descriptor=type_desc,
                offset=grp.offset,
                byte_length=grp.total_bytes,
                occurs_count=grp.occurs_count,
                element_size=elem_size,
            )
            # Recurse into group's children
            yield from grp.all_fields()

    def enclosing_occurs_element_size(self, name: str) -> int:
        """Return the subscript stride for ``name``: the element_size of the
        nearest ancestor (or self) OCCURS group/field.

        When a leaf is nested inside an OCCURS group, COBOL subscripting strides
        by the OCCURS *element* size, not by the leaf's own byte_length. Returns
        0 if ``name`` is not under (and is not itself) an OCCURS table.
        """
        result = self._enclosing_occurs_element_size(name, enclosing=0)
        return result if result is not None else 0

    def _enclosing_occurs_element_size(self, name: str, enclosing: int) -> int | None:
        """Walk the tree tracking the nearest enclosing OCCURS element_size.

        ``enclosing`` is the element_size of the closest OCCURS ancestor seen so
        far (0 if none). Returns the stride for ``name`` once found, else None.
        """
        if name in self.fields:
            leaf = self.fields[name]
            # A leaf that itself has OCCURS strides by its own element_size;
            # otherwise it inherits the enclosing OCCURS group's element_size.
            if leaf.occurs_count > 0 and leaf.element_size > 0:
                return leaf.element_size
            return enclosing
        if name in self.groups:
            grp = self.groups[name]
            return grp.element_size if grp.occurs_count > 0 else enclosing
        for grp in self.groups.values():
            next_enclosing = grp.element_size if grp.occurs_count > 0 else enclosing
            found = grp._enclosing_occurs_element_size(name, next_enclosing)
            if found is not None:
                return found
        return None

    def lookup_as_storage(self, name: str) -> FieldLayout | None:
        """Return a FieldLayout for name, synthesizing one for groups.

        For elementary fields, returns the real FieldLayout.
        For group names, synthesizes an alphanumeric FieldLayout whose
        byte_length, offset, occurs_count, and element_size match the group.
        Returns None if name is not found anywhere in the layout.
        """
        leaf = self.lookup(name)
        if leaf is not None:
            return leaf
        try:
            grp = self.lookup_group(name)
        except KeyError:
            return None
        type_desc = CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC,
            total_digits=grp.total_bytes,
        )
        elem_size = grp.element_size if grp.element_size > 0 else grp.total_bytes
        return FieldLayout(
            name=name,
            type_descriptor=type_desc,
            offset=grp.offset,
            byte_length=grp.total_bytes,
            occurs_count=grp.occurs_count,
            element_size=elem_size,
        )


def _placed_child_extent(
    cobol_field: CobolField,
    sub_fields: dict[str, FieldLayout],
    sub_groups: dict[str, "DataLayout"],
    group_offset: int,
) -> int | None:
    """Return the group's byte length from its children's PLACED extents.

    The extent is ``max(child.offset + child.length) - group_offset`` over
    NON-REDEFINES children (REDEFINES children — leaf or group — overlay the
    same storage and do not extend the group). For an OCCURS group the caller
    multiplies the returned single-occurrence extent by the occurrence count.

    Returns None if the group has no non-REDEFINES children (caller falls back
    to the summed length so an all-REDEFINES group still gets a size).
    """
    # Collect non-REDEFINES children with their placed (offset, length).
    placed: list[tuple[int, int]] = []
    for child in cobol_field.children:
        if child.redefines:
            continue
        built = sub_fields.get(child.name) or sub_groups.get(child.name)
        if built is None:
            continue
        if isinstance(built, DataLayout):
            placed.append((built.offset, built.total_bytes))
        else:
            placed.append((built.offset, built.byte_length))
    if not placed:
        return None
    placed.sort()
    # Each child's end is bounded by the NEXT non-REDEFINES child's placed
    # offset: the real compiler lays siblings out contiguously, so a child
    # whose PIC our parser over-sizes (e.g. an edited PIC) cannot extend past
    # where the compiler placed its successor. The last child uses its own end.
    end = group_offset
    for i, (off, length) in enumerate(placed):
        child_end = off + length
        if i + 1 < len(placed):
            child_end = min(child_end, placed[i + 1][0])
        end = max(end, child_end)
    return end - group_offset


def _flatten_field(
    cobol_field: CobolField,
    base_offset: int,
    sibling_fields: dict[str, FieldLayout],
    sibling_groups: dict[str, DataLayout],
) -> tuple[str, FieldLayout | DataLayout]:
    """Return (name, leaf) for elementary fields, (name, DataLayout) for groups."""
    # Offset resolution — REDEFINES gets offset of the field it redefines.
    # COBOL requires the redefined field to appear before REDEFINES at same level,
    # so the sibling dicts already contain the target by the time we process REDEFINES.
    if cobol_field.redefines:
        if cobol_field.redefines in sibling_fields:
            absolute_offset = sibling_fields[cobol_field.redefines].offset
        elif cobol_field.redefines in sibling_groups:
            absolute_offset = sibling_groups[cobol_field.redefines].offset
        else:
            absolute_offset = base_offset + cobol_field.offset
    else:
        absolute_offset = base_offset + cobol_field.offset

    if cobol_field.children:
        sub_fields: dict[str, FieldLayout] = {}
        sub_groups: dict[str, DataLayout] = {}
        for child in cobol_field.children:
            child_name, child_result = _flatten_field(
                child, absolute_offset, sub_fields, sub_groups
            )
            if isinstance(child_result, DataLayout):
                sub_groups[child_name] = child_result
            else:
                sub_fields[child_name] = child_result
        # Group length from PLACED child extents (compiler-assigned offsets),
        # not from summing our own per-field length estimates. This is robust
        # against a child whose PIC our parser sizes differently than the real
        # compiler (e.g. an edited PIC like +ZZZ,ZZZ,ZZ9.99): summing would
        # over-reach and overlap the next sibling, whereas the compiler-placed
        # offset of that sibling bounds this group correctly. REDEFINES children
        # overlay the same storage, so only non-REDEFINES children extend the
        # group. OCCURS multiplies the single-occurrence extent by the count.
        single_extent = _placed_child_extent(
            cobol_field, sub_fields, sub_groups, absolute_offset
        )
        if single_extent is None:
            group_length = _compute_group_length(cobol_field)
        elif cobol_field.occurs > 0:
            group_length = single_extent * cobol_field.occurs
        else:
            group_length = single_extent
        elem_size = cobol_field.element_size if cobol_field.element_size > 0 else 0
        group_layout = DataLayout(
            fields=sub_fields,
            groups=sub_groups,
            offset=absolute_offset,
            total_bytes=group_length,
            occurs_count=cobol_field.occurs,
            element_size=elem_size,
        )
        return cobol_field.name, group_layout

    # Elementary leaf
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
    fl = FieldLayout(
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
    return cobol_field.name, fl


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
    layout: DataLayout,
) -> FieldLayout:
    """Resolve a level-66 RENAMES field into a FieldLayout.

    RENAMES creates a read-only alias over a contiguous range of fields.
    Offset = from_field.offset. Byte length = span from from_field through
    thru_field (or from_field itself if no THRU).
    """
    from_name = renames_field.renames_from
    thru_name = renames_field.renames_thru if renames_field.renames_thru else from_name

    from_layout = layout.lookup_or_raise(from_name)
    thru_layout = layout.lookup_or_raise(thru_name)

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
    """Build a recursive DataLayout from a list of top-level CobolField trees.

    Args:
        fields: Top-level DATA DIVISION fields (level 01/77 items).

    Returns:
        A DataLayout with fields/groups split and total_bytes computed.
    """
    non_renames_fields = [f for f in fields if not f.renames_from]
    top_fields: dict[str, FieldLayout] = {}
    top_groups: dict[str, DataLayout] = {}
    for f in non_renames_fields:
        name, result = _flatten_field(f, 0, top_fields, top_groups)
        if isinstance(result, DataLayout):
            top_groups[name] = result
        else:
            top_fields[name] = result

    # RENAMES fields (level 66) — resolved against the partial layout
    renames_fields = [f for f in fields if f.renames_from]
    if renames_fields:
        temp_layout = DataLayout(fields=top_fields, groups=top_groups)
        for rf in renames_fields:
            top_fields[rf.name] = _resolve_renames(rf, temp_layout)

    non_redefines_top = [f for f in non_renames_fields if not f.redefines]
    total = sum(_compute_group_length(f) for f in non_redefines_top)

    logger.info(
        "Data layout: %d top-level fields, %d top-level groups, %d total bytes",
        len(top_fields),
        len(top_groups),
        total,
    )

    return DataLayout(fields=top_fields, groups=top_groups, total_bytes=total)
