# Cross-Class Field Resolution — Design Spec

**Date:** 2026-03-21
**Status:** Approved
**Scope:** Subclass constructors assigning parent class fields via implicit this
**Issue:** red-dragon-nzlv

## Problem

`class Dog extends Animal { Dog(String n) { name = n; } }` — `name` is a field of `Animal`, not `Dog`. The store target checks `ctx.symbol_table.classes.get("Dog").fields` which doesn't include `name`, so it emits `STORE_VAR` instead of `STORE_FIELD this, name`.

## Design

Add `resolve_field(class_name, field_name)` to `SymbolTable` that walks the class hierarchy via `ClassInfo.parents`. Update the 3 store targets to use it instead of direct `.fields` lookup.

```python
def resolve_field(self, class_name: str, field_name: str) -> FieldInfo | None:
    class_info = self.classes.get(class_name)
    if class_info is None:
        return None
    if field_name in class_info.fields:
        return class_info.fields[field_name]
    for parent in class_info.parents:
        result = self.resolve_field(parent, field_name)
        if result is not None:
            return result
    return None
```

### Files Changed

- `interpreter/frontends/symbol_table.py` — add `resolve_field`
- `interpreter/frontends/csharp/expressions.py` — use `resolve_field`
- `interpreter/frontends/java/expressions.py` — use `resolve_field`
- `interpreter/frontends/c/expressions.py` — use `resolve_field`

## Testing

- `test_subclass_constructor_assigns_parent_field` — Java: Dog extends Animal, name assigned in Dog constructor
- `test_multi_level_inheritance` — Java: C extends B extends A, field from A assigned in C
