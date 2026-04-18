# MOVE CORRESPONDING + Recursive DataLayout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat `DataLayout.fields` dict (all descendants) with a recursive `fields`/`groups` structure, then implement MOVE CORRESPONDING lowering end-to-end (Python + Java bridge).

**Architecture:** `DataLayout` becomes a tree: `fields` holds direct elementary children, `groups` holds direct group children as nested `DataLayout`s. Recursive `lookup()`, `all_leaves()`, and `lookup_group()` replace direct dict access. `MoveCorrespondingStatement` is a new frozen dataclass; `lower_move_corresponding()` matches direct leaf names between source and destination groups. The Java bridge emits `MOVE_CORRESPONDING` JSON when `stmt.getMoveType() == MoveType.MOVE_CORRESPONDING`.

**Tech Stack:** Python 3.12, pytest, ProLeap COBOL parser (Java), Gson.

---

## File Map

| File | Action |
|---|---|
| `interpreter/cobol/data_layout.py` | **Rewrite** — recursive DataLayout, new `_flatten_field`, delete `_fix_redefines_offsets`/`_with_offset` |
| `interpreter/cobol/emit_context.py` | **Modify** — 4 `layout.fields[…]` sites + add `resolve_field_ref_from()` |
| `interpreter/cobol/condition_name_index.py` | **Modify** — `build_condition_index` takes `DataLayout`, iterates `all_leaves()` |
| `interpreter/cobol/cobol_frontend.py` | **Modify** — 2 sites: `all_leaves()` + `build_condition_index(layout)` |
| `interpreter/cobol/lower_data_division.py` | **Modify** — 1 site: `all_leaves()` |
| `interpreter/frontends/symbol_table.py` | **Modify** — 1 site: `all_leaves()` |
| `interpreter/cobol/cobol_statements.py` | **Modify** — add `MoveCorrespondingStatement` + `"MOVE_CORRESPONDING"` in `_DISPATCH_TABLE` + union type |
| `interpreter/cobol/lower_arithmetic.py` | **Modify** — delete `_leaf_fields_of`, rewrite `lower_initialize`, add `lower_move_corresponding` |
| `interpreter/cobol/statement_dispatch.py` | **Modify** — add `MoveCorrespondingStatement` branch |
| `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java` | **Modify** — MOVE_CORRESPONDING branch in `serializeMove` |
| `tests/unit/test_data_layout.py` | **Migrate + extend** — `layout.fields["X"]` → `layout.lookup("X")` (all 86 sites), new test classes |
| `tests/unit/test_occurs_layout.py` | **Migrate** — group field accesses |
| `tests/unit/test_lower_move_corresponding.py` | **Create** — unit tests with mock EmitContext |
| `tests/integration/test_cobol_move_corresponding.py` | **Create** — full VM execution tests |
| `tests/integration/test_cobol_redefines_complex.py` | **Create** — complex REDEFINES VM execution tests |

---

## Task 1: Write failing tests for new DataLayout recursive API

**Files:**
- Modify: `tests/unit/test_data_layout.py`

- [ ] **Step 1.1: Add the failing test class to `test_data_layout.py`**

Append to the end of `tests/unit/test_data_layout.py`:

```python
class TestBuildDataLayoutMoveCorresponding:
    def test_lookup_group_returns_datalayout(self):
        """lookup_group('WS-SRC') returns a DataLayout with direct leaf fields."""
        fields = [
            CobolField(
                name="WS-SRC",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-A", level=5, pic="X(5)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="WS-B", level=5, pic="X(5)", usage="DISPLAY", offset=5
                    ),
                ],
            ),
            CobolField(
                name="WS-DST",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-A", level=5, pic="X(5)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="WS-C", level=5, pic="X(5)", usage="DISPLAY", offset=5
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        src = layout.lookup_group("WS-SRC")
        dst = layout.lookup_group("WS-DST")
        assert "WS-A" in src.fields
        assert "WS-B" in src.fields
        assert "WS-A" in dst.fields
        assert "WS-C" in dst.fields
        # Matching names: only WS-A
        matching = src.fields.keys() & dst.fields.keys()
        assert matching == {"WS-A"}
        # Non-matching fields absent
        assert "WS-B" not in dst.fields
        assert "WS-C" not in src.fields

    def test_no_flat_dict_collision_same_child_name(self):
        """WS-SRC.WS-A and WS-DST.WS-A do not overwrite each other."""
        fields = [
            CobolField(
                name="WS-SRC",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-A", level=5, pic="X(3)", usage="DISPLAY", offset=0
                    ),
                ],
            ),
            CobolField(
                name="WS-DST",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=3,
                children=[
                    CobolField(
                        name="WS-A", level=5, pic="9(4)", usage="DISPLAY", offset=0
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        src_a = layout.lookup_group("WS-SRC").fields["WS-A"]
        dst_a = layout.lookup_group("WS-DST").fields["WS-A"]
        assert src_a.byte_length == 3
        assert dst_a.byte_length == 4
        assert src_a.offset == 0
        assert dst_a.offset == 3

    def test_lookup_returns_leaf_by_name(self):
        fields = [
            CobolField(
                name="WS-REC",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-X", level=5, pic="9(2)", usage="DISPLAY", offset=0
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        fl = layout.lookup("WS-X")
        assert fl is not None
        assert fl.name == "WS-X"
        assert fl.byte_length == 2

    def test_all_leaves_yields_elementary_fields(self):
        fields = [
            CobolField(
                name="WS-REC",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-X", level=5, pic="9(2)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="WS-Y", level=5, pic="X(3)", usage="DISPLAY", offset=2
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        leaves = list(layout.all_leaves())
        names = {fl.name for fl in leaves}
        assert names == {"WS-X", "WS-Y"}


class TestBuildDataLayoutRedefinesComplex:
    def test_multiple_redefines_of_same_field(self):
        """B REDEFINES A, C REDEFINES A — both at A's offset; total_bytes unchanged."""
        fields = [
            CobolField(
                name="WS-A", level=77, pic="X(4)", usage="DISPLAY", offset=0
            ),
            CobolField(
                name="WS-B",
                level=77,
                pic="9(4)",
                usage="DISPLAY",
                offset=0,
                redefines="WS-A",
            ),
            CobolField(
                name="WS-C",
                level=77,
                pic="X(4)",
                usage="DISPLAY",
                offset=0,
                redefines="WS-A",
            ),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 4
        a = layout.lookup("WS-A")
        b = layout.lookup("WS-B")
        c = layout.lookup("WS-C")
        assert a is not None and a.offset == 0
        assert b is not None and b.offset == 0
        assert c is not None and c.offset == 0

    def test_chained_redefines(self):
        """A, B REDEFINES A, C REDEFINES B — C ends up at A's offset."""
        fields = [
            CobolField(
                name="WS-A", level=77, pic="X(4)", usage="DISPLAY", offset=0
            ),
            CobolField(
                name="WS-B",
                level=77,
                pic="9(4)",
                usage="DISPLAY",
                offset=0,
                redefines="WS-A",
            ),
            CobolField(
                name="WS-C",
                level=77,
                pic="X(4)",
                usage="DISPLAY",
                offset=0,
                redefines="WS-B",
            ),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 4
        assert layout.lookup("WS-C").offset == 0  # type: ignore[union-attr]

    def test_group_redefines_elementary(self):
        """A group B REDEFINES an elementary A — group gets A's offset."""
        fields = [
            CobolField(
                name="WS-A", level=77, pic="X(4)", usage="DISPLAY", offset=0
            ),
            CobolField(
                name="WS-B",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                redefines="WS-A",
                children=[
                    CobolField(
                        name="WS-B1",
                        level=5,
                        pic="X(2)",
                        usage="DISPLAY",
                        offset=0,
                    ),
                    CobolField(
                        name="WS-B2",
                        level=5,
                        pic="X(2)",
                        usage="DISPLAY",
                        offset=2,
                    ),
                ],
            ),
        ]
        layout = build_data_layout(fields)
        assert layout.total_bytes == 4
        b_layout = layout.lookup_group("WS-B")
        assert b_layout.offset == 0
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
cd /Users/asgupta/code/red-dragon
poetry run python -m pytest tests/unit/test_data_layout.py::TestBuildDataLayoutMoveCorresponding tests/unit/test_data_layout.py::TestBuildDataLayoutRedefinesComplex -v 2>&1 | tail -20
```

