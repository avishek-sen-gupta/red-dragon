# C# Ref Expressions (Ref Locals) Design

**Issue:** red-dragon-c4v
**Date:** 2026-03-16
**Status:** Approved

## Goal

Support C# ref local variables (`ref int x = ref y;`) so that reads/writes to the ref local alias the original variable. Scoped to `ref <identifier>` — ref to array elements, object fields, ref reassignment, and ref returns are filed as separate follow-ups.

## Background

C# ref expressions create managed references (pointers) to existing variables. The simplest form is `ref int x = ref y;` — after this, reading/writing `x` reads/writes `y`.

The existing `out`/`ref`/`in` parameter infrastructure (red-dragon-ia8) already implements the dereference machinery: `ADDRESS_OF` promotes a variable to heap, `byref_params` tracks which names need dereference, and `LOAD_INDIRECT`/`STORE_INDIRECT` handle the actual read/write-through. Ref locals reuse this entire pipeline.

## Design

### Tree-sitter structure

```
variable_declaration
  ref_type "ref int"              ← type child
    predefined_type "int"
  variable_declarator "x = ref y"
    identifier "x"
    ref_expression "ref y"        ← value (initializer)
      identifier "y"
```

Two new node types: `ref_type` and `ref_expression`.

### Frontend changes

**`node_types.py`**: Add `REF_EXPRESSION = "ref_expression"` and `REF_TYPE = "ref_type"`.

**`lower_ref_expression`** (new, in `expressions.py`): Dispatch handler for `ref_expression` nodes.
- Extract the single named child (the inner expression).
- If it's an IDENTIFIER → emit `ADDRESS_OF name` (creates a `Pointer` to the variable's heap location).
- Otherwise → fall back to `ctx.lower_expr(inner)` (degraded value-only mode for unsupported inner expressions like `arr[0]` or `obj.field`).

**`lower_variable_declaration`** (in `declarations.py`): Detect when the type child is `ref_type`. If so, pass `is_ref=True` to `_lower_csharp_declarator`.

**`_lower_csharp_declarator`**: When `is_ref=True`, after declaring and storing the variable, add the variable name to `ctx.byref_params`. This makes all subsequent reads go through `emit_byref_load` (LOAD_VAR → LOAD_INDIRECT) and writes through `emit_byref_store` (LOAD_VAR → STORE_INDIRECT).

**`frontend.py`**: Add `ref_expression` to the expression dispatch table.

### IR emission example

`ref int x = ref y;` followed by `x = 42;` and `int z = x;`:

```
ADDRESS_OF y          → %0 (Pointer to y's heap location)
DECL_VAR x, %0        (x holds the Pointer)
# x = 42:
CONST 42              → %1
LOAD_VAR x            → %2 (the Pointer)
STORE_INDIRECT %2, %1 (writes 42 through to y's heap cell)
# int z = x:
LOAD_VAR x            → %3 (the Pointer)
LOAD_INDIRECT %3      → %4 (reads y's current value = 42)
DECL_VAR z, %4
```

### No VM changes

The entire feature is frontend-only. `ADDRESS_OF`, `LOAD_INDIRECT`, `STORE_INDIRECT`, and `byref_params` already exist.

## Scope

**In scope:**
- `ref int x = ref y;` — ref local aliasing a variable
- Unit and integration tests

**Out of scope (separate issues filed):**
- `ref arr[i]` — ref to array element (red-dragon-h56)
- `ref obj.field` — ref to object field (red-dragon-x3v)
- `x = ref arr[1]` — ref reassignment (red-dragon-rd3)
- `return ref x` — ref returns (red-dragon-562)

## Files to Modify

- `interpreter/frontends/csharp/node_types.py` — add REF_EXPRESSION, REF_TYPE
- `interpreter/frontends/csharp/expressions.py` — add `lower_ref_expression`
- `interpreter/frontends/csharp/declarations.py` — detect `ref_type`, pass `is_ref` flag
- `interpreter/frontends/csharp/frontend.py` — add dispatch entry
- `tests/unit/test_csharp_frontend.py` — unit tests for IR emission
- `tests/integration/test_csharp_frontend_execution.py` — integration tests for ref local aliasing

## Testing

- Unit: `ref int x = ref y;` emits ADDRESS_OF + DECL_VAR, and `x` appears in byref_params-equivalent IR (LOAD_INDIRECT on read)
- Integration: `ref int x = ref y; x = 42; int z = y;` produces `z == 42` (write-through verified)
- Integration: `ref int x = ref y; int z = x;` where `y = 10` produces `z == 10` (read-through verified)
