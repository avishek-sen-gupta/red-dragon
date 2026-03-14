# Builtins TypedValue Args Migration (red-dragon-x9r)

## Problem

Builtins receive naked Python primitives — `_resolve_reg` strips `TypedValue` wrappers before passing args to builtins. This means:
1. Type information is lost at the builtin boundary, then re-inferred via `typed_from_runtime` on the way out.
2. Symbolic fallback results carry no input type information.
3. The builtin interface is an open hole in an otherwise closed `TypedValue` type system.

## Goal

1. All builtins receive `list[TypedValue]` args instead of `list[Any]`.
2. Method builtins receive `TypedValue` obj instead of `Any`.
3. `CobolIOProvider.handle_call` receives `list[TypedValue]` args.
4. Parameter binding in user function/constructor calls passes `TypedValue` directly (no re-wrapping).
5. No naked primitives cross the builtin calling boundary.

## Design

### 1. Caller changes (executor.py)

Three call-site entry points resolve args — all switch from `_resolve_reg` to `_resolve_binop_operand`:

**`_handle_call_function` (line 1126):**
```python
# Before:
args = [_resolve_reg(vm, a) for a in arg_regs]
# After:
args = [_resolve_binop_operand(vm, a) for a in arg_regs]
```

**`_handle_call_method` (line 1236, 1239):**
```python
# Before:
obj_val = _resolve_reg(vm, inst.operands[0])
args = [_resolve_reg(vm, a) for a in arg_regs]
# After:
obj_val = _resolve_binop_operand(vm, inst.operands[0])
args = [_resolve_binop_operand(vm, a) for a in arg_regs]
```

**`_handle_call_unknown` (line 1351-1353):**
```python
# Before:
target_val = _resolve_reg(vm, inst.operands[0])
args = [_resolve_reg(vm, a) for a in arg_regs]
# After:
target_val = _resolve_binop_operand(vm, inst.operands[0])
args = [_resolve_binop_operand(vm, a) for a in arg_regs]
```

`_resolve_binop_operand` (vm.py:339) already exists — it returns `TypedValue`, falling back to `typed_from_runtime` for non-register operands.

### 2. Builtin signatures

All function builtins change from:
```python
def _builtin_foo(args: list[Any], vm: VMState) -> BuiltinResult:
```
to:
```python
def _builtin_foo(args: list[TypedValue], vm: VMState) -> BuiltinResult:
```

All method builtins change from:
```python
def _method_foo(obj: Any, args: list[Any], vm: VMState) -> BuiltinResult:
```
to:
```python
def _method_foo(obj: TypedValue, args: list[TypedValue], vm: VMState) -> BuiltinResult:
```

### 3. Builtin internals — per-builtin unwrap points

Each builtin accesses raw values via `.value`. Every unwrap point is enumerated below.

**`_builtin_len`** (3 unwrap points):
```python
val = args[0].value           # was: args[0]
addr = _heap_addr(val)        # unchanged — val is raw
if isinstance(val, (list, tuple, str)):  # unchanged — val is raw
```

**`_builtin_range`** (2 unwrap points):
```python
# Before:
if any(_is_symbolic(a) for a in args):
concrete = list(args)
# After:
if any(_is_symbolic(a.value) for a in args):
concrete = [a.value for a in args]
```
The `int(concrete[N])` calls then work on raw values as before.

**`_builtin_print`** (1 unwrap point):
```python
# Before:
logger.info("[VM print] %s", " ".join(str(a) for a in args))
# After:
logger.info("[VM print] %s", " ".join(str(a.value) for a in args))
```

**`_builtin_int`** (2 unwrap points):
```python
# Before:
if args and not _is_symbolic(args[0]):
    return BuiltinResult(value=int(args[0]))
# After:
if args and not _is_symbolic(args[0].value):
    return BuiltinResult(value=int(args[0].value))
```

**`_builtin_float`** — same pattern as `_builtin_int`: `args[0]` → `args[0].value` in both `_is_symbolic` check and `float()` call.

**`_builtin_str`** — same pattern: `args[0]` → `args[0].value` in `_is_symbolic` check and `str()` call.

**`_builtin_bool`** — same pattern: `args[0]` → `args[0].value` in `_is_symbolic` check and `bool()` call.

**`_builtin_abs`** — same pattern: `args[0]` → `args[0].value` in `_is_symbolic` check and `abs()` call.

**`_builtin_max`** (2 unwrap points):
```python
# Before:
if all(not _is_symbolic(a) for a in args):
    return BuiltinResult(value=max(args))
# After:
if all(not _is_symbolic(a.value) for a in args):
    return BuiltinResult(value=max(a.value for a in args))
```

**`_builtin_min`** — same pattern as `_builtin_max`: unwrap in `_is_symbolic` check and `min()` call.