Expected: FAIL with `AttributeError: 'DataLayout' object has no attribute 'lookup_group'`

---

## Task 2: Rewrite `data_layout.py` — recursive DataLayout

**Files:**
- Modify: `interpreter/cobol/data_layout.py`

- [ ] **Step 2.1: Replace the entire file**

```python
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
        group_length = _compute_group_length(cobol_field)
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
```

- [ ] **Step 2.2: Run the new failing tests — they should now pass**

```bash
poetry run python -m pytest tests/unit/test_data_layout.py::TestBuildDataLayoutMoveCorresponding tests/unit/test_data_layout.py::TestBuildDataLayoutRedefinesComplex -v 2>&1 | tail -20
```

Expected: All PASS.

- [ ] **Step 2.3: Run the existing test_data_layout.py suite to see what breaks**

```bash
poetry run python -m pytest tests/unit/test_data_layout.py -v 2>&1 | grep -E "PASSED|FAILED|ERROR" | head -40
```

Expected: Several FAIL — tests still use `layout.fields["X"]` for group items and nested children that are now in `layout.groups`.

---

## Task 3: Migrate `test_data_layout.py` and `test_occurs_layout.py`

**Files:**
- Modify: `tests/unit/test_data_layout.py`
- Modify: `tests/unit/test_occurs_layout.py`

Groups that had children are now in `layout.groups`; their children are reachable via `layout.lookup("X")`. Top-level elementary fields (level 77) remain in `layout.fields` but `.lookup()` also works for them.

- [ ] **Step 3.1: Migrate `TestBuildDataLayoutGroup` in `test_data_layout.py`**

Replace `test_group_with_children` method:

```python
def test_group_with_children(self):
    fields = [
        CobolField(
            name="WS-DATE",
            level=1,
            pic="",
            usage="DISPLAY",
            offset=0,
            children=[
                CobolField(
                    name="WS-YEAR", level=5, pic="9(4)", usage="DISPLAY", offset=0
                ),
                CobolField(
                    name="WS-MONTH", level=5, pic="99", usage="DISPLAY", offset=4
                ),
                CobolField(
                    name="WS-DAY", level=5, pic="99", usage="DISPLAY", offset=6
                ),
            ],
        ),
    ]
    layout = build_data_layout(fields)
    assert layout.total_bytes == 8
    # WS-DATE is a group — use lookup_group for structural check
    date_grp = layout.lookup_group("WS-DATE")
    assert date_grp.total_bytes == 8
    # Children are leaves — use lookup()
    assert layout.lookup("WS-YEAR").offset == 0       # type: ignore[union-attr]
    assert layout.lookup("WS-YEAR").byte_length == 4  # type: ignore[union-attr]
    assert layout.lookup("WS-MONTH").offset == 4      # type: ignore[union-attr]
    assert layout.lookup("WS-MONTH").byte_length == 2 # type: ignore[union-attr]
    assert layout.lookup("WS-DAY").offset == 6        # type: ignore[union-attr]
    assert layout.lookup("WS-DAY").byte_length == 2   # type: ignore[union-attr]
```

- [ ] **Step 3.2: Migrate `TestBuildDataLayoutRedefines` in `test_data_layout.py`**

Replace `test_redefines_shares_offset`:

```python
def test_redefines_shares_offset(self):
    fields = [
        CobolField(
            name="WS-DATE",
            level=1,
            pic="",
            usage="DISPLAY",
            offset=0,
            children=[
                CobolField(
                    name="WS-YEAR", level=5, pic="9(4)", usage="DISPLAY", offset=0
                ),
                CobolField(
                    name="WS-MONTH", level=5, pic="99", usage="DISPLAY", offset=4
                ),
                CobolField(
                    name="WS-DAY", level=5, pic="99", usage="DISPLAY", offset=6
                ),
            ],
        ),
        CobolField(
            name="WS-DATE-NUM",
            level=1,
            pic="9(8)",
            usage="DISPLAY",
            offset=0,
            redefines="WS-DATE",
        ),
    ]
    layout = build_data_layout(fields)
    assert layout.total_bytes == 8
    fl = layout.lookup("WS-DATE-NUM")
    assert fl is not None
    assert fl.offset == 0
    assert fl.byte_length == 8
    assert fl.redefines == "WS-DATE"
```

- [ ] **Step 3.3: Migrate `TestBuildDataLayoutNestedGroups` in `test_data_layout.py`**

Replace `test_nested_group`:

```python
def test_nested_group(self):
    fields = [
        CobolField(
            name="WS-REC",
            level=1,
            pic="",
            usage="DISPLAY",
            offset=0,
            children=[
                CobolField(
                    name="WS-HEADER",
                    level=5,
                    pic="",
                    usage="DISPLAY",
                    offset=0,
                    children=[
                        CobolField(
                            name="WS-ID",
                            level=10,
                            pic="9(3)",
                            usage="DISPLAY",
                            offset=0,
                        ),
                        CobolField(
                            name="WS-TYPE",
                            level=10,
                            pic="X(2)",
                            usage="DISPLAY",
                            offset=3,
                        ),
                    ],
                ),
                CobolField(
                    name="WS-BODY",
                    level=5,
                    pic="X(20)",
                    usage="DISPLAY",
                    offset=5,
                ),
            ],
        ),
    ]
    layout = build_data_layout(fields)
    assert layout.total_bytes == 25
    header_grp = layout.lookup_group("WS-HEADER")
    assert header_grp.total_bytes == 5
    assert layout.lookup("WS-ID").offset == 0     # type: ignore[union-attr]
    assert layout.lookup("WS-TYPE").offset == 3   # type: ignore[union-attr]
    assert layout.lookup("WS-BODY").offset == 5   # type: ignore[union-attr]
```

