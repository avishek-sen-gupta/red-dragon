# Star Patterns in Sequence Matching — Design Spec

**Date:** 2026-03-20
**Status:** Approved
**Scope:** `case [first, *rest]:` star/splat patterns in Python list and tuple patterns
**Issue:** red-dragon-2uke

## Problem

Python's structural pattern matching supports star patterns (`*rest`) inside list and tuple patterns to capture remaining elements. The current Pattern ADT has no way to represent this — `SequencePattern` only does exact-length matching.

## Approach

Add a `StarPattern(name)` frozen dataclass to the Pattern ADT. A `StarPattern` appears as one of the elements in `SequencePattern.elements`. The pattern compiler detects it and switches from exact-length (`==`) to minimum-length (`>=`) matching, using the existing `slice` builtin to extract the captured rest.

## Design

### 1. New ADT Variant

```python
@dataclass(frozen=True)
class StarPattern(Pattern):
    """Captures remaining elements in a sequence pattern. Python's ``*rest``."""
    name: str
```

`SequencePattern.elements` stays `tuple[Pattern, ...]`. At most one `StarPattern` per `SequencePattern` (Python grammar enforces this).

### 2. Pattern Compiler Changes

**`compile_pattern_test` standalone for `StarPattern`:** Add `case StarPattern(): return _const_true(ctx)` — a star always matches, no test needed.

**Test IR** — `compile_pattern_test` for `SequencePattern` with a `StarPattern`:

1. Find star index: `star_idx = next(i for i, e in enumerate(elems) if isinstance(e, StarPattern))`
2. Fixed count: `fixed_count = len(elems) - 1`
3. Emit `CALL_FUNCTION len(subject)` → `BINOP >= len_reg, fixed_count` (minimum length)
4. Fixed elements before star (indices `0..star_idx-1`): `LOAD_INDEX subject, i` → recurse
5. Fixed elements after star: compute actual index via `BINOP - len_reg, offset` → `LOAD_INDEX subject, computed_idx` → recurse. Note: `LOAD_INDEX` resolves its second operand via `_resolve_reg`, so register-based indices work.
6. StarPattern is skipped in the test loop (already covered by the `>=` length check)
7. AND all sub-results

**Bind IR** — `compile_pattern_bindings` for `SequencePattern` with `StarPattern`:

1. Emit `CALL_FUNCTION len(subject)` to get length register (needed for after-star index computation)
2. Bind fixed elements before star (literal indices)
3. Bind fixed elements after star (computed indices via `BINOP - len_reg, offset`)
4. StarPattern binding: if `name != "_"`, emit `CALL_FUNCTION slice(subject, star_idx, len - after_count)` → `STORE_VAR name`. If `name == "_"`, skip the slice entirely (wildcard star captures nothing).

**No star** — existing exact-length path unchanged.

### 3. Python Frontend Parser

Add to `parse_pattern` in `interpreter/frontends/python/patterns.py`:

```python
if node_type == PythonNodeType.SPLAT_PATTERN:
    named = [c for c in node.children if c.is_named]
    name = ctx.node_text(named[0]) if named else "_"
    return StarPattern(name=name)
```

Tree-sitter produces `splat_pattern` inside `list_pattern`/`tuple_pattern` case_pattern children. `PythonNodeType.SPLAT_PATTERN` already exists.

### 4. Files Changed

**Modified:**
- `interpreter/frontends/common/patterns.py` — add `StarPattern`, update `compile_pattern_test` and `compile_pattern_bindings` for star-in-sequence
- `interpreter/frontends/python/patterns.py` — handle `splat_pattern` in `parse_pattern`

**No new files.** No changes to `ir.py`, `executor.py`, `vm.py`, `builtins.py`.

## Testing

**Unit tests** (add to `tests/unit/test_pattern_compiler.py`):

- `test_star_pattern_emits_gte_length_check` — `>=` instead of `==`
- `test_star_pattern_no_test_for_star_element` — star emits no test IR
- `test_star_pattern_binds_via_slice` — emits `CALL_FUNCTION slice` + `STORE_VAR`
- `test_star_at_beginning_computes_tail_indices` — `[*head, last]` index computation
- `test_star_in_middle` — `[a, *mid, z]` before + after + slice
- `test_wildcard_star_skips_slice` — `StarPattern(name="_")` emits no `CALL_FUNCTION slice` or `STORE_VAR`

**Integration tests** (add to `tests/integration/test_python_pattern_matching.py`):

- `test_star_at_end` — `[first, *rest]` with `[1,2,3,4]` → `first==1`, rest has 3 elements
- `test_star_at_beginning` — `[*head, last]` with `[1,2,3]` → `last==3`, head has 2 elements
- `test_star_in_middle` — `[a, *mid, z]` with `[1,2,3,4,5]` → `a==1`, `z==5`, mid has 3 elements
- `test_star_empty_rest` — `[a, b, *rest]` with `[1,2]` → `rest` is empty
- `test_star_in_tuple` — `(first, *rest)` with `(10, 20, 30)` → `first==10`
- `test_star_minimum_length_rejects` — `[a, b, *rest]` with `[1]` → falls to default
- `test_wildcard_star_no_binding` — `[first, *_]` with `[1, 2, 3]` → `first==1`, no `_` variable created
- `test_nested_star_pattern` — `[a, [b, *inner], c]` with `[1, [2, 3, 4], 5]` → `a==1`, `c==5`, `inner` has 2 elements

Existing xfail `test_star_pattern_in_list` gets xfail removed.
