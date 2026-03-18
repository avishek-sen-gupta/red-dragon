# Fix _resolve_reg() TypedValue Unwrapping — Design Spec

## Problem

`_resolve_reg()` strips `TypedValue` wrappers from register values, returning bare values. Downstream handlers that store values (DECL_VAR, STORE_VAR, STORE_FIELD, etc.) then re-wrap via `typed_from_runtime()`, which can only infer primitive types — everything else gets `UNKNOWN`. This means parameterized types like `pointer(scalar("Dog"))` set by NEW_OBJECT are lost when they reach local vars.

## Solution

Change `_resolve_reg()` to return `TypedValue` instead of bare values. This preserves type information through the entire register→handler→storage pipeline.

### Changes

**1. `_resolve_reg` returns `TypedValue`**

```python
def _resolve_reg(vm: VMState, operand: str) -> TypedValue:
    """Resolve a register name to its TypedValue."""
    if isinstance(operand, str) and operand.startswith("%"):
        frame = vm.current_frame
        val = frame.registers.get(operand, operand)
        if isinstance(val, TypedValue):
            return val
        return typed_from_runtime(val)
    return typed_from_runtime(operand)
```

**2. Delete `_resolve_binop_operand`** — now identical to `_resolve_reg`. Update its 8 callsites in `_handle_binop` to use `_resolve_reg`.

**3. 7 write callsites drop `typed_from_runtime`** — the returned `TypedValue` is used directly:

- `_handle_decl_var`: `var_writes={name: val}` (was `typed_from_runtime(val)`)
- `_handle_store_var`: `tv = val` (was `typed_from_runtime(val)`)
- `_handle_store_indirect`: `value=val` in HeapWrite (was `typed_from_runtime(val)`)
- `_handle_store_field`: `value=val` in HeapWrite (was `typed_from_runtime(val)`)
- `_handle_store_index`: `value=val` in HeapWrite (was `typed_from_runtime(val)`)
- `_handle_return`: `tv = val` (was `typed_from_runtime(val)`)
- `_handle_throw`: no storage change needed (reasoning string only)

**4. 19 read callsites add `.value`** — they need bare values for `_heap_addr()`, `isinstance()`, `bool()`, `int()`, dict lookups, indexing:

```python
obj_val = _resolve_reg(vm, inst.operands[0]).value
```

This includes two callsites outside `executor.py`:

- `backend.py:95`: `_serialize_value(_resolve_reg(state, op).value)` — serializer expects bare values
- `vm.py` `_resolve_typed_reg`: `_coerce_value(_resolve_reg(vm, operand).value, ...)` — `runtime_type_name()` and coercion expect bare values

## What stays the same

- `apply_update` — already stores `TypedValue` as-is in `var_writes` and `register_writes`
- `typed_from_runtime` — still used as fallback when a register holds a non-TypedValue (legacy/transition)
- `_heap_addr()` — still operates on bare values
- Heap dict keys — still bare strings

## Affected callsites

| Category | Count | Change |
|----------|-------|--------|
| Write (type-preserving) | 7 | Drop `typed_from_runtime`, use `TypedValue` directly |
| Read (bare value) | 19 | Add `.value` suffix |
| `_resolve_binop_operand` | 8 | Replace with `_resolve_reg` |
| `_resolve_binop_operand` def | 1 | Delete |
| **Total** | 35 | |

## Testing

- Unit: `_resolve_reg` returns `TypedValue` with preserved type
- Integration: `pointer(scalar("Dog"))` survives from NEW_OBJECT through DECL_VAR to `local_vars`
- All 11944 existing tests stay green

## Beads issue

`red-dragon-s47a`