- [ ] **Step 3.4: Migrate `TestBuildDataLayoutOccursDependingOn` in `test_data_layout.py`**

Replace `test_occurs_depending_on_propagated`:

```python
def test_occurs_depending_on_propagated(self):
    fields = [
        CobolField(
            name="WS-REC",
            level=1,
            pic="",
            usage="DISPLAY",
            offset=0,
            children=[
                CobolField(
                    name="WS-COUNT",
                    level=5,
                    pic="9(3)",
                    usage="DISPLAY",
                    offset=0,
                ),
                CobolField(
                    name="WS-ITEMS",
                    level=5,
                    pic="X(10)",
                    usage="DISPLAY",
                    offset=3,
                    occurs=20,
                    element_size=10,
                    occurs_depending_on="WS-COUNT",
                    occurs_min=1,
                ),
            ],
        ),
    ]
    layout = build_data_layout(fields)
    fl = layout.lookup("WS-ITEMS")
    assert fl is not None
    assert fl.occurs_depending_on == "WS-COUNT"
    assert fl.occurs_min == 1
    assert fl.byte_length == 200  # 20 * 10
```

- [ ] **Step 3.5: Migrate `TestBuildDataLayoutRenames` in `test_data_layout.py`**

Replace both renames test methods:

```python
def test_simple_renames(self):
    """Level 66 RENAMES single field — offset and length match the target."""
    fields = [
        CobolField(
            name="WS-REC",
            level=1,
            pic="",
            usage="DISPLAY",
            offset=0,
            children=[
                CobolField(
                    name="WS-FIRST",
                    level=5,
                    pic="X(10)",
                    usage="DISPLAY",
                    offset=0,
                ),
                CobolField(
                    name="WS-LAST",
                    level=5,
                    pic="X(10)",
                    usage="DISPLAY",
                    offset=10,
                ),
            ],
        ),
        CobolField(
            name="WS-ALIAS",
            level=66,
            pic="",
            usage="DISPLAY",
            offset=0,
            renames_from="WS-FIRST",
        ),
    ]
    layout = build_data_layout(fields)
    fl = layout.lookup("WS-ALIAS")
    assert fl is not None
    assert fl.offset == 0
    assert fl.byte_length == 10
    assert fl.renames_from == "WS-FIRST"
    assert fl.renames_thru == ""
    assert layout.total_bytes == 20

def test_renames_thru(self):
    """Level 66 RENAMES A THRU C — offset = A.offset, length spans through C."""
    fields = [
        CobolField(
            name="WS-REC",
            level=1,
            pic="",
            usage="DISPLAY",
            offset=0,
            children=[
                CobolField(
                    name="WS-A",
                    level=5,
                    pic="X(5)",
                    usage="DISPLAY",
                    offset=0,
                ),
                CobolField(
                    name="WS-B",
                    level=5,
                    pic="X(3)",
                    usage="DISPLAY",
                    offset=5,
                ),
                CobolField(
                    name="WS-C",
                    level=5,
                    pic="X(7)",
                    usage="DISPLAY",
                    offset=8,
                ),
            ],
        ),
        CobolField(
            name="WS-SPAN",
            level=66,
            pic="",
            usage="DISPLAY",
            offset=0,
            renames_from="WS-A",
            renames_thru="WS-C",
        ),
    ]
    layout = build_data_layout(fields)
    fl = layout.lookup("WS-SPAN")
    assert fl is not None
    assert fl.offset == 0
    assert fl.byte_length == 15
    assert fl.renames_from == "WS-A"
    assert fl.renames_thru == "WS-C"
    assert layout.total_bytes == 15
```

- [ ] **Step 3.6: Migrate simple-field tests — replace `.fields["X"]` with `.lookup("X")`**

In `TestBuildDataLayoutSingleField`, `TestBuildDataLayoutMultipleTopLevel`, `TestBuildDataLayoutCompTypes`, `TestBuildDataLayoutOccursDependingOn.test_occurs_depending_on_uses_max_storage`, `TestBuildDataLayoutSignClause`, `TestBuildDataLayoutBlankWhenZero`, and `TestBuildDataLayoutFieldValue`, every `layout.fields["WS-X"]` becomes `layout.lookup("WS-X")`.

Also `"WS-A" in layout.fields` → `layout.lookup("WS-A") is not None`, and `len(layout.fields) == 2` → `sum(1 for _ in layout.all_leaves()) == 2`.

Apply all of these changes now. The pattern is mechanical: `layout.fields["X"]` → `layout.lookup("X")` (with optional `# type: ignore[union-attr]` if the result is used without an assert-not-None).

- [ ] **Step 3.7: Migrate `test_occurs_layout.py`**

`TestElementaryOccurs`: level-77 fields stay in `layout.fields` but use `layout.lookup("X")` for consistency:

```python
# In test_elementary_occurs_multiplies_length:
fl = layout.lookup("WS-TBL")
assert fl is not None
assert fl.byte_length == 20
assert fl.occurs_count == 5
assert fl.element_size == 4

# In test_non_occurs_field_unaffected:
fl = layout.lookup("WS-PLAIN")
assert fl is not None
assert fl.byte_length == 4
assert fl.occurs_count == 0

# In test_occurs_with_following_field:
assert layout.lookup("WS-TBL").byte_length == 12   # type: ignore[union-attr]
assert layout.lookup("WS-AFTER").byte_length == 2  # type: ignore[union-attr]
```

`TestGroupOccurs.test_group_occurs_multiplies_total`: WS-GROUP has children, so it becomes a group:

```python
def test_group_occurs_multiplies_total(self):
    """Group item with OCCURS 3 containing 2-byte child → 6 bytes total."""
    fields = [
        CobolField(
            name="WS-GROUP",
            level=1,
            pic="",
            usage="DISPLAY",
            offset=0,
            occurs=3,
            element_size=2,
            children=[
                CobolField(
                    name="WS-ITEM",
                    level=5,
                    pic="9(2)",
                    usage="DISPLAY",
                    offset=0,
                ),
            ],
        ),
    ]
    layout = build_data_layout(fields)
    assert layout.total_bytes == 6
    grp = layout.lookup_group("WS-GROUP")
    assert grp.total_bytes == 6
    assert grp.occurs_count == 3
    assert grp.element_size == 2
    # Child field
    item = layout.lookup("WS-ITEM")
    assert item is not None
    assert item.byte_length == 2
    assert item.offset == 0
```

