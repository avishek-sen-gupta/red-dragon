# Implicit `this` Field Store in Constructors — Design Spec

**Date:** 2026-03-21
**Status:** Approved
**Scope:** Fix bare field assignments in constructors (Java, C#, C++) to emit `STORE_FIELD this` instead of `STORE_VAR`
**Issue:** red-dragon-yn17

## Problem

In Java, C#, and C++ constructors, `x = v` means `this.x = v`. But tree-sitter parses the left side as a bare `identifier`, so the frontend emits `STORE_VAR x` (local variable) instead of `STORE_FIELD this, x` (object field). This makes constructor-assigned fields return symbolic when accessed later.

Languages with explicit self syntax (Python `self.x`, Ruby `@x`, PHP `$this->x`) are unaffected.

## Approach

Track declared field names on `ctx._class_field_names`. During class lowering, populate the set. In each language's store target function, when the target is a bare identifier in `_class_field_names`, emit `LOAD_VAR this` + `STORE_FIELD` instead of `STORE_VAR`.

## Design

### 1. Context Field

Add to `TreeSitterEmitContext` in `interpreter/frontends/context.py`:

```python
_class_field_names: set[str] = field(default_factory=set)
```

### 2. Populate During Class Lowering

Each language's class declaration function already collects field info. Add `ctx._class_field_names = {field names}` before lowering the class body, clear after.

- **C#:** `_collect_csharp_field_inits` already extracts field names — save to `ctx._class_field_names`
- **Java:** same pattern with `_collect_java_field_inits`
- **C++:** extract from `field_declaration` nodes in class body

### 3. Check in Store Target

In each language's store target function, the bare `identifier` branch currently does `STORE_VAR name`. Change to:

```python
if name in ctx._class_field_names:
    this_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=this_reg, operands=["this"])
    ctx.emit(Opcode.STORE_FIELD, operands=[this_reg, name, val_reg], node=parent_node)
else:
    emit_store(ctx, name, val_reg, node=parent_node)
```

### 4. Files Changed

**Modified:**
- `interpreter/frontends/context.py` — add `_class_field_names` field
- `interpreter/frontends/csharp/declarations.py` — populate field names
- `interpreter/frontends/csharp/expressions.py` — check in `lower_csharp_store_target`
- `interpreter/frontends/java/declarations.py` — populate field names
- `interpreter/frontends/java/expressions.py` — check in store target
- `interpreter/frontends/cpp/declarations.py` — populate field names
- `interpreter/frontends/cpp/expressions.py` — check in store target

## Testing

**Integration tests:**
- C#: `new Circle(5).Radius` → `5`
- Java: `new Circle(5).radius` → `5`
- C++: `Circle c(5); c.radius` → `5`
- Remove xfail from C# `test_switch_expr_recursive_with_capture`