**`_builtin_keys`** (2 unwrap points):
```python
# Before:
val = args[0]
addr = _heap_addr(val)
# After:
val = args[0].value
addr = _heap_addr(val)
```
The call to `_builtin_array_of(field_names, vm)` passes raw strings (field name strings from heap). See section 4 on why `_builtin_array_of` must retain its isinstance guard.

**`_builtin_object_rest`** (2 unwrap points):
```python
# Before:
obj_val = args[0]
excluded_keys = set(args[1:])
# After:
obj_val = args[0].value
excluded_keys = set(a.value for a in args[1:])
```

**`_builtin_slice`** (4 unwrap points):
```python
# Before:
if len(args) < 2 or any(_is_symbolic(a) for a in args):
collection = args[0]
raw_start, raw_stop, raw_step = args[1], _arg_or_none(args, 2), _arg_or_none(args, 3)
# After:
if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
collection = args[0].value
raw_start, raw_stop, raw_step = args[1].value, _arg_or_none_value(args, 2), _arg_or_none_value(args, 3)
```

`_arg_or_none` becomes `_arg_or_none_value` (unwraps `.value`):
```python
def _arg_or_none_value(args: list[TypedValue], index: int) -> Any:
    return args[index].value if index < len(args) else None
```

The isinstance/heap checks on `collection` then work on raw values as before. The delegation to `_builtin_array_of(list(collection[py_slice]), vm)` for native lists passes raw values — see section 4.

**`_method_slice`**:
```python
# Before:
def _method_slice(obj: Any, args: list[Any], vm: VMState) -> BuiltinResult:
    return _builtin_slice([obj, *args], vm)
# After:
def _method_slice(obj: TypedValue, args: list[TypedValue], vm: VMState) -> BuiltinResult:
    return _builtin_slice([obj, *args], vm)
```
This works — `obj` and `args` are already TypedValue, so `[obj, *args]` is `list[TypedValue]`.

**Note on `_arg_or_none`:** Renamed to `_arg_or_none_value` and changed to unwrap `.value`:
```python
def _arg_or_none_value(args: list[TypedValue], index: int) -> Any:
    return args[index].value if index < len(args) else None
```

### 4. `_builtin_array_of` — isinstance guard retained

`_builtin_array_of` is called from two categories of callers:
1. **External callers** (executor.py arg injection, `Builtins.TABLE` dispatch) — pass `list[TypedValue]` after migration.
2. **Internal callers** (`_builtin_keys`, `_builtin_slice`, `_slice_heap_array`) — may pass raw values (field name strings from heap, sliced list elements).

The isinstance guard **must be retained**:
```python
fields = {
    str(i): val if isinstance(val, TypedValue) else typed_from_runtime(val)
    for i, val in enumerate(args)
}
```

This is safe — it normalizes both TypedValue and raw inputs. The guard can be removed as a follow-up once all internal callers are also migrated to wrap their inputs.

### 5. `_try_builtin_call` — symbolic fallback and reasoning

The UNCOMPUTABLE path and success path format args for reasoning strings. After migration, `a` is TypedValue:

```python
# UNCOMPUTABLE path (line 941):
args_desc = ", ".join(_symbolic_name(a.value) for a in args)

# Success path reasoning (line 956-958):
reasoning=(
    f"builtin {func_name}"
    f"({', '.join(repr(a.value) for a in args)}) = {result.value!r}"
),
```

### 6. IOProvider changes

**`CobolIOProvider.handle_call`** signature changes:
```python
# Before:
def handle_call(self, func_name: str, args: list[Any]) -> Any:
    ...
    return method(*args)

# After:
def handle_call(self, func_name: str, args: list[TypedValue]) -> Any:
    ...
    return method(*[a.value for a in args])
```

The base class `handle_call` unwraps `.value` before splatting to internal methods (`_accept`, `_write_record`, etc.), which keep their raw-typed signatures since they're private implementation details.

The executor call site (line 1134) needs no change for the `handle_call` invocation — args are already TypedValue after step 1.

The reasoning strings at lines 1139 and 1147 must unwrap:
```python
# Before:
reasoning=f"io_provider {func_name}({args!r}) = {result!r}",
# After:
reasoning=f"io_provider {func_name}({[a.value for a in args]!r}) = {result!r}",
```

### 7. Parameter binding cleanup

**`_try_user_function_call` (line 1064-1068):**
```python
# Before:
param_vars = {
    params[i]: typed_from_runtime(arg)
    for i, arg in enumerate(args)
    if i < len(params)
}

# After:
param_vars = {
    params[i]: arg
    for i, arg in enumerate(args)
    if i < len(params)
}
```

Args are already TypedValue — no re-wrapping needed.