- [ ] **Step 3.8: Run the full migrated test suite**

```bash
poetry run python -m pytest tests/unit/test_data_layout.py tests/unit/test_occurs_layout.py -v 2>&1 | tail -30
```

Expected: All PASS.

- [ ] **Step 3.9: Commit**

```bash
git add interpreter/cobol/data_layout.py tests/unit/test_data_layout.py tests/unit/test_occurs_layout.py
git commit -m "feat(cobol): recursive DataLayout with lookup/lookup_group/all_leaves"
```

---

## Task 4: Migrate production callers

**Files:**
- Modify: `interpreter/cobol/condition_name_index.py`
- Modify: `interpreter/cobol/cobol_frontend.py`
- Modify: `interpreter/cobol/lower_data_division.py`
- Modify: `interpreter/frontends/symbol_table.py`
- Modify: `interpreter/cobol/emit_context.py`

- [ ] **Step 4.1: Update `condition_name_index.py`**

Change the signature of `build_condition_index` and its iteration. Replace the entire function:

```python
def build_condition_index(layout: "DataLayout") -> ConditionNameIndex:
    """Build a condition name index from a recursive DataLayout.

    Iterates all leaf fields depth-first and collects their level-88
    conditions into a lookup keyed by condition name.

    Args:
        layout: DataLayout (from build_data_layout).

    Returns:
        A ConditionNameIndex for use in condition lowering.
    """
    entries: dict[str, ConditionEntry] = {}

    for fl in layout.all_leaves():
        for condition in fl.conditions:
            entries[condition.name] = ConditionEntry(
                parent_field_name=fl.name,
                values=condition.values,
            )
            logger.debug(
                "Indexed condition %s -> parent %s with %d values",
                condition.name,
                fl.name,
                len(condition.values),
            )

    logger.info("Condition name index: %d entries", len(entries))
    return ConditionNameIndex(entries)
```

Also update the import at the top of the file — add `DataLayout` import:

```python
from interpreter.cobol.data_layout import DataLayout, FieldLayout
```

And add `TYPE_CHECKING` guard if needed (or just a regular import since `DataLayout` is used at runtime).

- [ ] **Step 4.2: Update `cobol_frontend.py` — 2 sites**

Line ~119 (`data_layout` property): change
```python
for name, fl in self._layout.fields.items()
```
to:
```python
for fl in self._layout.all_leaves()
```
with `fl.name` replacing `name`.

Line ~133 (`lower()` method): change
```python
condition_index = build_condition_index(layout.fields)
```
to:
```python
condition_index = build_condition_index(layout)
```

- [ ] **Step 4.3: Update `lower_data_division.py`**

Line 24: change
```python
fields_with_values = [fl for fl in layout.fields.values() if fl.value]
```
to:
```python
fields_with_values = [fl for fl in layout.all_leaves() if fl.value]
```

- [ ] **Step 4.4: Update `symbol_table.py`**

Lines ~84-93: change
```python
fields = {
    FieldName(name): FieldInfo(...)
    for name, fl in layout.fields.items()
}
```
to:
```python
fields = {
    FieldName(fl.name): FieldInfo(
        name=FieldName(fl.name),
        type_hint=(
            fl.type_descriptor.pic if hasattr(fl.type_descriptor, "pic") else ""
        ),
        has_initializer=bool(fl.value),
    )
    for fl in layout.all_leaves()
}
```

- [ ] **Step 4.5: Update `emit_context.py` — 4 sites + new method**

**Site 1 — `resolve_field_ref` line ~183:**

```python
# Before:
fl = layout.fields[base_name]
# After:
fl = layout.lookup_as_storage(base_name)
assert fl is not None, f"Field or group not found in layout: {base_name!r}"
```

**Site 2 — `resolve_field_ref` subscript lines ~197-199:**

```python
# Before:
if sub_base in layout.fields:
    sub_fl = layout.fields[sub_base]
    idx_reg = self.emit_decode_field(region_reg, sub_fl)
# After:
sub_fl = layout.lookup(sub_base)
if sub_fl is not None:
    idx_reg = self.emit_decode_field(region_reg, sub_fl)
```

**Site 3 — `has_field` line ~256:**

```python
# Before:
return base_name in layout.fields
# After:
return layout.lookup_as_storage(base_name) is not None
```

**New method — add after `has_field`:**

```python
def resolve_field_ref_from(self, fl: FieldLayout, region_reg: str) -> ResolvedFieldRef:
    """Resolve a FieldLayout to a ResolvedFieldRef without a name lookup.

    Used when the FieldLayout is already known (e.g. MOVE CORRESPONDING).
    """
    offset_reg = self.fresh_reg()
    self.emit_inst(Const(result_reg=offset_reg, value=fl.offset))
    return ResolvedFieldRef(fl=fl, offset_reg=offset_reg)
```

- [ ] **Step 4.6: Run the full COBOL test suite**

```bash
poetry run python -m pytest tests/unit/ tests/integration/ -k "cobol" --tb=short 2>&1 | tail -30
```

Expected: All COBOL tests pass. If any fail, check whether the failure is in a test that used `layout.fields["X"]` for group items.

- [ ] **Step 4.7: Run the full test suite**

```bash
poetry run python -m pytest tests/ --tb=short -q 2>&1 | tail -20
```

Expected: All tests pass (same count as before this task).

- [ ] **Step 4.8: Commit**

```bash
git add interpreter/cobol/condition_name_index.py interpreter/cobol/cobol_frontend.py interpreter/cobol/lower_data_division.py interpreter/frontends/symbol_table.py interpreter/cobol/emit_context.py
git commit -m "refactor(cobol): migrate all DataLayout callers to recursive API"
```

---

## Task 5: Add `MoveCorrespondingStatement` to `cobol_statements.py`

**Files:**
- Modify: `interpreter/cobol/cobol_statements.py`

- [ ] **Step 5.1: Write a failing test for statement parsing**

Append to `tests/unit/test_cobol_statements.py` (or create it if missing):

```python
def test_parse_move_corresponding_statement():
    from interpreter.cobol.cobol_statements import parse_statement, MoveCorrespondingStatement
    data = {
        "type": "MOVE_CORRESPONDING",
        "source": "WS-SRC",
        "targets": ["WS-DST1", "WS-DST2"],
    }
    stmt = parse_statement(data)
    assert isinstance(stmt, MoveCorrespondingStatement)
    assert stmt.source == "WS-SRC"
    assert stmt.targets == ["WS-DST1", "WS-DST2"]
```

- [ ] **Step 5.2: Run to confirm it fails**

```bash
poetry run python -m pytest tests/unit/test_cobol_statements.py::test_parse_move_corresponding_statement -v 2>&1 | tail -10
```

