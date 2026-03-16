# LOAD_INDIRECT / STORE_INDIRECT Opcodes Design

**Issue:** red-dragon-aiu
**Date:** 2026-03-16
**Status:** Approved

## Goal

Replace the magic `"*"` field name convention in `LOAD_FIELD` / `STORE_FIELD` with dedicated `LOAD_INDIRECT` / `STORE_INDIRECT` opcodes for pointer dereference. This eliminates semantic overloading of field access instructions and makes pointer dereference a first-class IR concept.

## Background

ADR-099 introduced pointer aliasing via `ADDRESS_OF`, `Pointer`, and `var_heap_aliases`. Pointer dereference was implemented by overloading `LOAD_FIELD ptr "*"` and `STORE_FIELD ptr "*" val` — the VM special-cases `field_name == "*"` to read/write through `Pointer.offset` in the heap object at `Pointer.base`. This convention is used by C (`*ptr`), Rust (`*expr`), and C# (`out`/`ref`/`in` byref params).

The `"*"` string is a magic constant that overloads field access semantics, making the IR harder to reason about. Dedicated opcodes express intent clearly.

## Design

### New Opcodes

Added to the `Opcode` enum under the existing "Pointer operations" section:

```python
# Pointer operations
ADDRESS_OF = "ADDRESS_OF"
LOAD_INDIRECT = "LOAD_INDIRECT"
STORE_INDIRECT = "STORE_INDIRECT"
```

### Operand Layout

**`LOAD_INDIRECT`**: `result_reg=%r`, `operands=[ptr_reg]`
- Reads the value at `Pointer.offset` in `vm.heap[Pointer.base]`
- If `ptr_reg` holds a `BoundFuncRef`, returns it unchanged (C function pointer dereference identity)
- If `ptr_reg` holds a `Pointer` whose base is not on the heap, returns a fresh symbolic

**`STORE_INDIRECT`**: `result_reg=None`, `operands=[ptr_reg, val_reg]`
- Writes `val` to `Pointer.offset` in `vm.heap[Pointer.base]`

### VM Handlers

Extract the `if field_name == "*"` branches from `_handle_load_field` and `_handle_store_field` into new `_handle_load_indirect` and `_handle_store_indirect` functions. Remove the `"*"` special cases from the existing handlers entirely (clean break, no fallback).

### Frontend Migration

6 emission sites across 3 frontends:

| Frontend | File | Line(s) | Change |
|----------|------|---------|--------|
| C | `c/expressions.py` | ~98-99 | `STORE_FIELD [ptr, "*", val]` → `STORE_INDIRECT [ptr, val]` |
| C | `c/expressions.py` | ~166-169 | `LOAD_FIELD [ptr, "*"]` → `LOAD_INDIRECT [ptr]` |
| Rust | `rust/expressions.py` | ~131-134 | `LOAD_FIELD [ptr, "*"]` → `LOAD_INDIRECT [ptr]` |
| Rust | `rust/expressions.py` | ~954-956 | `STORE_FIELD [ptr, "*", val]` → `STORE_INDIRECT [ptr, val]` |
| C# | `csharp/expressions.py` | ~331-332 | `LOAD_FIELD [reg, "*"]` → `LOAD_INDIRECT [reg]` |
| C# | `csharp/expressions.py` | ~345 | `STORE_FIELD [ptr, "*", val]` → `STORE_INDIRECT [ptr, val]` |

### Downstream Consumers

- **`type_inference.py`**: Add dispatch entries. `LOAD_INDIRECT` infers the Pointer's target type (or UNKNOWN). `STORE_INDIRECT` is a no-op for inference.
- **`dataflow.py`**: Add `LOAD_INDIRECT` to value-producing instructions set. Add def/use extraction entries for both opcodes.

## Scope

**In scope:**
- `LOAD_INDIRECT` / `STORE_INDIRECT` in `Opcode` enum
- VM handlers in `executor.py`
- Migrate C, Rust, C# frontends (6 sites)
- Update `type_inference.py` and `dataflow.py`
- Remove `"*"` special cases from `_handle_load_field` / `_handle_store_field`
- Update unit tests asserting on `LOAD_FIELD "*"` / `STORE_FIELD "*"` IR output

**Out of scope:**
- No new language features — purely a refactor
- No changes to `Pointer`, `HeapObject`, `ADDRESS_OF`, or `var_heap_aliases`

## Testing

- Existing C pointer tests, Rust deref tests, and C# byref tests are primary verification
- Update unit tests that assert `"*"` in `LOAD_FIELD`/`STORE_FIELD` operands to assert `LOAD_INDIRECT`/`STORE_INDIRECT` opcodes
- No new integration tests needed — VM behaviour is identical

### VM handler detail

In `_handle_store_field`, the `isinstance(obj_val, Pointer)` block handles both `"*"` dereference and `ptr->field` struct access. Only the `field_name == "*"` ternary path moves to `STORE_INDIRECT`; the `ptr->field` path (non-`"*"` field on a Pointer) remains in `_handle_store_field`.

In `_handle_load_field`, the `BoundFuncRef` identity guard (`field_name == "*" and isinstance(obj_val, BoundFuncRef)`) lives outside the Pointer block. This entire check moves to `_handle_load_indirect`.

### Type inference

`_infer_load_indirect` assigns UNKNOWN — preserving current effective behavior, since no class has a `"*"` field so the existing `_infer_load_field` always misses for dereferences.

## Files to Modify

- `interpreter/ir.py` — add opcodes
- `interpreter/executor.py` — add handlers, remove `"*"` special cases from LOAD_FIELD/STORE_FIELD
- `interpreter/type_inference.py` — add dispatch entries
- `interpreter/dataflow.py` — add to value-producing set and def/use extraction
- `interpreter/frontends/c/expressions.py` — migrate 2 sites
- `interpreter/frontends/rust/expressions.py` — migrate 2 sites
- `interpreter/frontends/csharp/expressions.py` — migrate 2 sites
- `tests/unit/test_csharp_frontend.py` — update byref IR assertions
- `tests/unit/test_c_frontend.py` — update pointer deref IR assertions (if any)
- `tests/unit/test_rust_frontend.py` — update deref IR assertions (if any)
- `tests/unit/test_pointer_aliasing.py` — update `"*"` field IR construction to new opcodes
- `tests/unit/test_heap_writes_typed.py` — update `STORE_FIELD "*"` construction
- `docs/ir-reference.md` — document new opcodes, remove `"*"` references
- `docs/frontend-design/c.md` — update pointer dereference documentation
- `docs/notes-on-vm-design.md` — update `"*"` convention references
