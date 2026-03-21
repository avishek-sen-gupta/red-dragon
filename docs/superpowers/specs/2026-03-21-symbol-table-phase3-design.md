# Symbol Table Phase 3: Replace Workarounds — Design Spec

**Date:** 2026-03-21
**Status:** Approved
**Scope:** Replace `_class_field_names` and `_resolve_match_args` with `ctx.symbol_table` lookups. Delete the ad-hoc code.
**Issue:** red-dragon-j87f

## Problem

Two ad-hoc workarounds exist that duplicate information now available in `ctx.symbol_table`:
1. `ctx._class_field_names` — manually collected during class lowering for implicit-this detection
2. `_resolve_match_args` — walks the AST at pattern-parse time to find `__match_args__`

Both can be replaced with `ctx.symbol_table` lookups since Phase 2 extractors now populate the table before lowering begins.

## Design

### Replace #1: `_class_field_names` → `ctx.symbol_table`

**In store targets** (C#, Java, C/C++), replace:
```python
if name in ctx._class_field_names:
```
with:
```python
class_info = ctx.symbol_table.classes.get(ctx._current_class_name)
if class_info and name in class_info.fields:
```

**Delete:**
- `_class_field_names` field from `TreeSitterEmitContext`
- `_collect_csharp_all_field_names` from `csharp/declarations.py`
- `_collect_java_all_field_names` from `java/declarations.py`
- `_collect_cpp_all_field_names` from `cpp/declarations.py`
- All save/restore of `_class_field_names` in class lowering functions

### Replace #2: `_resolve_match_args` → `ctx.symbol_table`

**In `parse_pattern`** (`python/patterns.py`), replace:
```python
match_args = _resolve_match_args(node, class_name)
```
with:
```python
class_info = ctx.symbol_table.classes.get(class_name)
match_args = list(class_info.match_args) if class_info else []
```

**Delete:**
- `_resolve_match_args`, `_find_module_root`, `_find_class_def`, `_extract_match_args_from_body` from `python/patterns.py`

### Deferred

`_resolve_class_static_field` in `executor.py` stays as-is — threading `symbol_table` to the executor is a separate concern.

### Files Changed

- `interpreter/frontends/context.py` — remove `_class_field_names`
- `interpreter/frontends/csharp/declarations.py` — remove `_collect_csharp_all_field_names`, save/restore
- `interpreter/frontends/csharp/expressions.py` — use `ctx.symbol_table`
- `interpreter/frontends/java/declarations.py` — remove `_collect_java_all_field_names`, save/restore
- `interpreter/frontends/java/expressions.py` — use `ctx.symbol_table`
- `interpreter/frontends/cpp/declarations.py` — remove `_collect_cpp_all_field_names`, save/restore
- `interpreter/frontends/c/expressions.py` — use `ctx.symbol_table`
- `interpreter/frontends/python/patterns.py` — use `ctx.symbol_table`, delete AST walkers

## Testing

All existing tests must pass unchanged — behavior is identical, only the source of truth changes. No new tests needed.
