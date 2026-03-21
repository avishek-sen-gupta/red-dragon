# Scala 3 Enum Definitions — Design Spec

**Date:** 2026-03-22
**Issue:** red-dragon-416 (P1)

## Summary

Add support for Scala 3 simple enum definitions (`enum Color { case Red, Green, Blue }`). Follow the Rust pattern: single container object with `STORE_FIELD` per variant.

## Scope

**In scope:** Simple enums — `enum Color { case Red, Green, Blue }`. Access via `Color.Red` (field expression).

**Out of scope:** Parameterized variants (`case Circle(radius: Double)`) — filed as `red-dragon-y9s4`.

## Architecture

### IR Emission

Follow Rust's `lower_enum_item` pattern:

```
NEW_OBJECT "enum:Color"
CONST "Red"
STORE_FIELD obj, "Red", "Red"
CONST "Green"
STORE_FIELD obj, "Green", "Green"
CONST "Blue"
STORE_FIELD obj, "Blue", "Blue"
DECL_VAR Color, obj
```

Each variant stores its name as a string value. `Color.Red` resolves via the existing `LOAD_FIELD` on field_expression.

### Implementation

1. Add `ENUM_DEFINITION = "enum_definition"` (or whatever tree-sitter uses) to `ScalaNodeType`
2. Add `lower_enum_def(ctx, node)` to `interpreter/frontends/scala/declarations.py`
3. Add dispatch entry to `frontend.py` stmt_dispatch
4. Tree-sitter structure needs diagnostic verification — `enum Color { case Red, Green, Blue }` may parse as `enum_definition` with `enum_case` or `simple_enum_case` children

### Testing

Unit test: verify IR output (NEW_OBJECT, STORE_FIELD per variant, DECL_VAR)
Integration test: `enum Color { case Red, Green, Blue }; val c = Color.Red` — verify c resolves to "Red"
