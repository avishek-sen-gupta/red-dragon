# Handler TypedValue Migration (red-dragon-132)

## Problem

Executor handlers produce raw Python values in `register_writes` and `var_writes`. The wrapping into `TypedValue` happens in `apply_update`, which also deserializes serialized dicts (SymbolicValue, Pointer) back into objects. This creates an unnecessary serialize/deserialize roundtrip for local execution: handlers call `_serialize_value()` to flatten objects, then `apply_update` calls `_deserialize_value()` to reconstruct them.

The LLM path genuinely needs serialization (JSON transport), but the local executor path does not.

## Goal

Handlers produce `TypedValue` directly in `register_writes` and `var_writes`. `apply_update` stores values directly (with lightweight type coercion). The serialize/deserialize roundtrip is eliminated from local execution. The LLM path transforms raw values into `TypedValue` at the boundary before reaching `apply_update`.

## Design

### 1. Split apply_update responsibilities

**`apply_update(vm, update, type_env, conversion_rules)`** — receives TypedValue in register_writes and var_writes. Stores them directly, with one exception: **assignment-time type coercion**. Since coercion depends on the target register's declared type (which only `apply_update` knows via `type_env`), `apply_update` checks if the TypedValue's type matches the declared type and coerces if needed. This is a lightweight unwrap-coerce-rewrap, not the full deserialize+infer path.

```python
for reg, tv in update.register_writes.items():
    declared = type_env.register_types.get(reg, UNKNOWN)
    if declared and tv.type != declared:
        coerced = _coerce_value(tv.value, reg, type_env, conversion_rules)
        frame.registers[reg] = typed(coerced, declared)
    else:
        frame.registers[reg] = tv
```

For var_writes, when a variable has a heap alias, `apply_update` unwraps `.value` from the TypedValue and writes raw to the heap (heap fields are not yet TypedValue — that's red-dragon-gny). Similarly, closure bindings receive `.value` (raw) since closure environments stay raw (red-dragon-0xf).

All other update fields (heap_writes, new_objects, new_regions, call_push, call_pop, continuations, path_condition) remain unchanged.

**`materialize_raw_update(raw_update, vm, type_env, conversion_rules)`** — new function. Takes a StateUpdate with raw values (from LLM), deserializes via `_deserialize_value`, coerces via `_coerce_value`, and wraps into TypedValue. Returns a new StateUpdate with TypedValue in register_writes and var_writes. This is the existing apply_update register/var logic extracted into a preparation step.

### 2. Execution loop change

In `execute_cfg` and `execute_cfg_traced`:

```python
result = _try_execute_locally(instruction, vm, ...)
if result.handled:
    update = result.update                          # already has TypedValue
else:
    raw_update = llm.interpret_instruction(instruction, vm)
    update = materialize_raw_update(raw_update, vm, type_env, conversion_rules)

apply_update(vm, update)  # always receives TypedValue
```

Same pattern in `_handle_call_dispatch_setup`.

### 3. Handler migration pattern

Not all handlers currently use `_serialize_value` uniformly. The current state is mixed:

| Current pattern | Examples | Migration |
|---|---|---|
| `_serialize_value(val)` | `_handle_load_var`, `_handle_store_var`, `_handle_load_field`, builtins | `typed_from_runtime(val)` |
| `sym.to_dict()` | `_handle_symbolic`, `_handle_unop`, `_handle_load_field` (missing), `_handle_load_index` (missing) | `typed(sym, UNKNOWN)` |
| Raw value (no serialization) | `_handle_const` | `typed_from_runtime(val)` |
| `SymbolicValue` object directly | `_handle_binop` | `typed(sym, UNKNOWN)` |
| `Pointer` object directly | `_handle_address_of` | `typed(ptr, scalar(TypeName.POINTER))` |
| Heap address string (e.g., `"obj_42"`) | `_handle_new_object`, `_handle_new_array`, `_try_class_constructor_call` | `typed(addr, UNKNOWN)` — these are object references, not strings |

Each handler is migrated to produce `TypedValue` directly. The `_serialize_value` call and `sym.to_dict()` calls are both eliminated in the same handler commit.

### 4. Migration order

Incremental, one handler (or small group) per commit:
1. `materialize_raw_update` + `apply_update` refactor (foundation) + `_format_val` update for TypedValue
2. Simple handlers: `_handle_const`, `_handle_store_var`
3. Value-loading handlers: `_handle_load_var`, `_handle_load_field`, `_handle_load_index`
4. Object handlers: `_handle_new_object`, `_handle_new_array`, `_handle_address_of`
5. Operator handlers: `_handle_binop`, `_handle_unop`
6. Call handlers: `_handle_call_function`, `_handle_call_method`, `_try_builtin_call`, `_try_class_constructor_call`, `_try_user_function_call`
7. Region/symbolic handlers: `_handle_alloc_region`, `_handle_load_region`, `_handle_symbolic`
8. Remove `_serialize_value` import from executor.py (final cleanup)

Note: `_handle_store_field` and `_handle_store_index` produce `heap_writes` (not register_writes/var_writes), so they are **out of scope** — their `_serialize_value` calls remain until red-dragon-gny.

### 5. _format_val and verbose logging

`_format_val` in run.py (called by `_log_update` on every step when `verbose=True`) currently checks `isinstance(v, dict) and v.get("__symbolic__")`. After migration, register_writes/var_writes contain `TypedValue`, not dicts. `_format_val` must be updated in Phase 1 (foundation) to handle TypedValue — either unwrapping to format the inner value, or adding a TypedValue branch. This is **not** a follow-up; it must land with the foundation commit to avoid broken verbose output.

### 6. _handle_return_flow

`_handle_return_flow` in run.py writes `_deserialize_value(update.return_value, vm)` directly into `caller_frame.registers[result_reg]`. Since `return_value` stays raw (red-dragon-n9m), this write must wrap in TypedValue to maintain consistency: `typed_from_runtime(_deserialize_value(update.return_value, vm))`. This is a one-line fix that lands in Phase 1.

### 7. LLM path isolation

The LLM path (`backend.py`, `unresolved_call.py`) continues producing raw values. `materialize_raw_update` transforms them at the boundary. No changes to the LLM path.

`_serialize_value` remains in `vm_types.py` and is still used by:
- `backend.py` — serializing VM state for LLM prompts
- `unresolved_call.py` — serializing args/state for LLM resolvers
- `vm_types.py` — `HeapObject.to_dict()`, `ClosureEnvironment.serialize()`, `StackFrame.to_dict()`

### 8. What stays raw

- **heap_writes** values — raw (red-dragon-gny)
- **return_value** — raw (red-dragon-n9m)
- **closure bindings** — receive `.value` from TypedValue (red-dragon-0xf)
- **heap alias writes** — receive `.value` from TypedValue (red-dragon-gny)
- **LLM responses** — raw, transformed by `materialize_raw_update`

## Testing

Each handler migration is verified by the existing 11,400+ test suite. No test assertion changes expected since the observable behavior (values stored in registers/local_vars) remains TypedValue — only the wrapping location moves from apply_update to the handler.

New unit tests for `materialize_raw_update` to verify the raw-to-TypedValue transformation.

## Follow-up issues

- **red-dragon-n9m** — Migrate `return_value` to TypedValue
- **red-dragon-gny** — Migrate `heap_writes` to TypedValue
- **red-dragon-rrb** — Simplify `apply_update` after full migration
- **red-dragon-0xf** — ClosureEnvironment.bindings TypedValue