**`_handle_call_method` param binding (lines 1314-1317):**
```python
# Before:
new_vars[params[0]] = typed_from_runtime(obj_val)
for i, arg in enumerate(args):
    if i + 1 < len(params):
        new_vars[params[i + 1]] = typed_from_runtime(arg)

# After:
new_vars[params[0]] = obj_val
for i, arg in enumerate(args):
    if i + 1 < len(params):
        new_vars[params[i + 1]] = arg
```

`obj_val` and `arg` are already TypedValue — `typed_from_runtime` would double-wrap.

**`_try_class_constructor_call` param binding (lines 1016-1024):**
```python
# Before (Python-style):
for i, arg in enumerate(args):
    if i + 1 < len(params):
        new_vars[params[i + 1]] = typed_from_runtime(arg)

# Before (Java/C++-style):
for i, arg in enumerate(args):
    if i < len(params):
        new_vars[params[i]] = typed_from_runtime(arg)

# After (both paths):
# Replace typed_from_runtime(arg) with just arg
```

### 8. `arguments` injection

The two direct calls to `_builtin_array_of` for arguments injection (lines 1070, 1319) pass `list(args)` where `args` is now `list[TypedValue]`. This works — `_builtin_array_of` receives TypedValue args directly, the isinstance guard passes them through.

### 9. Scala-style apply and native indexing

**Scala-style apply (line 1167):**
```python
# Before:
if len(args) == 1 and isinstance(args[0], int):
    addr = _heap_addr(func_val)
    ...
    idx_key = str(args[0])
    ...
    reasoning=f"heap call-index {func_name}({args[0]}) = {tv!r}",

# After:
if len(args) == 1 and isinstance(args[0].value, int):
    addr = _heap_addr(func_val)
    ...
    idx_key = str(args[0].value)
    ...
    reasoning=f"heap call-index {func_name}({args[0].value}) = {tv!r}",
```

Note: `func_val` here is resolved from `local_vars[func_name].value` (line 1160) — it's already unwrapped, so `_heap_addr(func_val)` is fine.

**Native string/list indexing (lines 1183-1191):**
```python
# Before:
and isinstance(args[0], int)
element = func_val[args[0]]
reasoning=f"native call-index {func_name}({args[0]}) = {element!r}",

# After:
and isinstance(args[0].value, int)
element = func_val[args[0].value]
reasoning=f"native call-index {func_name}({args[0].value}) = {element!r}",
```

### 10. Overload resolver call sites

**Superseded:** The overload resolver now accepts `list[TypedValue]` directly (see `2026-03-13-overload-resolution-typedvalue-design.md`). Call sites pass `args` without unwrapping:

```python
winner = overload_resolver.resolve(sigs, args)
```

`DefaultTypeCompatibility` reads `arg.type` (a `TypeExpr`) instead of calling `runtime_type_name()`, and uses `TypeGraph.is_subtype_expr()` for subtype-aware scoring.

### 11. Unresolved call resolver

The `UnresolvedCallResolver` receives `args` from executor.py call sites. After migration, these are `list[TypedValue]`. The resolver uses `_symbolic_name(a)` and `_serialize_value(a)` which expect raw values.

**Unwrap at call sites** in executor.py (4 locations):
```python
# _handle_call_function line 1164:
return call_resolver.resolve_call(func_name, [a.value for a in args], inst, vm)

# _handle_call_function line 1222:
return call_resolver.resolve_call(func_name, [a.value for a in args], inst, vm)

# _handle_call_method line 1270:
return call_resolver.resolve_method(obj_desc, method_name, [a.value for a in args], inst, vm)

# _handle_call_method line 1309:
return call_resolver.resolve_method(type_hint, method_name, [a.value for a in args], inst, vm)
```

**`_handle_call_unknown` line 1362-1363:**
```python
# Before:
target_desc = _symbolic_name(target_val)
return call_resolver.resolve_call(target_desc, args, inst, vm)
# After:
target_desc = _symbolic_name(target_val.value)
return call_resolver.resolve_call(target_desc, [a.value for a in args], inst, vm)
```

The `UnresolvedCallResolver` interface signatures remain `list[Any]` — unchanged.

### 12. `_handle_call_method` — FUNC_REF dispatch and reasoning

**FUNC_REF dispatch (line 1242-1246):** `_parse_func_ref(obj_val)` where `obj_val` is now TypedValue. `_parse_func_ref` expects a raw string. Unwrap both the check and the call:
```python
# Before:
func_ref = _parse_func_ref(obj_val)
if func_ref.matched:
    return _try_user_function_call(
        obj_val, args, inst, vm, cfg, registry, current_label
    )
# After:
func_ref = _parse_func_ref(obj_val.value)
if func_ref.matched:
    return _try_user_function_call(
        obj_val.value, args, inst, vm, cfg, registry, current_label
    )
```
`_try_user_function_call` receives raw `func_val` string (for `_parse_func_ref`) and `list[TypedValue]` args.

