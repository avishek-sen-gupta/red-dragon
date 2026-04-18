# Design: Recursive DataLayout + MOVE CORRESPONDING

**Date:** 2026-04-18  
**Scope:** `interpreter/cobol/data_layout.py` and COBOL MOVE CORRESPONDING support  
**Fixes:** Bug 4q25.6 (MOVE CORRESPONDING not implemented), flat-dict collision bug

---

## Problem

`DataLayout.fields: dict[str, FieldLayout]` uses bare field names as keys. When two groups share a child name (e.g. `WS-SRC.WS-A` and `WS-DST.WS-A`), the second entry silently overwrites the first. This makes MOVE CORRESPONDING impossible to implement correctly, and is a latent correctness bug for programs with identically-named fields in different groups.

Additionally, the ProLeap bridge's `StatementSerializer.serializeMove()` silently emits empty operands when it encounters a `MOVE CORRESPONDING` statement (because `getMoveToStatement()` returns null for that variant).

---

## Section 1: Data Model

`DataLayout` becomes recursive. The flat `fields: dict[str, FieldLayout]` (all descendants) is replaced:

```python
@dataclass(frozen=True)
class DataLayout:
    fields: dict[str, FieldLayout]    # direct elementary (leaf) children only
    groups: dict[str, "DataLayout"]   # direct group children, keyed by group name
    offset: int = 0                   # absolute byte offset of this group's start
    total_bytes: int = 0              # only meaningful at root level

    def lookup(self, name: str) -> FieldLayout | None:
        """Recursive search for a leaf field by bare name."""
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
        """Return a nested DataLayout by group name; raises if not found or is a leaf."""
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
```

The old flat `fields: dict[str, FieldLayout]` (all descendants) is removed entirely. All callers migrate to `lookup()` / `all_leaves()`.

**Collision-free:** `WS-SRC.WS-A` and `WS-DST.WS-A` live in separate `DataLayout.fields` dicts — no overwrite.

---

## Section 2: `_flatten_field` Refactor

`_flatten_field` is rewritten to return `(name, FieldLayout | DataLayout)` and build the recursive structure directly, rather than dumping into a flat accumulator.

```python
def _flatten_field(
    cobol_field: CobolField,
    base_offset: int,
    sibling_fields: dict[str, FieldLayout],
    sibling_groups: dict[str, DataLayout],
) -> tuple[str, FieldLayout | DataLayout]:
    """Return (name, leaf) for elementary fields, (name, DataLayout) for groups."""
    # Offset resolution — REDEFINES gets offset of the field it redefines
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
        group_layout = DataLayout(
            fields=sub_fields,
            groups=sub_groups,
            offset=absolute_offset,
            total_bytes=group_length,
        )
        return cobol_field.name, group_layout

    # Elementary leaf
    type_desc = parse_pic(
        cobol_field.pic, cobol_field.usage,
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
    return cobol_field.name, fl
```

`build_data_layout` assembles the root:

```python
def build_data_layout(fields: list[CobolField]) -> DataLayout:
    non_renames_fields = [f for f in fields if not f.renames_from]
    top_fields: dict[str, FieldLayout] = {}
    top_groups: dict[str, DataLayout] = {}
    for f in non_renames_fields:
        name, result = _flatten_field(f, 0, top_fields, top_groups)
        if isinstance(result, DataLayout):
            top_groups[name] = result
        else:
            top_fields[name] = result

    # RENAMES fields (level 66) — resolved against top_fields/top_groups
    renames_fields = [f for f in fields if f.renames_from]
    for rf in renames_fields:
        top_fields[rf.name] = _resolve_renames(rf, top_fields, top_groups)

    non_redefines_top = [f for f in non_renames_fields if not f.redefines]
    total = sum(_compute_group_length(f) for f in non_redefines_top)

    return DataLayout(fields=top_fields, groups=top_groups, total_bytes=total)
```

**`_fix_redefines_offsets` is removed** — offset resolution now happens inline during the forward build pass, since COBOL requires the redefined field to precede the REDEFINES field at each level.

### REDEFINES correctness

**Multiple REDEFINES of same field (A, B REDEFINES A, C REDEFINES A):** Both B and C look up A in the local sibling dict → both get A's offset. Correct.

**Chained REDEFINES (A, B REDEFINES A, C REDEFINES B):** B looks up A → gets offset 0. C looks up B → B already has offset 0 → C gets offset 0. One-hop lookup is sufficient because each link in the chain already has the correct offset.

**REDEFINES inside a REDEFINES block:** When building the children of a REDEFINES group, the local `sub_fields`/`sub_groups` accumulate in source order. A nested REDEFINES resolves against its local siblings — the fact that its parent is itself a REDEFINES is irrelevant.

**REDEFINES combined with OCCURS:** OCCURS fields are elementary or group items — REDEFINES of an OCCURS field follows the same offset-from-sibling-dict logic. No special case.

