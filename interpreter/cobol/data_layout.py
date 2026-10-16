# pyright: standard
"""Data layout builder — computes byte layouts from COBOL field trees.

Pure function: takes a list of CobolField trees and produces a recursive
DataLayout with computed type descriptors and byte lengths.
The ProLeap bridge provides byte offsets; this module validates them
and attaches CobolTypeDescriptor via parse_pic.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, replace
from itertools import accumulate, chain
from typing import TypeVar

from cobol_asg.asg_types import CobolField
from cobol_asg.cobol_types import CobolDataCategory, CobolTypeDescriptor
from cobol_asg.condition_name import ConditionName, ConditionValue
from cobol_asg.pic_parser import parse_pic
from cobol_asg.ref_mod import RefModOperand
from cobol_asg.source_span import SourceSpan

logger = logging.getLogger(__name__)

# RENAMES (level-66) is always treated as ALPHANUMERIC; its descriptor is fixed.
_RENAMES_TYPE_DESCRIPTOR = parse_pic("X")


class CobolAmbiguousReferenceError(Exception):
    """A bare (unqualified) field reference resolves to more than one field.

    Real COBOL compilers reject this at compile time; the programmer must
    qualify with IN/OF (e.g. ``WS-ID OF WS-SUB``) to disambiguate.
    """

    def __init__(self, name: str):
        super().__init__(
            f"*** Guru Meditation Error #00A18105.C0BF1E1D ***\n"
            f"Ambiguous reference to {name!r} — declared in more than one "
            f"place in this record. Qualify with IN/OF (e.g. '{name} OF "
            f"<group-name>') to disambiguate."
        )


# Generic value type for the case-insensitive dict lookup helper.
_V = TypeVar("_V")


def _ci_get(mapping: dict[str, _V], name: str) -> _V | None:
    """Look up ``name`` in ``mapping`` case-insensitively.

    COBOL identifiers are case-insensitive, but the layout preserves the
    verbatim declared name as the dict key (e.g. ``Vstring-length`` from
    CardDemo CSUTLDTC). A direct hit is preferred; otherwise the first key
    whose upper-case form matches ``name`` upper-cased is returned. Field names
    are unique within a record, so at most one case-insensitive match exists.
    """
    direct = mapping.get(name)
    if direct is not None:
        return direct
    upper = name.upper()
    for key, value in mapping.items():
        if key.upper() == upper:
            return value
    return None


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
    value_is_figurative: bool = False
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
    holds_address: bool = False
    span: SourceSpan | None = None
    """Where this field was declared, or None for compiler-allocated items.

    OCCURS elements inherit their parent's span: a subscripted access and
    its declaration share a source line. Index items have none — they
    correspond to no source text.
    """


@dataclass(frozen=True)
class OccursTable:
    """A declared OCCURS construct, as a bounded byte span.

    ``offset`` is where occurrence 1 starts, ``element_size`` the subscript
    stride, and ``total_bytes`` the whole table. This is the tightest
    *declared* bound an access with a computed subscript can be clamped to:
    the index is unknown, but it cannot escape the table.
    """

    offset: int
    element_size: int
    occurs_count: int

    @property
    def total_bytes(self) -> int:
        return self.element_size * self.occurs_count


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
        index_owner: index name -> the OCCURS item it indexes. Populated only
            on the index-item layout built by :func:`build_index_layout`; a
            Format 1 SEARCH names only the table, so this is how its implicit
            index is found. Query it via :meth:`first_index_for`, never by
            exact-match dict access.
        occurs_depending_on: The OCCURS DEPENDING ON object of a variable
            table; empty for a fixed one.
    """

    fields: dict[str, FieldLayout] = field(default_factory=dict)
    groups: dict[str, DataLayout] = field(default_factory=dict)
    offset: int = 0
    total_bytes: int = 0
    occurs_count: int = 0
    element_size: int = 0
    conditions: list[ConditionName] = field(default_factory=list)
    index_owner: dict[str, str] = field(default_factory=dict)
    span: SourceSpan | None = None
    value: str = ""
    value_is_figurative: bool = False
    occurs_depending_on: str = ""
    renames: dict[str, FieldLayout] = field(default_factory=dict)

    def lookup(self, name: str) -> FieldLayout | None:
        """Search for a leaf field by bare name within this subtree.

        Field names should be unique within the subtree rooted at ``self``;
        if the bare name resolves to more than one field at different
        nesting levels, that is a genuine program error and raises
        :class:`CobolAmbiguousReferenceError` (real COBOL compilers reject
        this at compile time, requiring IN/OF qualification); a qualified
        reference resolves through :meth:`qualified_matches`.

        COBOL identifiers are case-insensitive: a field declared ``Vstring-length``
        (e.g. CardDemo CSUTLDTC) is referenced as ``VSTRING-LENGTH`` from the
        PROCEDURE DIVISION, so the match is done case-insensitively while the
        verbatim declared name is preserved on the FieldLayout.
        """
        matches = self._find_all(name)
        if len(matches) > 1:
            raise CobolAmbiguousReferenceError(name)
        return matches[0] if matches else None

    def _find_all(self, name: str) -> list[FieldLayout]:
        """Collect every leaf field matching ``name`` (case-insensitive) in this subtree."""
        results = []
        direct = _ci_get(self.fields, name)
        if direct is not None:
            results.append(direct)
        for sub in self.groups.values():
            results.extend(sub._find_all(name))
        return results

    def exists(self, name: str) -> bool:
        """True if ``name`` names at least one item here, elementary, group or
        level-66 — a pure existence check that never raises on ambiguity. Use
        :meth:`qualified_matches` to resolve a reference to one item."""
        return any(match.name.upper() == name.upper() for match in self.items())

    def is_index_of(self, index_name: str, table_name: str) -> bool:
        """Whether ``index_name`` is one of the ``INDEXED BY`` names of ``table_name``,
        compared case-insensitively as :meth:`first_index_for` does."""
        return any(
            name.upper() == index_name.upper() and owner.upper() == table_name.upper()
            for name, owner in self.index_owner.items()
        )

    def first_index_for(self, table_name: str) -> str | None:
        """Return the first ``INDEXED BY`` name declared on ``table_name``, or None.

        A Format 1 SEARCH names only the table and implicitly uses its first
        index; ``index_owner`` preserves declaration order, so the first match
        wins. Both sides are compared case-insensitively — the table name is
        lexed from a SEARCH statement and need not match the DATA DIVISION's
        casing.
        """
        wanted = table_name.upper()
        for index_name, owner in self.index_owner.items():
            if owner.upper() == wanted:
                return index_name
        return None

    def lookup_or_raise(self, name: str) -> FieldLayout:
        result = self.lookup(name)
        if result is None:
            raise KeyError(f"Field not found in layout: {name!r}")
        return result

    def qualified_matches(
        self, name: str, qualifiers: Sequence[str]
    ) -> tuple[DataItemMatch, ...]:
        """Every data item, elementary or group, that ``name`` qualified by
        ``qualifiers`` (innermost first, as written) can denote: empty when none,
        one when the reference is unique; more than one raises
        :class:`CobolAmbiguousReferenceError`."""
        found = tuple(
            match
            for match in self.items()
            if match.name.upper() == name.upper() and match.qualified_by(qualifiers)
        )
        if len(found) > 1:
            raise CobolAmbiguousReferenceError(name)
        return found

    def items(self) -> Iterator[DataItemMatch]:
        """Every elementary and group item in this subtree, depth-first, each
        with the groups enclosing it."""
        return self._items(())

    def _items(
        self, ancestors: tuple[tuple[str, DataLayout], ...]
    ) -> Iterator[DataItemMatch]:
        yield from (
            DataItemMatch(name, leaf, ancestors) for name, leaf in self.fields.items()
        )
        yield from (
            match
            for name, group in self.groups.items()
            for match in chain(
                (DataItemMatch(name, group, ancestors),),
                group._items((*ancestors, (name, group))),
                (
                    DataItemMatch(alias, renamed, (*ancestors, (name, group)))
                    for alias, renamed in group.renames.items()
                ),
            )
        )

    def lookup_group(self, name: str) -> DataLayout:
        """Return a nested DataLayout by group name; raises KeyError if not found.

        Matched case-insensitively (COBOL identifiers are case-insensitive)."""
        direct = _ci_get(self.groups, name)
        if direct is not None:
            return direct
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
                span=grp.span,
                value=grp.value,
                value_is_figurative=grp.value_is_figurative,
                occurs_depending_on=grp.occurs_depending_on,
            )
            # Recurse into group's children
            yield from grp.all_fields()

    def lookup_as_storage(
        self, name: str, qualifiers: tuple[str, ...] = ()
    ) -> FieldLayout | None:
        """The storage ``name`` qualified by ``qualifiers`` denotes — an elementary
        item's own FieldLayout, or an alphanumeric one synthesised over a group —
        or None when nothing here matches."""
        found = self.qualified_matches(name, qualifiers)
        return found[0].storage if found else None


