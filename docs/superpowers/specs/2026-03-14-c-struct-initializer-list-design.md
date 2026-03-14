# C Struct Initializer List Fix

## Problem

`struct Node n = {3, 0}` and `struct Node n = {.value = 3, .next = 0}` both lower
via `lower_initializer_list` as `NEW_ARRAY` + `STORE_INDEX`. Subsequent `n.value`
does `LOAD_FIELD` on an array, which returns SymbolicValue instead of `3`.

## Root Cause

`_lower_init_declarator` has `struct_type` available but blindly calls
`ctx.lower_expr(value_node)`, which dispatches to `lower_initializer_list`.
That function has no struct context and treats all `{...}` as arrays.

## Design

**Approach: Intercept in `_lower_init_declarator` + IR scan for field names.**

When `struct_type` is set and `value_node.type == "initializer_list"`:

1. Emit `CALL_FUNCTION <struct_type>` to create the object (same as uninitialized
   struct var path).
2. Emit `STORE_VAR <var_name> <obj_reg>` so the object is addressable.
3. For each element in the initializer list:
   - **Designated** (`initializer_pair` with `field_designator`): extract field name
     from the designator AST node, lower the value expression, emit `STORE_FIELD`.
   - **Positional**: scan `ctx.instructions` for `STORE_FIELD` instructions in the
     struct's class body to get ordered field names, map element index to field name,
     lower the value expression, emit `STORE_FIELD`.
4. Skip the normal `ctx.lower_expr(value_node)` path.

**IR scan helper** — `_extract_struct_field_names(ctx, struct_name) -> list[str]`:
scans `ctx.instructions` for the class label block matching `struct_name`, collects
`STORE_FIELD` operand field names in order. Returns empty list if not found.

**Files changed:**
- `interpreter/frontends/c/declarations.py` — interception logic + IR scan helper
- No changes to `lower_initializer_list` (stays as array path)
- No changes to context, VM, or other frontends

**Scope:** C frontend only. Union initializers are out of scope (separate issue if
needed). Nested struct initializers (e.g. `{{1}, 2}` for `struct Outer`) are handled
naturally — the inner `{1}` would need its own struct context from the outer struct's
field type, which requires type metadata not yet available. For now, inner initializer
lists fall through to the existing array path.

**Future:** The IR scan is a stopgap. `red-dragon-k7g` tracks proper
`ClassTypeDescriptor` metadata that will supersede this.
