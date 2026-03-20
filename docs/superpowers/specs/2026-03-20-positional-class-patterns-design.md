# Positional Class Patterns via `__match_args__` — Design Spec

**Date:** 2026-03-20
**Status:** Approved
**Scope:** `case Point(a, b):` positional class patterns resolved via `__match_args__`
**Issue:** red-dragon-jkw2

## Problem

Positional class patterns like `case Point(a, b):` don't work. The compiler emits `LOAD_INDEX subject, 0` for positional args, but user-defined classes store fields by name (`self.x`, `self.y`), not by numeric index. Python requires `__match_args__` to map positions to field names.

## Approach

Frontend-level resolution. When `parse_pattern` encounters a `class_pattern` with positional args, it walks the tree-sitter AST (via `.parent` up to the module root) to find the class definition, extracts `__match_args__`, and converts positional args to keyword args. The `ClassPattern` that reaches the compiler has `keyword` fields, not `positional`. No VM or compiler changes needed.

## Design

**Add helper `_resolve_match_args(node, class_name)`** in `interpreter/frontends/python/patterns.py`:

1. Walk up from `node` via `.parent` to reach the module root
2. Search module children for `class_definition` where `name` field == `class_name`
3. In the class body (`block`), find an `assignment` where left child is `identifier("__match_args__")`
4. The right child is a `tuple` containing `string` nodes. Extract `string_content` text from each → return as `list[str]`
5. If not found, return empty list

**Tree-sitter AST structure** (verified):
```
class_definition
  body: block
    assignment
      identifier: __match_args__
      tuple
        string → string_content: "x"
        string → string_content: "y"
```

**Modify `class_pattern` handling in `parse_pattern`**: Currently separates children into `positional` and `keyword` lists. When positional patterns exist, call `_resolve_match_args(node, class_name)`. If field names are returned, zip them with positional patterns → append to `keyword` list instead. Clear `positional`.

### Files Changed

**Modified:**
- `interpreter/frontends/python/patterns.py` — add `_resolve_match_args`, modify `class_pattern` handling

**No changes to:** Pattern ADT, compiler (`common/patterns.py`), VM, builtins

## Testing

**Integration tests** (add to `tests/integration/test_python_pattern_matching.py`):

- `test_class_positional_with_match_args` — `Point(3, b)` with `__match_args__` → `b == 4`
- `test_class_positional_two_captures` — `Point(a, b)` captures both → `a == 3, b == 4`
- `test_class_positional_literal_rejects` — `Point(99, b)` with non-matching value → falls to default
- Update existing xfail `test_class_positional` to include `__match_args__` and remove xfail
