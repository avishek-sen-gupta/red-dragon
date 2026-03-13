# HeapObject.fields TypedValue Migration (red-dragon-x2t) — Phase 2

## Problem

After Phase 1 (red-dragon-gny), `HeapWrite.value` carries TypedValue through the pipeline, but `apply_update` unwraps it before storing in `HeapObject.fields`. Every reader then re-wraps via `typed_from_runtime()`. This unwrap/re-wrap roundtrip loses type information that was already computed.

## Goal

1. `HeapObject.fields` stores `TypedValue` directly — no unwrap at write time.
2. Readers that need TypedValue (`_handle_load_field`, `_handle_load_index`) pass through directly.
3. Readers that need raw values (`_builtin_len`, `_serialize_value`) unwrap explicitly.
4. Builtins that create HeapObjects wrap values with `typed_from_runtime()` at construction.

## Scope

This migration covers `HeapObject.fields` storage only. Builtins continue to create HeapObjects directly (refactoring builtins to emit StateUpdate is red-dragon-vva, a separate issue).

## Design

### 1. Write sites — stop unwrapping, store TypedValue

**`apply_update` heap_writes loop (vm.py):**

Current:
```python
val = (
    hw.value.value
    if isinstance(hw.value, TypedValue)
    else _deserialize_value(hw.value, vm)
)
vm.heap[hw.obj_addr].fields[hw.field] = val
```

After:
```python
val = (
    hw.value
    if isinstance(hw.value, TypedValue)
    else typed_from_runtime(_deserialize_value(hw.value, vm))
)
vm.heap[hw.obj_addr].fields[hw.field] = val
```

The `isinstance` guard handles LLM responses that may produce raw values before materialization. Removed in red-dragon-rrb.

**`apply_update` alias var_writes (vm.py):**

Current:
```python
raw_val = tv.value if isinstance(tv, TypedValue) else tv
vm.heap[alias_ptr.base].fields[str(alias_ptr.offset)] = raw_val
```

After:
```python
typed_val = tv if isinstance(tv, TypedValue) else typed_from_runtime(tv)
vm.heap[alias_ptr.base].fields[str(alias_ptr.offset)] = typed_val
```

**`_handle_load_field` symbolic cache (executor.py ~line 439):**

Current:
```python
heap_obj.fields[field_name] = sym
```

After:
```python
heap_obj.fields[field_name] = typed(sym, UNKNOWN)
```

**`_builtin_array_of` (builtins.py):**

Current:
```python
fields = {str(i): val for i, val in enumerate(args)}
fields["length"] = len(args)
```

After — use isinstance guard so both raw and TypedValue inputs are handled:
```python
fields = {
    str(i): val if isinstance(val, TypedValue) else typed_from_runtime(val)
    for i, val in enumerate(args)
}
fields["length"] = typed(len(args), scalar(TypeName.INT))
```

**`_builtin_object_rest` (builtins.py):**

Current:
```python
rest_fields = {k: v for k, v in source_fields.items() if k not in excluded}
```

After — source fields are already TypedValue (they come from the heap), so pass through:
```python
rest_fields = {k: v for k, v in source_fields.items() if k not in excluded}
```
No change needed here since source fields are already TypedValue after this migration.

**`_handle_address_of` address-of promotion (executor.py):**

Current:
```python
vm.heap[mem_addr] = HeapObject(type_hint=None, fields={"0": current_val})
```

After:
```python
vm.heap[mem_addr] = HeapObject(type_hint=None, fields={"0": typed_from_runtime(current_val)})
```

### 2. Read sites — pass through TypedValue or unwrap

**Important:** `typed_from_runtime` is NOT idempotent — passing a TypedValue wraps it inside another TypedValue with UNKNOWN type. Every read site that previously called `typed_from_runtime(raw)` unconditionally must use an `isinstance` guard to avoid double-wrapping.

**`_handle_load_field` (executor.py, 3 sites: pointer dereference ~line 378, pointer field ~line 387, regular field ~line 430):**

Current:
```python
raw = heap_obj.fields[field_name]
tv = typed_from_runtime(raw)
```