@dataclass(frozen=True)
class DataItemMatch:
    """A data item found by name, with the groups containing it, outermost first."""

    name: str
    item: FieldLayout | DataLayout
    ancestors: tuple[tuple[str, DataLayout], ...]

    def qualified_by(self, qualifiers: Sequence[str]) -> bool:
        enclosing = iter(key.upper() for key, _ in reversed(self.ancestors))
        return all(qualifier.upper() in enclosing for qualifier in qualifiers)

    @property
    def storage(self) -> FieldLayout:
        if isinstance(self.item, FieldLayout):
            return self.item
        return _group_storage(self.name, self.item)

    @property
    def tables(self) -> tuple[OccursTable, ...]:
        return tuple(
            OccursTable(group.offset, group.element_size, group.occurs_count)
            for group in (*(group for _, group in self.ancestors), self.item)
            if group.occurs_count > 0 and group.element_size > 0
        )

    @property
    def record_extent(self) -> tuple[int, int]:
        record = _group_storage(*self.ancestors[0]) if self.ancestors else self.storage
        return record.offset, record.byte_length


def _group_storage(name: str, group: DataLayout) -> FieldLayout:
    return FieldLayout(
        name=name,
        type_descriptor=CobolTypeDescriptor(
            category=CobolDataCategory.ALPHANUMERIC, total_digits=group.total_bytes
        ),
        offset=group.offset,
        byte_length=group.total_bytes,
        occurs_count=group.occurs_count,
        element_size=(
            group.element_size if group.element_size > 0 else group.total_bytes
        ),
        span=group.span,
        occurs_depending_on=group.occurs_depending_on,
    )