---

## Section 3: MOVE CORRESPONDING Lowering

New statement type in `cobol_statements.py`:

```python
@dataclass(frozen=True)
class MoveCorrespondingStatement:
    source: str          # source group name
    targets: list[str]   # one or more destination group names
```

Lowering in `lower_arithmetic.py`:

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

Matching is one level deep (direct elementary children only). Nested sub-group matching is not part of this design.

`EmitContext` gains `resolve_field_ref_from(fl: FieldLayout, region_reg: str)` — takes a `FieldLayout` directly (offset already known) rather than looking up by name.

Dispatch in `statement_dispatch.py`:

```python
elif isinstance(stmt, MoveCorrespondingStatement):
    lower_move_corresponding(ctx, stmt, layout, region_reg)
```

---

## Section 4: Java Bridge Changes

`StatementSerializer.serializeMove()` in `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java`:

```java
private void serializeMove(MoveStatement stmt, JsonObject obj) {
    if (stmt.getMoveType() == MoveType.MOVE_CORRESPONDING) {
        MoveCorrespondingToStatement corr = stmt.getMoveCorrespondingToStatement();
        obj.addProperty("type", "MOVE_CORRESPONDING");
        obj.addProperty("source",
            corr.getMoveCorrespondingFromSendingArea().getName().toUpperCase());
        JsonArray targets = new JsonArray();
        for (var recv : corr.getMoveCorrespondingToReceivingAreas()) {
            targets.add(recv.getName().toUpperCase());
        }
        obj.add("targets", targets);
    } else {
        // existing MOVE TO logic — unchanged
        MoveToStatement moveTo = stmt.getMoveToStatement();
        // ...
    }
}
```

Python deserializer (in `cobol_frontend.py` statement parsing branch):

```python
if stmt_type == "MOVE_CORRESPONDING":
    yield MoveCorrespondingStatement(
        source=data["source"],
        targets=data["targets"],   # always a list
    )
```

---

## Section 5: Migration Strategy

### Production callers

All `layout.fields[name]` / `name in layout.fields` accesses migrate:

| File | Change |
|---|---|
| `emit_context.py` | `has_field` → `layout.lookup(name) is not None`; `resolve_field_ref` → `layout.lookup_or_raise(name)` (4 sites) |
| `cobol_frontend.py` | field iteration loop → `layout.all_leaves()`; `build_condition_index` call |
| `condition_name_index.py` | `build_condition_index` takes `DataLayout`, iterates `layout.all_leaves()` |
| `symbol_table.py` | field iteration loop → `layout.all_leaves()` |
| `lower_data_division.py` | already uses `.values()` filter — migrates to `layout.all_leaves()` with same filter |

### Tests

All `layout.fields["X"]` accesses in test files migrate to `layout.lookup("X")`. Approximately 86 sites across `test_data_layout.py` and `test_occurs_layout.py`. Mechanical substitution only.

---

## Section 6: Testing

### Unit tests — `test_data_layout.py` (migrated + extended)

Existing tests: `layout.fields["X"]` → `layout.lookup("X")`. All assertions unchanged.

New test class `TestBuildDataLayoutRedefinesComplex`:
- Multiple REDEFINES of same field — all at same offset, `total_bytes` unchanged
- Chained REDEFINES (A → B REDEFINES A → C REDEFINES B) — C at same offset as A
- Elementary REDEFINES a group — leaf at same offset as group
- Group REDEFINES an elementary — sub-group at same offset as leaf
- REDEFINES nested inside a REDEFINES block — inner sibling resolved at local level
- REDEFINES combined with OCCURS

New test class `TestBuildDataLayoutMoveCorresponding`:
- `lookup_group` returns the correct `DataLayout` for a named group
- `fields.keys()` intersection produces the expected matching leaf names
- Non-matching fields absent from intersection

### Unit tests — `test_lower_move_corresponding.py` (new)

IR-level tests with mock `EmitContext`:
- Matched fields: one decode/encode pair emitted per matched name
- Unmatched fields: no instructions emitted
- Multiple targets: each target group receives the copied values

### Integration tests — `test_cobol_move_corresponding.py` (new)

Full VM execution via `run()`:
- Basic MOVE CORRESPONDING — matched fields copied, unmatched left unchanged
- MOVE CORRESPONDING with multiple targets
- Groups with no matching names — no-op, all fields unchanged
- Partial overlap — only overlapping names copied

### Integration tests — `test_cobol_redefines_complex.py` (new)

Full VM execution:
- Write via original field, read via REDEFINES alias — same bytes
- Write via REDEFINES, read via original — same bytes
- Chained REDEFINES — write via root, verify via each link in chain
- Multiple REDEFINES of same field — each alias reflects the write
- REDEFINES combined with OCCURS table access
