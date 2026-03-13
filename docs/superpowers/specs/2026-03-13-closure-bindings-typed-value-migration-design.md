# ClosureEnvironment.bindings TypedValue Migration (red-dragon-0xf)

## Problem

`ClosureEnvironment.bindings` stores raw values. Every write site unwraps TypedValue before storing, and the single read site re-wraps via `typed_from_runtime()`. This unwrap/re-wrap roundtrip loses type information, same pattern eliminated from registers, vars, return_value, HeapWrite.value, and HeapObject.fields.

## Goal

1. `ClosureEnvironment.bindings` stores TypedValue directly.
2. Write sites pass through TypedValue instead of unwrapping.
3. The read site passes through TypedValue instead of re-wrapping.
4. `_serialize_value()` in `to_dict()` already handles TypedValue — no change needed.

## Design

### 1. Write sites — stop unwrapping

**`_handle_const` creation (executor.py ~line 98-103):**

Current:
```python
env = ClosureEnvironment(
    bindings={
        k: v.value if isinstance(v, TypedValue) else v
        for k, v in enclosing.local_vars.items()
    }
)
```

After — pass through TypedValue directly:
```python
env = ClosureEnvironment(bindings=dict(enclosing.local_vars))
```

**`_handle_const` reuse (executor.py ~line 93-94):**

Current:
```python
for k, v in enclosing.local_vars.items():
    if k not in env.bindings:
        env.bindings[k] = v.value if isinstance(v, TypedValue) else v
```

After:
```python
for k, v in enclosing.local_vars.items():
    if k not in env.bindings:
        env.bindings[k] = v
```

**`apply_update` sync-back (vm.py ~line 300):**

Current:
```python
env.bindings[var] = raw_val
```

After:
```python
env.bindings[var] = tv
```

Remove `raw_val = tv.value` (line 289) — it becomes dead code after this change. Remove the stale comment `# Closure bindings stay raw`.

### 2. Read site — pass through TypedValue

**`_try_user_function_call` (executor.py ~line 1092-1093):**

Current:
```python
new_vars = (
    {k: typed_from_runtime(v) for k, v in captured.items()} if captured else {}
)
```

After — all write sites change atomically, so bindings are always TypedValue:
```python
new_vars = dict(captured) if captured else {}
```

### 3. Type annotation

`ClosureEnvironment.bindings: dict[str, Any]` stays unchanged. Narrowing to `dict[str, TypedValue]` happens in red-dragon-rrb.

## What stays the same

- `ClosureEnvironment.to_dict()` — `_serialize_value()` already handles TypedValue
- Keys-only read at executor.py ~line 116 — unaffected
- Shared mutable environment semantics — unchanged

## Testing

- Existing test suite (11,481+) verifies no regressions.
- Update `test_closure_binding_unwraps_value` in `test_materialize_raw_update.py`: assert bindings store TypedValue, not raw values.
- New unit test: verify closure creation stores TypedValue in bindings.
- Existing closure integration tests (`test_closures.py`, Rosetta closure tests) verify end-to-end semantics.

## Follow-up

- **red-dragon-rrb** — Remove transition isinstance guards, narrow field types including `bindings: dict[str, TypedValue]`
