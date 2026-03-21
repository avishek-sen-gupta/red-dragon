# Implicit `this` for Field Reads — Design Spec

**Date:** 2026-03-21
**Status:** Approved
**Scope:** Bare field reads in Java/C#/C++ methods emit `LOAD_FIELD this` instead of `LOAD_VAR`
**Issue:** red-dragon-5jdr

## Problem

In Java/C#/C++ methods, `return radius;` where `radius` is a class field emits `LOAD_VAR radius` which returns symbolic. It should emit `LOAD_VAR this` + `LOAD_FIELD this_reg, radius`.

Parameters and local variables that shadow field names must take precedence.

## Design

### 1. NULL_FIELD sentinel

Add to `interpreter/frontends/symbol_table.py`:

```python
NULL_FIELD = FieldInfo(name="", type_hint="", has_initializer=False)
```

Change `resolve_field` to return `FieldInfo` (never None):
- Returns the found `FieldInfo` if field exists in class or ancestor
- Returns `NULL_FIELD` if not found

Callers check `field.name` for truthiness.

### 2. Track declared names in current method

Add `_method_declared_names: set[str]` to `TreeSitterEmitContext`. In `emit()`, when `opcode == DECL_VAR`, add `operands[0]` to the set.

Add `reset_method_scope()` that clears the set. Call it at function/method entry in Java, C#, C++ declarations.

### 3. Check in `lower_identifier`

In `common/expressions.py`, modify `lower_identifier` — before emitting `LOAD_VAR`, check:
- Is `name` NOT in `ctx._method_declared_names`?
- Is `ctx._current_class_name` set?
- Does `ctx.symbol_table.resolve_field(ctx._current_class_name, name).name` return truthy?

If all yes → emit `LOAD_VAR this` + `LOAD_FIELD`.

### 4. Update existing store target callers

The 3 store targets currently use `resolve_field` with `is not None` check. Update to check `.name` instead.

### Files Changed

- `interpreter/frontends/symbol_table.py` — `NULL_FIELD`, change `resolve_field` return type
- `interpreter/frontends/context.py` — `_method_declared_names`, track in `emit()`, `reset_method_scope()`
- `interpreter/frontends/common/expressions.py` — field check in `lower_identifier`
- `interpreter/frontends/java/declarations.py` — call `reset_method_scope()` at method entry
- `interpreter/frontends/csharp/declarations.py` — same
- `interpreter/frontends/cpp/declarations.py` — same
- `interpreter/frontends/csharp/expressions.py` — update store target caller
- `interpreter/frontends/java/expressions.py` — same
- `interpreter/frontends/c/expressions.py` — same

## Testing

- `test_method_reads_field` — `getRadius()` returns field value concretely
- `test_param_shadows_field` — `bar(int radius)` returns parameter, not field
- `test_local_shadows_field` — `int radius = 99; return radius;` returns 99
- `test_cross_class_field_read` — method in subclass reads parent field