def _placed_child_extent(
    cobol_field: CobolField,
    sub_fields: dict[str, FieldLayout],
    sub_groups: dict[str, DataLayout],
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
            conditions=list(cobol_field.conditions),
            span=cobol_field.span,
            value=cobol_field.value,
            value_is_figurative=cobol_field.value_is_figurative,
            occurs_depending_on=cobol_field.occurs_depending_on,
        )
        return cobol_field.name, group_layout

    # Elementary leaf — PIC was parsed once at ingestion.
    type_desc = cobol_field.type_descriptor
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
        value_is_figurative=cobol_field.value_is_figurative,
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
        holds_address=cobol_field.usage == "POINTER",
        span=cobol_field.span,
    )
    return cobol_field.name, fl


def record_length(cobol_field: CobolField) -> int:
    """How many bytes a record occupies, REDEFINES children not counted."""
    return _compute_group_length(cobol_field)


def _compute_group_length(cobol_field: CobolField) -> int:
    """Compute the byte length of a group item from its children.

    REDEFINES children share the same offset and do NOT increase
    the group's total size. OCCURS fields multiply their element
    size by the occurrence count.
    """
    if not cobol_field.children:
        element_length = cobol_field.type_descriptor.byte_length
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
    record_name: str,
    record: DataLayout,
) -> FieldLayout:
    """Resolve a level-66 RENAMES field into a FieldLayout.

    RENAMES creates an alias over a contiguous range of the items of the 01
    record it follows: offset = from item's offset, byte length = span from the
    from item through the thru item (or the from item alone if no THRU). Either
    item may be elementary or a group, and is qualified as written, with the
    record itself a valid qualifier.
    """
    scope = DataLayout(groups={record_name: record})
    thru = renames_field.renames_thru
    from_storage = _renamed_storage(scope, renames_field.renames_from)
    thru_storage = _renamed_storage(
        scope, thru if thru.name else renames_field.renames_from
    )
    offset = from_storage.offset
    byte_length = (thru_storage.offset + thru_storage.byte_length) - offset

    logger.debug(
        "RENAMES %s: from=%s thru=%s offset=%d length=%d",
        renames_field.name,
        renames_field.renames_from.name,
        thru.name,
        offset,
        byte_length,
    )

    return FieldLayout(
        name=renames_field.name,
        type_descriptor=_RENAMES_TYPE_DESCRIPTOR,
        offset=offset,
        byte_length=byte_length,
        renames_from=renames_field.renames_from.name,
        renames_thru=thru.name,
        span=renames_field.span,
    )


