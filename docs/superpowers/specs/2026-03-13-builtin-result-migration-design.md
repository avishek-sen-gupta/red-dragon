# Builtins BuiltinResult Migration (red-dragon-vva)

## Problem

Heap-mutating builtins (`_builtin_array_of`, `_builtin_object_rest`) directly write to `vm.heap` as a side effect, bypassing the `apply_update` pipeline. This means heap mutations from builtins are invisible to the StateUpdate contract — they don't appear in `new_objects` or `heap_writes`, breaking the invariant that all VM state changes flow through `apply_update`.

## Goal

1. All builtins return `BuiltinResult(value, new_objects, heap_writes)` — a uniform interface.
2. Heap-mutating builtins express their side effects as `new_objects` + `heap_writes` in the result.
3. Pure builtins return `BuiltinResult` with empty side-effect lists.
4. `_try_builtin_call` and `METHOD_TABLE` dispatch assemble `StateUpdate` from `BuiltinResult` — no isinstance branching.
5. No builtin directly mutates `vm.heap`.

## Design

### 1. New dataclass: `BuiltinResult`

Lives in `interpreter/vm_types.py`:

```python
@dataclass
class BuiltinResult:
    value: Any
    new_objects: list[NewObject] = field(default_factory=list)
    heap_writes: list[HeapWrite] = field(default_factory=list)
```

`value` is the return value (heap address string, scalar, `Operators.UNCOMPUTABLE`, etc.).

### 2. Pure builtins

All pure builtins (`_builtin_len`, `_builtin_range`, `_builtin_print`, `_builtin_int`, `_builtin_float`, `_builtin_str`, `_builtin_bool`, `_builtin_abs`, `_builtin_max`, `_builtin_min`) return `BuiltinResult(value=...)` with default empty side-effect lists.

Example:
```python
def _builtin_len(args, vm):
    ...
    return BuiltinResult(value=len(fields))
```

`UNCOMPUTABLE` is returned as `BuiltinResult(value=Operators.UNCOMPUTABLE)`.

### 3. Heap-mutating builtins

**`_builtin_array_of`** — currently mutates `vm.heap[addr]` and `vm.symbolic_counter`. After:

```python
def _builtin_array_of(args, vm):
    addr = f"{ARR_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    fields = {
        str(i): val if isinstance(val, TypedValue) else typed_from_runtime(val)
        for i, val in enumerate(args)
    }
    fields["length"] = typed(len(args), scalar(TypeName.INT))
    return BuiltinResult(
        value=addr,
        new_objects=[NewObject(addr=addr, type_hint="array")],
        heap_writes=[
            HeapWrite(obj_addr=addr, field=k, value=v) for k, v in fields.items()
        ],
    )
```

**`_builtin_object_rest`** — same pattern:

```python
def _builtin_object_rest(args, vm):
    ...
    rest_addr = f"{ARR_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    return BuiltinResult(
        value=rest_addr,
        new_objects=[NewObject(addr=rest_addr, type_hint="object")],
        heap_writes=[
            HeapWrite(obj_addr=rest_addr, field=k, value=v)
            for k, v in rest_fields.items()
        ],
    )
```

### 4. Partially-delegating builtins

These functions delegate to `_builtin_array_of` on their happy paths but have their own return paths that need explicit `BuiltinResult` wrapping.

**`_builtin_keys`** (3 return paths):
- UNCOMPUTABLE (no args) → `BuiltinResult(value=_UNCOMPUTABLE)`
- UNCOMPUTABLE (not on heap) → `BuiltinResult(value=_UNCOMPUTABLE)`
- Happy path → delegates to `_builtin_array_of`, passes through `BuiltinResult`

**`_builtin_slice`** (5 return paths):
- UNCOMPUTABLE (bad args) → `BuiltinResult(value=_UNCOMPUTABLE)`
- Native list/tuple → delegates to `_builtin_array_of`, passes through `BuiltinResult`
- Heap array → delegates to `_slice_heap_array` → `_builtin_array_of`, passes through
- Native string → `BuiltinResult(value=collection[py_slice])`
- Fallback UNCOMPUTABLE → `BuiltinResult(value=_UNCOMPUTABLE)`

**`_slice_heap_array`** (2 return paths):
- UNCOMPUTABLE (non-int length) → `BuiltinResult(value=_UNCOMPUTABLE)`
- Happy path → delegates to `_builtin_array_of`, passes through `BuiltinResult`

**`_method_slice`** — pure delegation to `_builtin_slice`, passes through `BuiltinResult`.

### 4b. `_builtin_print` void return

`_builtin_print` returns `BuiltinResult(value=None)`. The caller wraps this via `typed_from_runtime(None)` which produces `TypedValue(value=None, type=UNKNOWN)`. This matches the existing behavior.

### 5. Caller changes

**`_try_builtin_call`** (executor.py):

```python
result = Builtins.TABLE[func_name](args, vm)
if result.value is Operators.UNCOMPUTABLE:
    # symbolic fallback (unchanged logic)
    ...
return ExecutionResult.success(
    StateUpdate(
        register_writes={inst.result_reg: typed_from_runtime(result.value)},
        new_objects=result.new_objects,
        heap_writes=result.heap_writes,
        reasoning=f"builtin {func_name}(...) = {result.value!r}",
    )
)
```

**`METHOD_TABLE` dispatch** in `_handle_call_method` (executor.py):

```python
method_fn = Builtins.METHOD_TABLE.get(method_name)
if method_fn is not None:
    result = method_fn(obj_val, args, vm)
    if result.value is not Operators.UNCOMPUTABLE:
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: typed_from_runtime(result.value)},
                new_objects=result.new_objects,
                heap_writes=result.heap_writes,
                reasoning=f"method builtin {method_name}(...) = {result.value!r}",
            )
        )
```

### 6. `symbolic_counter` mutation

`vm.symbolic_counter += 1` stays in the builtins. This is address generation — a monotonic counter that must run eagerly to produce the address string. It's not heap state and is not managed by `apply_update`.

### 7. `_builtin_len` heap reads

`_builtin_len` reads `vm.heap[addr].fields` — reads are fine. Only writes are migrated to `BuiltinResult`. Same for `_builtin_keys` reading field names and `_slice_heap_array` reading elements.

## What stays the same

- `Builtins.TABLE` and `METHOD_TABLE` structure — unchanged.
- `BYTE_BUILTINS` — they don't touch the heap, but must also return `BuiltinResult`.
- Builtin function signatures `(args: list[Any], vm: VMState) -> BuiltinResult`.
- Method builtin signatures `(obj: Any, args: list[Any], vm: VMState) -> BuiltinResult`.

## Testing

- Update `test_builtin_len_array.py`: `_builtin_array_of` returns `BuiltinResult`, unwrap `.value` for address.
- Update `test_builtin_keys.py`: same unwrapping.
- New unit test: `_builtin_object_rest` returns `BuiltinResult` with correct `new_objects` and `heap_writes`.
- New unit test: pure builtins return `BuiltinResult` with empty side-effect lists.
- Integration tests via `run()` verify end-to-end behavior unchanged (11,481+ tests).

## Follow-up

- `BYTE_BUILTINS` (COBOL) also need migration to `BuiltinResult` — included in this task since they're in the same `TABLE`.
