# Return Value TypedValue Migration (red-dragon-n9m)

## Problem

`_handle_return` serializes return values via `_serialize_value(val)`, and `_handle_return_flow` deserializes them back via `_deserialize_value` before wrapping in `typed_from_runtime`. This is the same serialize/deserialize roundtrip eliminated from register_writes and var_writes in red-dragon-132.

Additionally, the current design conflates two distinct concepts: "no return value because this isn't a RETURN instruction" and "the function returned None/null". Both produce `return_value = None` on StateUpdate. The `is not None` guard in `_handle_return_flow` prevents writing to the caller's result register for both cases, which happens to be correct but obscures the semantics.

## Goal

1. `_handle_return` produces `TypedValue` directly — no serialize/deserialize roundtrip.
2. Three return states are clearly distinguished via TypedValue's type:
   - `typed(None, scalar("Void"))` — void return (no operands, or explicit `return` with no value)
   - `typed(None, UNKNOWN)` — explicit `return None`/`return null`
   - `typed(42, scalar("Int"))` — concrete return value
3. `_handle_return_flow` writes unconditionally to the caller's result register (when `result_reg` exists).
4. The LLM path materializes `return_value` at the boundary via `materialize_raw_update`.

## Design

### 1. Add Void to TypeName

Add `VOID = "Void"` to `TypeName` in `interpreter/constants.py`.

### 2. Migrate _handle_return (executor.py)

Current:
```python
def _handle_return(inst, vm, **kwargs):
    val = _resolve_reg(vm, inst.operands[0]) if inst.operands else None
    return ExecutionResult.success(
        StateUpdate(
            return_value=_serialize_value(val),
            call_pop=True,
            reasoning=f"return {val!r}",
        )
    )
```

After:
```python
def _handle_return(inst, vm, **kwargs):
    if inst.operands:
        val = _resolve_reg(vm, inst.operands[0])
        tv = typed_from_runtime(val)
    else:
        tv = typed(None, scalar(constants.TypeName.VOID))
    return ExecutionResult.success(
        StateUpdate(
            return_value=tv,
            call_pop=True,
            reasoning=f"return {tv.value!r}",
        )
    )
```

Note: when `val` is Python `None` (from `_parse_const("None")` or `_resolve_reg` returning `None`), `typed_from_runtime(None)` produces `typed(None, UNKNOWN)` — distinguishable from Void.

Note: In practice, the Void branch rarely fires. Nearly all frontends emit `RETURN %reg` with an operand even for void returns — they emit `CONST None` (or `"()"` for Rust/Scala, `"0"` for C) first, then `RETURN %reg`. The Void branch exists for hand-crafted IR or edge cases where RETURN has no operands.

### 3. Migrate _handle_return_flow (run.py)

Current:
```python
if return_frame.result_reg and update.return_value is not None:
    raw = _deserialize_value(update.return_value, vm)
    caller_frame.registers[return_frame.result_reg] = typed_from_runtime(raw)
```

After:
```python
if return_frame.result_reg and update.return_value is not None:
    caller_frame.registers[return_frame.result_reg] = update.return_value
```

The `is not None` guard stays — it now only triggers for non-RETURN instructions (where `return_value` is the Pydantic field default `None`). All RETURN instructions produce a TypedValue (including Void), so they always pass the guard and write to the register. The `_deserialize_value` + `typed_from_runtime` calls are eliminated.

### 4. Materialize return_value for LLM path (vm.py)

Add return_value materialization to `materialize_raw_update`:

```python
materialized_rv = raw_update.return_value
if raw_update.return_value is not None and not isinstance(raw_update.return_value, TypedValue):
    deserialized = _deserialize_value(raw_update.return_value, vm)
    materialized_rv = typed_from_runtime(deserialized)
```

Include `"return_value": materialized_rv` in the `model_copy(update={...})` call.

The `isinstance` guard here is justified — unlike the handler path where we control all producers, LLM responses are always raw, but `materialize_raw_update` is also called during the transition period by `coerce_local_update`'s callers. The guard is cheap and prevents double-wrapping.

### 5. _serialize_value import in executor.py

After this migration, `_serialize_value` is no longer used for `return_value`. The remaining usages are `heap_writes` in `_handle_store_field` (2 sites) and `_handle_store_index` (1 site). The import stays with its existing comment — removal is tracked in red-dragon-gny.

### 6. StateUpdate field type

The field `return_value: Any | None = None` stays unchanged. The `Any` accommodates both TypedValue (from handlers) and raw values (from LLM, before materialization). The `None` default means "this update doesn't involve a RETURN instruction". Narrowing to `TypedValue | None` can happen after red-dragon-rrb removes the transition fallbacks.

## What stays the same

- `backend.py` LLM template — unchanged
- `call_pop` semantics — unchanged
- `_handle_throw` — unchanged (doesn't use `return_value`)
- `coerce_local_update` — passes `return_value` through unchanged. It only operates on `register_writes` (via `model_copy`), so the TypedValue in `return_value` flows through to `apply_update` and then `_handle_return_flow` untouched.

## Testing

- Existing test suite (11,400+) verifies no regressions.
- New unit tests for:
  - `_handle_return` with operands → TypedValue with inferred type
  - `_handle_return` without operands → `typed(None, scalar("Void"))`
  - `_handle_return` with None operand → `typed(None, UNKNOWN)` (distinguishable from Void)
  - `materialize_raw_update` with raw `return_value` → TypedValue
  - `materialize_raw_update` with `return_value: null` → stays None

## Follow-up

- **red-dragon-gny** — Migrate `heap_writes` to TypedValue
- **red-dragon-rrb** — Simplify `apply_update` and narrow `StateUpdate` field types after full migration