After:
```python
val = heap_obj.fields[field_name]
tv = val if isinstance(val, TypedValue) else typed_from_runtime(val)
```

The `isinstance` guard handles the transition period. Removed in red-dragon-rrb.

**`_handle_load_index` (executor.py ~line 523):**

Same `isinstance` guard pattern as `_handle_load_field` — one read site where `heap_obj.fields[key]` is wrapped via `typed_from_runtime`.

**`_handle_load_var` alias path (executor.py):**

Same pattern — pass through TypedValue if already wrapped.

**`_builtin_len` (builtins.py):**

Current:
```python
length = vm.heap[addr].fields.get("length")
```

After:
```python
length_tv = vm.heap[addr].fields.get("length")
length = length_tv.value if isinstance(length_tv, TypedValue) else length_tv
```

**`_slice_heap_array` (builtins.py):**

Current:
```python
length = heap_obj.fields.get("length", len(heap_obj.fields))
if not isinstance(length, int):
    return _UNCOMPUTABLE
indices = range(length)[py_slice]
elements = [heap_obj.fields.get(str(i)) for i in indices]
return _builtin_array_of(elements, vm)
```

After — unwrap "length" before the `isinstance` check. Element fields are TypedValue and pass through to `_builtin_array_of`, which uses the isinstance guard to avoid double-wrapping:
```python
length_raw = heap_obj.fields.get("length", len(heap_obj.fields))
length = length_raw.value if isinstance(length_raw, TypedValue) else length_raw
if not isinstance(length, int):
    return _UNCOMPUTABLE
indices = range(length)[py_slice]
elements = [heap_obj.fields.get(str(i)) for i in indices]
return _builtin_array_of(elements, vm)
```

**Call-index read site in `_handle_call_builtin_or_dispatch` (executor.py ~line 1178):**

Current:
```python
element = heap_obj.fields[idx_key]
return ExecutionResult.success(
    StateUpdate(
        register_writes={inst.result_reg: typed_from_runtime(element)},
        ...
    )
)
```

After — pass through TypedValue directly:
```python
element = heap_obj.fields[idx_key]
tv = element if isinstance(element, TypedValue) else typed_from_runtime(element)
return ExecutionResult.success(
    StateUpdate(
        register_writes={inst.result_reg: tv},
        ...
    )
)
```

**`_builtin_len` fallback path (builtins.py):**

The fallback `len(fields)` returns the dict's size (an int), which is unaffected by field values being TypedValue. No change needed for this path.

**`HeapObject.to_dict()` (vm_types.py):**

`_serialize_value()` already handles TypedValue unwrapping recursively. No change needed.

### 3. HeapObject field type annotation

`HeapObject.fields: dict[str, Any]` stays unchanged. Narrowing to `dict[str, TypedValue]` happens in red-dragon-rrb after all producers are migrated and transition guards are removed.

## What stays the same

- `ClosureEnvironment.bindings` stays raw (red-dragon-0xf)
- `HeapObject.to_dict()` / `_serialize_value()` — already handles TypedValue
- `_builtin_keys` — iterates field keys (strings), unaffected
- Builtins still create HeapObjects directly (red-dragon-vva refactors this)

## Testing

- Existing test suite (11,474+) verifies no regressions.
- Update unit tests in `test_heap_writes_typed.py`:
  - `apply_update` now stores TypedValue in fields (not raw)
  - Verify field values are TypedValue instances with correct `.value` and `.type`
- Update integration tests in `test_heap_writes_typed.py`:
  - End-to-end STORE_FIELD → LOAD_FIELD roundtrip preserves TypedValue in heap
  - End-to-end STORE_INDEX → LOAD_INDEX roundtrip preserves TypedValue in heap
- Update ~40 test assertions across 8 test files that check `heap_obj.fields[key] == raw_value` to unwrap via `.value` first or use a helper.

## Follow-up

- **red-dragon-vva** — Refactor builtins to emit StateUpdate with heap_writes
- **red-dragon-rrb** — Remove transition guards, narrow field types
- **red-dragon-0xf** — Extend TypedValue to ClosureEnvironment.bindings