Expected: FAIL with `ValueError: Unknown COBOL statement type: 'MOVE_CORRESPONDING'`

- [ ] **Step 5.3: Add `MoveCorrespondingStatement` class to `cobol_statements.py`**

After line 80 (after the `CobolStatementType` Union ends with `"DeleteStatement"`), insert `"MoveCorrespondingStatement"` into the Union:

```python
CobolStatementType = Union[
    "MoveStatement",
    "MoveCorrespondingStatement",   # add this line
    "ArithmeticStatement",
    # ... (all existing members unchanged) ...
    "DeleteStatement",
]
```

Then, before `_ARITHMETIC_TYPES` (near line 901), add the new dataclass. Place it after `MoveStatement`'s class definition:

```python
@dataclass(frozen=True)
class MoveCorrespondingStatement:
    """MOVE CORRESPONDING src TO dst1 [dst2 ...]."""

    source: str
    targets: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "MoveCorrespondingStatement":
        return cls(
            source=data.get("source", ""),
            targets=list(data.get("targets", [])),
        )

    def to_dict(self) -> dict:
        return {
            "type": "MOVE_CORRESPONDING",
            "source": self.source,
            "targets": list(self.targets),
        }
```

Then add to `_DISPATCH_TABLE`:

```python
_DISPATCH_TABLE: dict[str, type] = {
    "MOVE": MoveStatement,
    "MOVE_CORRESPONDING": MoveCorrespondingStatement,  # add this line
    "ADD": ArithmeticStatement,
    # ... rest unchanged ...
}
```

- [ ] **Step 5.4: Run the test to confirm it passes**

```bash
poetry run python -m pytest tests/unit/test_cobol_statements.py::test_parse_move_corresponding_statement -v 2>&1 | tail -10
```

Expected: PASS.

- [ ] **Step 5.5: Commit**

```bash
git add interpreter/cobol/cobol_statements.py tests/unit/test_cobol_statements.py
git commit -m "feat(cobol): add MoveCorrespondingStatement type and dispatch"
```

---

## Task 6: Unit tests for `lower_move_corresponding`, then implement

**Files:**
- Create: `tests/unit/test_lower_move_corresponding.py`
- Modify: `interpreter/cobol/lower_arithmetic.py`
- Modify: `interpreter/cobol/statement_dispatch.py`

- [ ] **Step 6.1: Write failing unit tests**

Create `tests/unit/test_lower_move_corresponding.py`:

```python
"""Unit tests for lower_move_corresponding lowering function."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from interpreter.cobol.asg_types import CobolField
from interpreter.cobol.cobol_statements import MoveCorrespondingStatement
from interpreter.cobol.data_layout import DataLayout, FieldLayout, build_data_layout
from interpreter.cobol.lower_arithmetic import lower_move_corresponding
from interpreter.cobol.pic_parser import parse_pic


def _make_layout_with_groups() -> DataLayout:
    """WS-SRC(WS-A:X(5), WS-B:X(5)) and WS-DST(WS-A:X(5), WS-C:X(5))."""
    return build_data_layout(
        [
            CobolField(
                name="WS-SRC",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=0,
                children=[
                    CobolField(
                        name="WS-A", level=5, pic="X(5)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="WS-B", level=5, pic="X(5)", usage="DISPLAY", offset=5
                    ),
                ],
            ),
            CobolField(
                name="WS-DST",
                level=1,
                pic="",
                usage="DISPLAY",
                offset=10,
                children=[
                    CobolField(
                        name="WS-A", level=5, pic="X(5)", usage="DISPLAY", offset=0
                    ),
                    CobolField(
                        name="WS-C", level=5, pic="X(5)", usage="DISPLAY", offset=5
                    ),
                ],
            ),
        ]
    )


class TestLowerMoveCorresponding:
    def test_matched_fields_emit_decode_encode_pair(self):
        """One matching field (WS-A) → one decode/encode pair emitted."""
        layout = _make_layout_with_groups()
        ctx = MagicMock()
        ctx.fresh_reg.side_effect = ["r1", "r2", "r3", "r4"]
        ctx.emit_decode_field.return_value = "decoded_reg"
        ctx.emit_to_string.return_value = "str_reg"
        ctx.resolve_field_ref_from.side_effect = [
            MagicMock(offset_reg="src_off"),
            MagicMock(offset_reg="dst_off"),
        ]

        stmt = MoveCorrespondingStatement(source="WS-SRC", targets=["WS-DST"])
        lower_move_corresponding(ctx, stmt, layout, "region_r0")

        assert ctx.emit_decode_field.call_count == 1
        assert ctx.emit_to_string.call_count == 1
        assert ctx.emit_encode_and_write.call_count == 1

    def test_unmatched_fields_emit_nothing(self):
        """WS-B (only in src) and WS-C (only in dst) produce no instructions."""
        layout = _make_layout_with_groups()
        ctx = MagicMock()
        ctx.resolve_field_ref_from.return_value = MagicMock(offset_reg="off")
        ctx.emit_decode_field.return_value = "d"
        ctx.emit_to_string.return_value = "s"

        stmt = MoveCorrespondingStatement(source="WS-SRC", targets=["WS-DST"])
        lower_move_corresponding(ctx, stmt, layout, "region_r0")

        # Only WS-A matched — exactly 1 decode/encode
        assert ctx.emit_decode_field.call_count == 1
        assert ctx.emit_encode_and_write.call_count == 1

    def test_multiple_targets_each_receive_copy(self):
        """Two targets → two encode/write calls (one per target)."""
        layout = build_data_layout(
            [
                CobolField(
                    name="WS-SRC",
                    level=1,
                    pic="",
                    usage="DISPLAY",
                    offset=0,
                    children=[
                        CobolField(
                            name="WS-X", level=5, pic="9(3)", usage="DISPLAY", offset=0
                        ),
                    ],
                ),
                CobolField(
                    name="WS-DST1",
                    level=1,
                    pic="",
                    usage="DISPLAY",
                    offset=3,
                    children=[
                        CobolField(
                            name="WS-X", level=5, pic="9(3)", usage="DISPLAY", offset=0
                        ),
                    ],
                ),
                CobolField(
                    name="WS-DST2",
                    level=1,
                    pic="",
                    usage="DISPLAY",
                    offset=6,
                    children=[
                        CobolField(
                            name="WS-X", level=5, pic="9(3)", usage="DISPLAY", offset=0
                        ),
                    ],
                ),
            ]
        )
        ctx = MagicMock()
        ctx.resolve_field_ref_from.return_value = MagicMock(offset_reg="off")
        ctx.emit_decode_field.return_value = "d"
        ctx.emit_to_string.return_value = "s"

        stmt = MoveCorrespondingStatement(
            source="WS-SRC", targets=["WS-DST1", "WS-DST2"]
        )
        lower_move_corresponding(ctx, stmt, layout, "region_r0")

        # 2 targets × 1 matching field = 2 encode/write calls
        assert ctx.emit_encode_and_write.call_count == 2

    def test_no_matching_names_emits_nothing(self):
        """Groups with no common leaf names → no instructions at all."""
        layout = build_data_layout(
            [
                CobolField(
                    name="WS-SRC",
                    level=1,
                    pic="",
                    usage="DISPLAY",
                    offset=0,
                    children=[
                        CobolField(
                            name="WS-P", level=5, pic="X(2)", usage="DISPLAY", offset=0
                        ),
                    ],
                ),
                CobolField(
                    name="WS-DST",
                    level=1,
                    pic="",
                    usage="DISPLAY",
                    offset=2,
                    children=[
                        CobolField(
                            name="WS-Q", level=5, pic="X(2)", usage="DISPLAY", offset=0
                        ),
                    ],
                ),
            ]
        )
        ctx = MagicMock()

        stmt = MoveCorrespondingStatement(source="WS-SRC", targets=["WS-DST"])
        lower_move_corresponding(ctx, stmt, layout, "region_r0")

        ctx.emit_decode_field.assert_not_called()
        ctx.emit_encode_and_write.assert_not_called()
```

