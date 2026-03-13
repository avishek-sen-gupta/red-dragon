# Heap Writes TypedValue Migration (red-dragon-gny) — Phase 1

## Problem

`_handle_store_field` and `_handle_store_index` serialize values via `_serialize_value(val)` into `HeapWrite`, and `apply_update` deserializes them back via `_deserialize_value` before storing in `HeapObject.fields`. This is the same serialize/deserialize roundtrip eliminated from register_writes, var_writes, and return_value in red-dragon-132 and red-dragon-n9m.

## Goal

1. `_handle_store_field` and `_handle_store_index` produce `TypedValue` in `HeapWrite.value` directly — no serialize/deserialize roundtrip.
2. `apply_update` unwraps `TypedValue` before storing in `HeapObject.fields` (heap stays raw in Phase 1).
3. The LLM path materializes `heap_writes` values at the boundary via `materialize_raw_update`.
4. `_serialize_value` is removed from executor.py imports (zero usages remaining there).

## Scope — Phase 1 only

This migration covers `HeapWrite.value` only. `HeapObject.fields` continues to store raw values. Migrating heap storage itself to `TypedValue` is Phase 2 (separate issue).

## Design

### 1. Migrate HeapWrite producers (executor.py)

Three sites replace `_serialize_value(val)` with `typed_from_runtime(val)`:

- `_handle_store_field` line 336 (pointer dereference path)
- `_handle_store_field` line 361 (regular field path)
- `_handle_store_index` line 474

After this, `_serialize_value` has zero usages in executor.py. Remove the import. The comment on the import line referencing red-dragon-gny is also removed.

### 2. Migrate HeapWrite consumer (apply_update in vm.py)

Current:
```python
vm.heap[hw.obj_addr].fields[hw.field] = _deserialize_value(hw.value, vm)
```

After:
```python
val = hw.value.value if isinstance(hw.value, TypedValue) else _deserialize_value(hw.value, vm)
vm.heap[hw.obj_addr].fields[hw.field] = val
```

The `isinstance` guard handles the transition — local handlers produce TypedValue, LLM responses (before materialization) may produce raw values. This guard is removed in red-dragon-rrb.

### 3. Extend materialize_raw_update for heap_writes (vm.py)

Add heap_writes materialization so the LLM path also wraps values in TypedValue:

```python
typed_heap_writes = [
    HeapWrite(
        obj_addr=hw.obj_addr,
        field=hw.field,
        value=(
            hw.value
            if isinstance(hw.value, TypedValue)
            else typed_from_runtime(_deserialize_value(hw.value, vm))
        ),
    )
    for hw in raw_update.heap_writes
]
```

Include `"heap_writes": typed_heap_writes` in the `model_copy(update={...})` call.

### 4. HeapWrite model field type

`HeapWrite.value: Any` stays unchanged. Narrowing to `TypedValue` happens in red-dragon-rrb after all producers are migrated.

## What stays the same

- `HeapObject.fields` stores raw values (Phase 2)
- All LOAD_FIELD/LOAD_INDEX readers still use `typed_from_runtime()` (Phase 2)
- Builtins that write directly to `HeapObject.fields` stay raw (Phase 2)
- Alias var writes in `apply_update` (line 275) stay raw (Phase 2)
- `_serialize_value` remains in vm_types.py (used by `StackFrame.to_dict()`)

## Testing

- Existing test suite (11,461+) verifies no regressions.
- New unit tests for:
  - `_handle_store_field` producing TypedValue in `HeapWrite.value`
  - `_handle_store_index` producing TypedValue in `HeapWrite.value`
  - `materialize_raw_update` materializing raw `heap_writes` values
  - `materialize_raw_update` passing through already-typed `heap_writes`
- New integration tests for:
  - End-to-end STORE_FIELD → LOAD_FIELD roundtrip via `run()`
  - End-to-end STORE_INDEX → LOAD_INDEX roundtrip via `run()`

## Follow-up

- **Phase 2** (new issue) — Migrate `HeapObject.fields` to store `TypedValue`
- **red-dragon-rrb** — Simplify `apply_update`, narrow field types after full migration