def _renamed_storage(scope: DataLayout, operand: RefModOperand) -> FieldLayout:
    found = scope.qualified_matches(operand.name, operand.qualifiers)
    if not found:
        raise KeyError(f"RENAMES operand not found in its record: {operand.name!r}")
    return found[0].storage


def _owned_renames(fields: Sequence[CobolField]) -> list[tuple[CobolField, str]]:
    """Each level-66 item with the 01 record immediately preceding it."""
    return [
        (
            f,
            next(
                record.name
                for record in reversed(fields[:position])
                if not record.renames_from.name
            ),
        )
        for position, f in enumerate(fields)
        if f.renames_from.name
    ]


def laid_end_to_end(fields: Sequence[CobolField]) -> list[CobolField]:
    """Top-level items at consecutive offsets in the order given. A REDEFINES or
    RENAMES item takes its position from what it names, so it keeps its own and
    occupies no bytes of the run."""
    spans = [0 if _positioned_by_name(f) else _compute_group_length(f) for f in fields]
    return [
        f if _positioned_by_name(f) else replace(f, offset=end - span)
        for f, span, end in zip(fields, spans, accumulate(spans), strict=True)
    ]


def _positioned_by_name(f: CobolField) -> bool:
    return bool(f.redefines or f.renames_from.name)


def build_data_layout(fields: list[CobolField]) -> DataLayout:
    """Build a recursive DataLayout from a list of top-level CobolField trees.

    Args:
        fields: Top-level DATA DIVISION fields (level 01/77 items).

    Returns:
        A DataLayout with fields/groups split and total_bytes computed.
    """
    non_renames_fields = [f for f in fields if not f.renames_from.name]
    top_fields: dict[str, FieldLayout] = {}
    top_groups: dict[str, DataLayout] = {}
    for f in non_renames_fields:
        name, result = _flatten_field(f, 0, top_fields, top_groups)
        if isinstance(result, DataLayout):
            top_groups[name] = result
        else:
            top_fields[name] = result

    owned = _owned_renames(fields)
    renamed_groups = {
        name: replace(
            group,
            renames={
                f.name: _resolve_renames(f, name, group)
                for f, owner in owned
                if owner == name
            },
        )
        for name, group in top_groups.items()
    }

    non_redefines_top = [f for f in non_renames_fields if not f.redefines]
    total = sum(_compute_group_length(f) for f in non_redefines_top)

    logger.debug(
        "Data layout: %d top-level fields, %d top-level groups, %d total bytes",
        len(top_fields),
        len(top_groups),
        total,
    )

    return DataLayout(fields=top_fields, groups=renamed_groups, total_bytes=total)


_INDEX_ITEM_TYPE = CobolTypeDescriptor(
    category=CobolDataCategory.BINARY, total_digits=9
)


def _index_declarations(fields: list[CobolField]) -> Iterator[tuple[str, str]]:
    """Yield (index name, indexed table name) for every INDEXED BY, in source order."""
    for f in fields:
        for index_name in f.indexed_by:
            yield index_name, f.name
        yield from _index_declarations(f.children)


def build_index_layout(*sections: list[CobolField]) -> DataLayout:
    """Build the index-item region for every ``INDEXED BY`` name in ``sections``.

    ``OCCURS ... INDEXED BY IX`` is the only declaration IX ever gets (``01 IX
    PIC ...`` is an error), so the compiler allocates it. Index items belong to
    no record: they get their OWN region, exactly like RETURN-CODE in
    ``special_registers`` — which is also what keeps them out of LINKAGE, whose
    region is the caller's argument storage and is NOT sized from
    ``total_bytes``.

    Each item holds a 1-based occurrence NUMBER, not the byte displacement IBM
    stores. Nothing here reads an index's raw bytes, and a program cannot
    legally observe the difference: REDEFINES of an index and a group MOVE of
    one are both errors.
    """
    items: dict[str, FieldLayout] = {}
    owners: dict[str, str] = {}
    offset = 0
    for section in sections:
        for index_name, table_name in _index_declarations(section):
            items[index_name] = FieldLayout(
                name=index_name,
                type_descriptor=_INDEX_ITEM_TYPE,
                offset=offset,
                byte_length=_INDEX_ITEM_TYPE.byte_length,
            )
            owners[index_name] = table_name
            offset += _INDEX_ITEM_TYPE.byte_length
    return DataLayout(fields=items, total_bytes=offset, index_owner=owners)