- [ ] **Step 6.2: Run to confirm tests fail**

```bash
poetry run python -m pytest tests/unit/test_lower_move_corresponding.py -v 2>&1 | tail -15
```

Expected: FAIL with `ImportError: cannot import name 'lower_move_corresponding'` (or attribute error from mock since function doesn't exist yet).

- [ ] **Step 6.3: Add `lower_move_corresponding` to `lower_arithmetic.py` and update imports**

In `lower_arithmetic.py`, first add the import for `MoveCorrespondingStatement`:

```python
from interpreter.cobol.cobol_statements import (
    ArithmeticStatement,
    ComputeStatement,
    ContinueStatement,
    DisplayStatement,
    EvaluateStatement,
    ExitStatement,
    GotoStatement,
    IfStatement,
    InitializeStatement,
    MoveCorrespondingStatement,
    MoveStatement,
    SetStatement,
    StopRunStatement,
    WhenOtherStatement,
    WhenStatement,
)
```

Delete `_leaf_fields_of` entirely (lines 264–297 of the original file).

Replace `lower_initialize` with this rewrite:

```python
def lower_initialize(
    ctx: EmitContext,
    stmt: InitializeStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """INITIALIZE field1 field2 — reset to type-appropriate defaults.

    For group items, each elementary (leaf) child is reset with the
    type-appropriate default: spaces for ALPHANUMERIC, zeros for numeric.
    """
    for operand in stmt.operands:
        leaf_fl = layout.lookup(operand)
        if leaf_fl is not None:
            leaf_fls: list[FieldLayout] = [leaf_fl]
        else:
            try:
                group = layout.lookup_group(operand)
                leaf_fls = list(group.all_leaves())
            except KeyError:
                logger.warning("INITIALIZE target %s not found in layout", operand)
                continue
        for lfl in leaf_fls:
            lfl_offset_reg = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=lfl_offset_reg, value=lfl.offset))
            td = lfl.type_descriptor
            if td.category == CobolDataCategory.ALPHANUMERIC:
                default = " " * td.total_digits
            else:
                default = "0"
            ctx.emit_field_encode(region_reg, lfl, default, lfl_offset_reg)
```

Also add `CobolDataCategory` to the import from `cobol_types`:

```python
from interpreter.cobol.cobol_types import CobolDataCategory
```

Add `lower_move_corresponding` after `lower_initialize`:

```python
def lower_move_corresponding(
    ctx: EmitContext,
    stmt: MoveCorrespondingStatement,
    layout: DataLayout,
    region_reg: str,
) -> None:
    """MOVE CORRESPONDING src TO dst — copy matching direct leaf fields."""
    src_layout = layout.lookup_group(stmt.source)

    for target_name in stmt.targets:
        dst_layout = layout.lookup_group(target_name)
        matching = src_layout.fields.keys() & dst_layout.fields.keys()

        for name in matching:
            src_fl = src_layout.fields[name]
            dst_fl = dst_layout.fields[name]

            src_ref = ctx.resolve_field_ref_from(src_fl, region_reg)
            decoded = ctx.emit_decode_field(region_reg, src_fl, src_ref.offset_reg)
            value_str = ctx.emit_to_string(decoded)

            dst_ref = ctx.resolve_field_ref_from(dst_fl, region_reg)
            ctx.emit_encode_and_write(region_reg, dst_fl, value_str, dst_ref.offset_reg)
```

- [ ] **Step 6.4: Run unit tests to confirm they pass**

```bash
poetry run python -m pytest tests/unit/test_lower_move_corresponding.py -v 2>&1 | tail -20
```

Expected: All PASS.

- [ ] **Step 6.5: Add dispatch in `statement_dispatch.py`**

Add import at top with the other arithmetic imports:

```python
from interpreter.cobol.cobol_statements import (
    ...
    MoveCorrespondingStatement,
    ...
)
```

Add to the `from interpreter.cobol.lower_arithmetic import (...)` block:

```python
    lower_move_corresponding,
```

Add the dispatch branch in `dispatch_statement`, after `isinstance(stmt, MoveStatement)`:

```python
    elif isinstance(stmt, MoveCorrespondingStatement):
        lower_move_corresponding(ctx, stmt, layout, region_reg)
```

- [ ] **Step 6.6: Run the full test suite**

```bash
poetry run python -m pytest tests/ -q --tb=short 2>&1 | tail -20
```

Expected: All tests pass.

- [ ] **Step 6.7: Commit**

```bash
git add interpreter/cobol/lower_arithmetic.py interpreter/cobol/statement_dispatch.py tests/unit/test_lower_move_corresponding.py
git commit -m "feat(cobol): add lower_move_corresponding and rewrite lower_initialize"
```

---

## Task 7: Update Java bridge — `serializeMove` in `StatementSerializer.java`

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java`

The ProLeap API for MOVE CORRESPONDING:
- `stmt.getMoveType()` returns `MoveStatement.MoveType` (inner enum: `MOVE_CORRESPONDING`, `MOVE_TO`)
- `stmt.getMoveCorrespondingToStatement()` returns `MoveCorrespondingToStatetement` (note: typo in ProLeap — one 't' missing in "Statement")
- `corr.getMoveToCorrespondingSendingArea().getSendingAreaCall()` returns `Call` (the source group)
- `corr.getReceivingAreaCalls()` returns `List<Call>` (the destination groups)

- [ ] **Step 7.1: Add new imports to `StatementSerializer.java`**

After the existing `import io.proleap.cobol.asg.metamodel.procedure.move.MoveToSendingArea;` line, add:

```java
import io.proleap.cobol.asg.metamodel.procedure.move.MoveCorrespondingToStatetement;
import io.proleap.cobol.asg.metamodel.procedure.move.MoveCorrespondingToSendingArea;
```

- [ ] **Step 7.2: Replace `serializeMove` with the MOVE_CORRESPONDING-aware version**

Replace the entire `serializeMove` static method:

```java
private static JsonObject serializeMove(MoveStatement stmt) {
    if (stmt.getMoveType() == MoveStatement.MoveType.MOVE_CORRESPONDING) {
        JsonObject obj = new JsonObject();
        obj.addProperty("type", "MOVE_CORRESPONDING");
        MoveCorrespondingToStatetement corr = stmt.getMoveCorrespondingToStatement();
        MoveCorrespondingToSendingArea sendingArea = corr.getMoveToCorrespondingSendingArea();
        obj.addProperty("source", extractCallName(sendingArea.getSendingAreaCall()).toUpperCase());
        JsonArray targets = new JsonArray();
        for (Call recv : corr.getReceivingAreaCalls()) {
            targets.add(extractCallName(recv).toUpperCase());
        }
        obj.add("targets", targets);
        return obj;
    }

    JsonObject obj = newStatement("MOVE");
    JsonArray operands = new JsonArray();

    MoveToStatement moveToStmt = stmt.getMoveToStatement();
    if (moveToStmt != null) {
        MoveToSendingArea sendingArea = moveToStmt.getSendingArea();
        if (sendingArea != null) {
            ValueStmt vs = sendingArea.getSendingAreaValueStmt();
            operands.add(extractValueStmtText(vs));
        }

        for (Call receivingCall : moveToStmt.getReceivingAreaCalls()) {
            operands.add(extractCallName(receivingCall));
        }
    }

    obj.add("operands", operands);
    return obj;
}
```

- [ ] **Step 7.3: Build the Java bridge**

```bash
cd /Users/asgupta/code/red-dragon/proleap-bridge
mvn package -q 2>&1 | tail -10
```

Expected: `BUILD SUCCESS`

- [ ] **Step 7.4: Run existing COBOL tests to confirm nothing broke**

```bash
cd /Users/asgupta/code/red-dragon
poetry run python -m pytest tests/ -k "cobol" -q --tb=short 2>&1 | tail -15
```

Expected: All pass.

- [ ] **Step 7.5: Update talismanrc for the changed Java file**

The bridge file is already in `.talismanrc`. Run talisman to get the new checksum:

```bash
cd /Users/asgupta/code/red-dragon
talisman --scan 2>&1 | grep StatementSerializer | head -5
```

If talisman flags the file, append a new entry to `.talismanrc` (never modify existing entries — MEMORY policy):

```yaml
- filename: proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java
  checksum: <new-checksum-from-talisman-output>
```

- [ ] **Step 7.6: Commit**

```bash
git add proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java .talismanrc
git commit -m "feat(bridge): serialize MOVE CORRESPONDING to JSON"
```

---

## Task 8: Integration tests for MOVE CORRESPONDING

**Files:**
- Create: `tests/integration/test_cobol_move_corresponding.py`

- [ ] **Step 8.1: Write failing integration tests**

Create `tests/integration/test_cobol_move_corresponding.py`:

```python
"""Integration tests for MOVE CORRESPONDING — full VM execution."""

from __future__ import annotations

import pytest

from interpreter.run import run

# Helper: build minimal COBOL program and run it, returning the result dict
def _run(source: str) -> dict:
    result = run(source.encode(), language="cobol")
    assert result is not None
    return result


class TestMoveCorrespondingBasic:
    def test_matched_fields_are_copied(self):
        """WS-A in both groups — MOVE CORRESPONDING copies it; WS-B and WS-C untouched."""
        source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SRC.
          05 WS-A PIC X(5) VALUE 'HELLO'.
          05 WS-B PIC X(5) VALUE 'WORLD'.
       01 WS-DST.
          05 WS-A PIC X(5) VALUE SPACES.
          05 WS-C PIC X(5) VALUE SPACES.
       PROCEDURE DIVISION.
           MOVE CORRESPONDING WS-SRC TO WS-DST.
           STOP RUN.
"""
        result = _run(source)
        assert result["WS-SRC"]["WS-A"] == "HELLO"
        assert result["WS-DST"]["WS-A"] == "HELLO"
        # WS-B not in DST, WS-C not in SRC — no copy
        assert result["WS-DST"]["WS-C"] == "     "

    def test_unmatched_fields_unchanged(self):
        """WS-B (only in SRC) and WS-C (only in DST) keep their initial values."""
        source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SRC.
          05 WS-A PIC 9(3) VALUE 42.
          05 WS-B PIC 9(3) VALUE 7.
       01 WS-DST.
          05 WS-A PIC 9(3) VALUE ZEROS.
          05 WS-C PIC 9(3) VALUE 99.
       PROCEDURE DIVISION.
           MOVE CORRESPONDING WS-SRC TO WS-DST.
           STOP RUN.
"""
        result = _run(source)
        assert int(result["WS-DST"]["WS-A"]) == 42
        assert int(result["WS-DST"]["WS-C"]) == 99

    def test_no_common_names_is_noop(self):
        """Groups with zero field name overlap — all fields unchanged."""
        source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SRC.
          05 WS-P PIC X(3) VALUE 'ABC'.
       01 WS-DST.
          05 WS-Q PIC X(3) VALUE 'XYZ'.
       PROCEDURE DIVISION.
           MOVE CORRESPONDING WS-SRC TO WS-DST.
           STOP RUN.
"""
        result = _run(source)
        assert result["WS-DST"]["WS-Q"] == "XYZ"

    def test_multiple_targets(self):
        """MOVE CORRESPONDING src TO dst1 dst2 — both targets receive the copy."""
        source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SRC.
          05 WS-X PIC 9(4) VALUE 1234.
       01 WS-DST1.
          05 WS-X PIC 9(4) VALUE ZEROS.
       01 WS-DST2.
          05 WS-X PIC 9(4) VALUE ZEROS.
       PROCEDURE DIVISION.
           MOVE CORRESPONDING WS-SRC TO WS-DST1 WS-DST2.
           STOP RUN.
"""
        result = _run(source)
        assert int(result["WS-DST1"]["WS-X"]) == 1234
        assert int(result["WS-DST2"]["WS-X"]) == 1234

    def test_partial_overlap(self):
        """SRC has WS-A and WS-B; DST has WS-A and WS-C — only WS-A copied."""
        source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-SRC.
          05 WS-A PIC X(4) VALUE 'TEST'.
          05 WS-B PIC X(4) VALUE 'ONLY'.
       01 WS-DST.
          05 WS-A PIC X(4) VALUE '    '.
          05 WS-C PIC X(4) VALUE 'KEEP'.
       PROCEDURE DIVISION.
           MOVE CORRESPONDING WS-SRC TO WS-DST.
           STOP RUN.
"""
        result = _run(source)
        assert result["WS-DST"]["WS-A"] == "TEST"
        assert result["WS-DST"]["WS-C"] == "KEEP"
```

- [ ] **Step 8.2: Run to confirm tests fail**

```bash
poetry run python -m pytest tests/integration/test_cobol_move_corresponding.py -v 2>&1 | tail -20
```

Expected: FAIL — either the Java bridge hasn't been built yet with the MOVE_CORRESPONDING support (Task 7 must be done first), or the Python side hasn't wired everything up. After Task 7 is complete these should pass.

- [ ] **Step 8.3: Run tests after Java bridge is built (should pass)**

```bash
poetry run python -m pytest tests/integration/test_cobol_move_corresponding.py -v 2>&1 | tail -20
```

Expected: All PASS.

- [ ] **Step 8.4: Commit**

```bash
git add tests/integration/test_cobol_move_corresponding.py
git commit -m "test(cobol): add integration tests for MOVE CORRESPONDING"
```

---

## Task 9: Integration tests for complex REDEFINES

**Files:**
- Create: `tests/integration/test_cobol_redefines_complex.py`

- [ ] **Step 9.1: Write the integration tests**

Create `tests/integration/test_cobol_redefines_complex.py`:

```python
"""Integration tests for complex REDEFINES scenarios — full VM execution."""

from __future__ import annotations

import pytest

from interpreter.run import run


def _run(source: str) -> dict:
    result = run(source.encode(), language="cobol")
    assert result is not None
    return result


class TestRedefinesBasicAlias:
    def test_write_original_read_via_alias(self):
        """Write via WS-DATE-NUM; read via WS-DATE children sees same bytes."""
        source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-DATE.
          05 WS-YEAR  PIC 9(4).
          05 WS-MONTH PIC 99.
          05 WS-DAY   PIC 99.
       01 WS-DATE-NUM PIC 9(8) REDEFINES WS-DATE.
       PROCEDURE DIVISION.
           MOVE 20260418 TO WS-DATE-NUM.
           STOP RUN.
"""
        result = _run(source)
        assert result["WS-DATE-NUM"] == "20260418"
        assert result["WS-YEAR"] == "2026"
        assert result["WS-MONTH"] == "04"
        assert result["WS-DAY"] == "18"

    def test_write_via_alias_read_original(self):
        """Write via group WS-DATE children; read via numeric alias reflects bytes."""
        source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-DATE.
          05 WS-YEAR  PIC 9(4) VALUE 2026.
          05 WS-MONTH PIC 99   VALUE 04.
          05 WS-DAY   PIC 99   VALUE 18.
       01 WS-DATE-NUM PIC 9(8) REDEFINES WS-DATE.
       PROCEDURE DIVISION.
           STOP RUN.
"""
        result = _run(source)
        assert result["WS-DATE-NUM"] == "20260418"


class TestMultipleRedefines:
    def test_two_aliases_same_offset(self):
        """B REDEFINES A and C REDEFINES A — write to A, both aliases reflect it."""
        source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC X(4) VALUE 'ABCD'.
       01 WS-B PIC 9(4) REDEFINES WS-A.
       01 WS-C PIC X(4) REDEFINES WS-A.
       PROCEDURE DIVISION.
           STOP RUN.
"""
        result = _run(source)
        assert result["WS-A"] == "ABCD"
        assert result["WS-C"] == "ABCD"

    def test_chained_redefines(self):
        """A, B REDEFINES A, C REDEFINES B — write to A, C reflects same bytes."""
        source = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TEST.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC X(4) VALUE 'ZYXW'.
       01 WS-B PIC X(4) REDEFINES WS-A.
       01 WS-C PIC X(4) REDEFINES WS-B.
       PROCEDURE DIVISION.
           STOP RUN.
"""
        result = _run(source)
        assert result["WS-A"] == "ZYXW"
        assert result["WS-B"] == "ZYXW"
        assert result["WS-C"] == "ZYXW"
```

- [ ] **Step 9.2: Run the tests**

```bash
poetry run python -m pytest tests/integration/test_cobol_redefines_complex.py -v 2>&1 | tail -20
```

Expected: All PASS (REDEFINES was already working; these tests confirm correctness after the DataLayout refactor).

- [ ] **Step 9.3: Run full test suite**

```bash
poetry run python -m pytest tests/ -q --tb=short 2>&1 | tail -10
```

Expected: All tests pass, count ≥ 13267 + new tests.

- [ ] **Step 9.4: Black formatting pass**

```bash
poetry run python -m black .
```

- [ ] **Step 9.5: Commit**

```bash
git add tests/integration/test_cobol_redefines_complex.py
git commit -m "test(cobol): add integration tests for complex REDEFINES scenarios"
```

---

## Self-Review Against Spec

**Section 1 (Data Model):** Covered in Tasks 1–3. `DataLayout` now has `fields`/`groups`/`offset`/`total_bytes` + the four methods. `occurs_count` and `element_size` added (spec gap fix). ✓

**Section 2 (`_flatten_field` refactor):** Implemented in Task 2. New signature `(cobol_field, base_offset, sibling_fields, sibling_groups) -> tuple[str, FieldLayout | DataLayout]`. Inline REDEFINES resolution. `_fix_redefines_offsets` and `_with_offset` deleted. ✓

**Section 3 (MOVE CORRESPONDING lowering):** `MoveCorrespondingStatement` in Task 5. `lower_move_corresponding` + `resolve_field_ref_from` in Task 6. `dispatch_statement` branch in Task 6. ✓

**Section 4 (Java bridge):** `serializeMove` branch in Task 7. Uses real ProLeap API: `getMoveCorrespondingToStatement()`, `getMoveToCorrespondingSendingArea().getSendingAreaCall()`, `getReceivingAreaCalls()`. ✓

**Section 5 (Migration):** All 5 caller files migrated in Task 4. `_leaf_fields_of` deleted, `lower_initialize` rewritten in Task 6. ✓

**Section 6 (Testing):** Unit tests for `DataLayout` (Tasks 1, 3), unit tests for `lower_move_corresponding` (Task 6), integration tests for MOVE CORRESPONDING (Task 8), integration tests for complex REDEFINES (Task 9). ✓

**Spec discrepancy fixed in plan:** Spec used `getMoveCorrespondingFromSendingArea()` — actual ProLeap API is `getMoveToCorrespondingSendingArea().getSendingAreaCall()`. Plan uses the real API. ✓

**Design gap resolved in plan:** `DataLayout` gains `occurs_count` and `element_size` fields (not in original spec) to support `lookup_as_storage()` synthesizing OCCURS group FieldLayouts. ✓