Same for `_heap_addr(obj_val)` at line 1262:
```python
addr = _heap_addr(obj_val.value)
```

And `_symbolic_name(obj_val)` at line 1269:
```python
obj_desc = _symbolic_name(obj_val.value)
```

**Method builtin reasoning (line 1258):**
```python
# Before:
reasoning=f"method builtin {method_name}({obj_val!r}, {args}) = {result.value!r}",
# After:
reasoning=f"method builtin {method_name}({obj_val.value!r}, {[a.value for a in args]}) = {result.value!r}",
```

**Method call dispatch reasoning (line 1330-1333):**
```python
# Before:
f"({', '.join(repr(a) for a in args)}),"
# After:
f"({', '.join(repr(a.value) for a in args)}),"
```

### 13. `_handle_call_function` — scope chain lookup and reasoning

**Scope chain lookup (line 1160):** `func_val = f.local_vars[func_name].value` — already unwraps `.value` from the stored TypedValue. No change needed.

**`_parse_func_ref`/`_parse_class_ref` calls** in `_try_class_constructor_call` (line 975) and `_try_user_function_call` (line 1055): these receive `func_val` which is already raw (unwrapped at line 1160). No change needed.

**Constructor reasoning (line 1037):**
```python
# Before:
f"({', '.join(repr(a) for a in args)}) → {addr},"
# After:
f"({', '.join(repr(a.value) for a in args)}) → {addr},"
```

**User function reasoning (line 1099-1101):**
```python
# Before:
f"({', '.join(repr(a) for a in args)}),"
# After:
f"({', '.join(repr(a.value) for a in args)}),"
```

### 14. `_handle_call_unknown` — FUNC_REF dispatch

**`_parse_func_ref(target_val)`** — `target_val` is now TypedValue:
```python
# Before:
user_result = _try_user_function_call(target_val, args, ...)
# After:
user_result = _try_user_function_call(target_val.value, args, ...)
```

`_try_user_function_call` receives `func_val` as raw string and `args` as `list[TypedValue]`.

### 15. BYTE_BUILTINS

All 25 byte builtins in `interpreter/cobol/byte_builtins.py` follow the same three-pattern migration:

**Pattern A — symbolic guard** (all 25 builtins):
```python
# Before:
if any(_is_symbolic(a) for a in args):
# After:
if any(_is_symbolic(a.value) for a in args):
```

**Pattern B — positional arg destructure** (all 22 builtins):
```python
# Before:
byte_val, position = args[0], args[1]
# After:
byte_val, position = args[0].value, args[1].value
```
Number of args varies per builtin (2-5), but all follow the same `args[N]` → `args[N].value` pattern.

**Pattern C — isinstance checks** (all 22 builtins):
```python
# Before:
if not isinstance(byte_val, int) or not isinstance(position, str):
```
These check the already-destructured local variables (`byte_val`, `position`, etc.), which are raw values after Pattern B. No change needed for isinstance checks — they operate on the unwrapped locals.

No byte builtin needs type information — the change is purely for interface consistency. Signatures change from `list[Any]` to `list[TypedValue]`.

### 16. Internal helper signatures

`_try_user_function_call`, `_try_class_constructor_call`, and `_handle_call_unknown` receive `args: list[TypedValue]` after the migration. Their type annotations should be updated from `list[Any]` to `list[TypedValue]` for internal consistency.

## What stays the same

- `BuiltinResult` structure — unchanged.
- `Builtins.TABLE` and `METHOD_TABLE` structure — unchanged.
- Return value wrapping in `_try_builtin_call` (`typed_from_runtime(result.value)`) — unchanged.
- `BuiltinResult.value` remains `Any` — type-preserving returns are a follow-up.
- `OverloadResolver`, `ResolutionStrategy`, `TypeCompatibility` interfaces — **updated to `list[TypedValue]`** (see `2026-03-13-overload-resolution-typedvalue-design.md`).
- `UnresolvedCallResolver` interface — unchanged (`list[Any]`).
- `_slice_heap_array` — internal, receives `HeapObject`, not args. Unaffected.

## Testing

- Update all existing builtin unit tests to pass `TypedValue` args (via `typed_from_runtime`).
- Update IOProvider unit tests to pass `TypedValue` args.
- Update method builtin tests to pass `TypedValue` obj.
- Integration tests via `run()` verify end-to-end behavior unchanged (11,530+ tests).

## Follow-up

- Type-preserving returns: builtins that can determine output type from input types (e.g., `abs(INT) → INT`) return `TypedValue` in `BuiltinResult.value` instead of raw values.
- Remove `_builtin_array_of` isinstance guard once all internal callers pass TypedValue.
- Migrate `UnresolvedCallResolver` interface to `list[TypedValue]`.
- Migrate `OverloadResolver` interface to `list[TypedValue]`.
