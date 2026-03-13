# Builtins TypedValue Args Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all builtins from receiving `list[Any]` args to `list[TypedValue]` args, closing the type system hole at the builtin calling boundary.

**Architecture:** Switch three call-site entry points in executor.py from `_resolve_reg` (unwraps TypedValue) to `_resolve_binop_operand` (preserves TypedValue). All downstream consumers (builtins, param binding, overload resolver, call resolver, IOProvider) then unwrap `.value` where they need raw values.

**Tech Stack:** Python 3.13+, pytest, black

**Spec:** `docs/superpowers/specs/2026-03-13-builtin-typedvalue-args-design.md`

**Critical constraint:** Builtins and executor MUST change atomically — intermediate commits where builtins expect TypedValue but executor still passes raw values will break all 11,530+ integration tests. All production code changes happen without committing; the single commit occurs after the full test suite passes in Task 6.

---

## Chunk 1: Builtins migration (no commits — verification via unit tests only)

### Task 1: Migrate pure builtins to `list[TypedValue]` args

**Files:**
- Modify: `interpreter/builtins.py` (lines 20-109 — 10 pure builtins)
- Modify: `tests/unit/test_pure_builtins_result.py`
- Modify: `tests/unit/test_builtin_len_array.py`
- Modify: `tests/unit/test_builtins.py` (TestBuiltinPrint)

**Do NOT commit after this task.** Unit tests verify correctness; integration tests will fail until Task 5 completes.

- [ ] **Step 1: Migrate pure builtins in builtins.py**

Update all 10 pure builtins in `interpreter/builtins.py`. For each, change the signature from `list[Any]` to `list[TypedValue]` and unwrap `.value` at every access point.

**`_builtin_len`** — signature + 1 unwrap:
```python
def _builtin_len(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if not args:
        return BuiltinResult(value=_UNCOMPUTABLE)
    val = args[0].value
    addr = _heap_addr(val)
    if addr and addr in vm.heap:
        fields = vm.heap[addr].fields
        if "length" in fields:
            return BuiltinResult(value=fields["length"].value)
        return BuiltinResult(value=len(fields))
    if isinstance(val, (list, tuple, str)):
        return BuiltinResult(value=len(val))
    return BuiltinResult(value=_UNCOMPUTABLE)
```

**`_builtin_range`** — signature + 2 unwraps:
```python
def _builtin_range(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    concrete = [a.value for a in args]
    if len(concrete) == 1:
        return BuiltinResult(value=list(range(int(concrete[0]))))
    if len(concrete) == 2:
        return BuiltinResult(value=list(range(int(concrete[0]), int(concrete[1]))))
    if len(concrete) == 3:
        return BuiltinResult(
            value=list(range(int(concrete[0]), int(concrete[1]), int(concrete[2])))
        )
    return BuiltinResult(value=_UNCOMPUTABLE)
```

**`_builtin_print`** — signature + 1 unwrap:
```python
def _builtin_print(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    logger.info("[VM print] %s", " ".join(str(a.value) for a in args))
    return BuiltinResult(value=None)
```

**`_builtin_int`** — signature + 2 unwraps:
```python
def _builtin_int(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if args and not _is_symbolic(args[0].value):
        try:
            return BuiltinResult(value=int(args[0].value))
        except (ValueError, TypeError):
            pass
    return BuiltinResult(value=_UNCOMPUTABLE)
```

**`_builtin_float`** — same pattern as `_builtin_int`: `args[0]` → `args[0].value` in `_is_symbolic` check and `float()` call.

**`_builtin_str`** — same pattern: `args[0]` → `args[0].value` in `_is_symbolic` check and `str()` call.

**`_builtin_bool`** — same pattern: `args[0]` → `args[0].value` in `_is_symbolic` check and `bool()` call.

**`_builtin_abs`** — same pattern: `args[0]` → `args[0].value` in `_is_symbolic` check and `abs()` call.

**`_builtin_max`** — signature + 2 unwraps:
```python
def _builtin_max(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if all(not _is_symbolic(a.value) for a in args):
        try:
            return BuiltinResult(value=max(a.value for a in args))
        except (ValueError, TypeError):
            pass
    return BuiltinResult(value=_UNCOMPUTABLE)
```

**`_builtin_min`** — same pattern as `_builtin_max`: unwrap in `_is_symbolic` check and `min()` call.

- [ ] **Step 2: Update unit tests to pass TypedValue args**

All direct builtin calls in test files must wrap raw args via `typed_from_runtime()`. Apply to EVERY call site in each file — the patterns below show representative examples, apply to all calls.

`tests/unit/test_pure_builtins_result.py` — add `from interpreter.typed_value import typed_from_runtime` to imports. Wrap every call:
```python
# Before:
result = _builtin_len(["arr_0"], vm)
result = _builtin_range([3], vm)
result = _builtin_print(["hello"], vm)
result = _builtin_int(["42"], vm)
result = _builtin_float(["3.14"], vm)
result = _builtin_str([42], vm)
result = _builtin_bool([1], vm)
result = _builtin_abs([-5], vm)
result = _builtin_max([1, 5, 3], vm)
result = _builtin_min([1, 5, 3], vm)
result = _builtin_len([], vm)  # empty args — no change

# After:
result = _builtin_len([typed_from_runtime("arr_0")], vm)
result = _builtin_range([typed_from_runtime(3)], vm)
result = _builtin_print([typed_from_runtime("hello")], vm)
result = _builtin_int([typed_from_runtime("42")], vm)
result = _builtin_float([typed_from_runtime("3.14")], vm)
result = _builtin_str([typed_from_runtime(42)], vm)
result = _builtin_bool([typed_from_runtime(1)], vm)
result = _builtin_abs([typed_from_runtime(-5)], vm)
result = _builtin_max([typed_from_runtime(1), typed_from_runtime(5), typed_from_runtime(3)], vm)
result = _builtin_min([typed_from_runtime(1), typed_from_runtime(5), typed_from_runtime(3)], vm)
```

`tests/unit/test_builtin_len_array.py` — file already imports `typed` from `typed_value`, add `typed_from_runtime` to that import. Update ALL 5 `_builtin_len` calls (lines 35, 43, 50, 64, 79) and ALL 3 `_builtin_array_of` calls (lines 33, 41, 49):
```python
# _builtin_len calls (5 total):
length = _builtin_len([typed_from_runtime(result.value)], vm)  # lines 35, 43, 50
result = _builtin_len([typed_from_runtime("obj_0")], vm)       # line 64
result = _builtin_len([typed_from_runtime("arr_0")], vm)       # line 79

# _builtin_array_of calls (3 total) — wrap each element:
result = _builtin_array_of([typed_from_runtime(10), typed_from_runtime(5), typed_from_runtime(3)], vm)  # line 33
result = _builtin_array_of([], vm)                                                                       # line 41
result = _builtin_array_of([typed_from_runtime(42)], vm)                                                 # line 49
```

`tests/unit/test_builtins.py` — file already imports `typed_from_runtime`. TestBuiltinPrint (3 calls):
```python
_builtin_print([typed_from_runtime("hello"), typed_from_runtime(42)], vm)  # lines 36, 42
_builtin_print([], vm)  # line 48 — empty, no change
```

- [ ] **Step 3: Run unit tests to verify**

Run: `poetry run python -m pytest tests/unit/test_pure_builtins_result.py tests/unit/test_builtin_len_array.py tests/unit/test_builtins.py::TestBuiltinPrint -v`
Expected: PASS

---

### Task 2: Migrate heap-mutating and delegating builtins to `list[TypedValue]` args

**Files:**
- Modify: `interpreter/builtins.py` (lines 112-265 — `_builtin_keys`, `_builtin_array_of`, `_builtin_slice`, `_builtin_object_rest`, `_method_slice`, `_arg_or_none`)
- Modify: `tests/unit/test_builtin_keys.py`
- Modify: `tests/unit/test_builtins.py` (TestBuiltinSlice, TestBuiltinObjectRest, TestMethodBuiltins)
- Modify: `tests/unit/test_array_of_builtin_result.py`
- Modify: `tests/unit/test_object_rest_builtin_result.py`
- Modify: `tests/unit/test_delegating_builtins_result.py`

**Do NOT commit after this task.**

**Dependency:** Task 2 depends on Task 1 (`_builtin_keys` delegates to `_builtin_array_of` which delegates to internal `typed_from_runtime`; `_builtin_slice` calls `_builtin_array_of`).

- [ ] **Step 1: Migrate heap-mutating and delegating builtins**

**`_builtin_keys`** — signature + 2 unwraps:
```python
def _builtin_keys(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if not args:
        return BuiltinResult(value=_UNCOMPUTABLE)
    val = args[0].value
    addr = _heap_addr(val)
    if not addr or addr not in vm.heap:
        return BuiltinResult(value=_UNCOMPUTABLE)
    field_names = [k for k in vm.heap[addr].fields if k != "length"]
    return _builtin_array_of(field_names, vm)
```

Note: `_builtin_keys` passes raw strings to `_builtin_array_of`. The isinstance guard in `_builtin_array_of` handles this — see below.

**`_builtin_array_of`** — signature changes but isinstance guard **retained**:
```python
def _builtin_array_of(args: list[TypedValue], vm: VMState) -> BuiltinResult:
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

The isinstance guard is retained because internal callers (`_builtin_keys`, `_builtin_slice`, `_slice_heap_array`) pass raw values. This also means the `arguments` injection in executor.py (lines 1070, 1319) works — it passes `list[TypedValue]` args which pass through the isinstance check.

**`_builtin_slice`** — signature + 4 unwraps:
```python
def _builtin_slice(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    collection = args[0].value
    raw_start, raw_stop, raw_step = (
        args[1].value,
        _arg_or_none_value(args, 2),
        _arg_or_none_value(args, 3),
    )
    start = _parse_slice_int(raw_start)
    stop = _parse_slice_int(raw_stop)
    step = _parse_slice_int(raw_step)
    py_slice = slice(start, stop, step)
    if isinstance(collection, (list, tuple)):
        return _builtin_array_of(list(collection[py_slice]), vm)
    addr = _heap_addr(collection)
    if addr and addr in vm.heap:
        return _slice_heap_array(vm.heap[addr], py_slice, vm)
    if isinstance(collection, str):
        return BuiltinResult(value=collection[py_slice])
    return BuiltinResult(value=_UNCOMPUTABLE)
```

**`_arg_or_none`** — rename to `_arg_or_none_value` and unwrap:
```python
def _arg_or_none_value(args: list[TypedValue], index: int) -> Any:
    """Return args[index].value if it exists, else None."""
    return args[index].value if index < len(args) else None
```

**`_builtin_object_rest`** — signature + 2 unwraps:
```python
def _builtin_object_rest(args: list[TypedValue], vm: VMState) -> BuiltinResult:
    if not args:
        return BuiltinResult(value=_UNCOMPUTABLE)
    obj_val = args[0].value
    excluded_keys = set(a.value for a in args[1:])
    addr = _heap_addr(obj_val)
    if not addr or addr not in vm.heap:
        return BuiltinResult(value=_UNCOMPUTABLE)
    source_fields = vm.heap[addr].fields
    rest_fields = {
        k: v for k, v in source_fields.items()
        if k not in excluded_keys and k != "length"
    }
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

**`_method_slice`** — signature only:
```python
def _method_slice(obj: TypedValue, args: list[TypedValue], vm: VMState) -> BuiltinResult:
    return _builtin_slice([obj, *args], vm)
```

- [ ] **Step 2: Update unit tests to pass TypedValue args**

Apply `typed_from_runtime()` wrapping to EVERY direct builtin call in each test file.

`tests/unit/test_builtin_keys.py` — 4 `Builtins.TABLE["keys"]` calls + 1 `_builtin_len` call:
```python
# All TABLE["keys"] calls (4 total, lines 40, 53, 69, 86):
result = Builtins.TABLE["keys"]([typed_from_runtime("obj_0")], vm)

# _builtin_len call (line 88):
length = _builtin_len([typed_from_runtime(keys_result.value)], vm)
```

`tests/unit/test_builtins.py` — TestBuiltinSlice (12 test methods, every `_builtin_slice` call):
```python
# Pattern — wrap each element:
result = _builtin_slice([typed_from_runtime([10, 20, 30, 40]), typed_from_runtime(1)], vm)
result = _builtin_slice([typed_from_runtime(addr), typed_from_runtime(1)], vm)
result = _builtin_slice([typed_from_runtime(42)], vm)
result = _builtin_slice([typed_from_runtime("hello"), typed_from_runtime(1), typed_from_runtime(3)], vm)
# Also wrap multi-arg variants: [collection, start, stop], [collection, start, stop, step]
# And "None" string args: typed_from_runtime("None")
# And negative starts: typed_from_runtime(-2)
```

TestBuiltinObjectRest (4 test methods, lines 200, 217, 225, 230):
```python
result = _builtin_object_rest([typed_from_runtime(addr), typed_from_runtime("a")], vm)
result = _builtin_object_rest([typed_from_runtime(addr), typed_from_runtime("x"), typed_from_runtime("y")], vm)
result = _builtin_object_rest([], vm)  # empty — no change
result = _builtin_object_rest([typed_from_runtime("not_a_heap_addr")], vm)
```

TestMethodBuiltins (3 test methods) — `obj` becomes TypedValue, args become `list[TypedValue]`:
```python
result = fn(typed_from_runtime(addr), [typed_from_runtime(1), typed_from_runtime(3)], vm)
result = fn(typed_from_runtime("hello"), [typed_from_runtime(1), typed_from_runtime(3)], vm)
```

`tests/unit/test_array_of_builtin_result.py` — all 7 `_builtin_array_of` calls. Add `typed_from_runtime` to imports:
```python
result = _builtin_array_of([typed_from_runtime(10), typed_from_runtime(20), typed_from_runtime(30)], vm)
result = _builtin_array_of([typed_from_runtime(10)], vm)
result = _builtin_array_of([], vm)  # empty — no change
_builtin_array_of([typed_from_runtime(1)], vm)
_builtin_array_of([typed_from_runtime(2)], vm)
```

`tests/unit/test_object_rest_builtin_result.py` — all 6 `_builtin_object_rest` calls:
```python
result = _builtin_object_rest([typed_from_runtime("obj_0"), typed_from_runtime("a")], vm)
result = _builtin_object_rest([], vm)  # empty — no change
result = _builtin_object_rest([typed_from_runtime("nonexistent_addr"), typed_from_runtime("a")], vm)
```

`tests/unit/test_delegating_builtins_result.py` — all call sites:
```python
result = _builtin_keys([], vm)  # empty — no change
result = _builtin_keys([typed_from_runtime("nonexistent")], vm)
result = _builtin_keys([typed_from_runtime("obj_0")], vm)
result = _builtin_slice([typed_from_runtime(1)], vm)
result = _builtin_slice([typed_from_runtime([10, 20, 30]), typed_from_runtime(0), typed_from_runtime(2)], vm)
result = _builtin_slice([typed_from_runtime("hello"), typed_from_runtime(1), typed_from_runtime(3)], vm)
result = _builtin_slice([typed_from_runtime("arr_0"), typed_from_runtime(0), typed_from_runtime(2)], vm)
result = _method_slice(typed_from_runtime([10, 20, 30]), [typed_from_runtime(0), typed_from_runtime(2)], vm)
```

- [ ] **Step 3: Run unit tests to verify**

Run: `poetry run python -m pytest tests/unit/test_builtin_keys.py tests/unit/test_builtins.py::TestBuiltinSlice tests/unit/test_builtins.py::TestBuiltinObjectRest tests/unit/test_builtins.py::TestMethodBuiltins tests/unit/test_array_of_builtin_result.py tests/unit/test_object_rest_builtin_result.py tests/unit/test_delegating_builtins_result.py -v`
Expected: PASS

---

## Chunk 2: Byte builtins and IOProvider (no commits)

### Task 3: Migrate BYTE_BUILTINS to `list[TypedValue]` args

**Files:**
- Modify: `interpreter/cobol/byte_builtins.py` (all 25 builtins)
- Modify: `tests/unit/test_byte_builtins.py`
- Modify: `tests/unit/test_byte_builtins_result.py`

**Do NOT commit after this task.**

- [ ] **Step 1: Migrate all 25 byte builtins**

Apply three patterns mechanically to all 25 builtins in `interpreter/cobol/byte_builtins.py`:

**Pattern A — signature:** Change `args: list[Any]` to `args: list[TypedValue]`.

**Pattern B — symbolic guard:** Change `_is_symbolic(a)` to `_is_symbolic(a.value)`.

**Pattern C — positional destructure:** Change `args[N]` to `args[N].value`.

Add `from interpreter.typed_value import TypedValue` to imports.

Example transformation for `_builtin_nibble_get`:
```python
# Before:
def _builtin_nibble_get(args: list[Any], vm: Any) -> BuiltinResult:
    if len(args) < 2 or any(_is_symbolic(a) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    byte_val, position = args[0], args[1]

# After:
def _builtin_nibble_get(args: list[TypedValue], vm: Any) -> BuiltinResult:
    if len(args) < 2 or any(_is_symbolic(a.value) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    byte_val, position = args[0].value, args[1].value
```

Apply identically to all 25 builtins. The isinstance checks and arithmetic after destructure operate on the already-unwrapped local variables — no change needed for those.

The 25 builtins are: `_builtin_nibble_get`, `_builtin_nibble_set`, `_builtin_byte_from_int`, `_builtin_int_from_byte`, `_builtin_bytes_to_string`, `_builtin_string_to_bytes`, `_builtin_list_get`, `_builtin_list_set`, `_builtin_list_len`, `_builtin_list_slice`, `_builtin_list_concat`, `_builtin_make_list`, `_builtin_cobol_prepare_digits`, `_builtin_cobol_prepare_sign`, `_builtin_string_find`, `_builtin_string_split`, `_builtin_string_count`, `_builtin_string_replace`, `_builtin_string_concat`, `_builtin_string_concat_pair`, `_builtin_int_to_binary_bytes`, `_builtin_binary_bytes_to_int`, `_builtin_float_to_bytes`, `_builtin_bytes_to_float`, `_builtin_cobol_blank_when_zero`.

- [ ] **Step 2: Update unit tests to pass TypedValue args**

`tests/unit/test_byte_builtins.py` — add `from interpreter.typed_value import typed_from_runtime` to imports. Wrap EVERY direct builtin call argument with `typed_from_runtime()`:

```python
# Before:
assert _builtin_nibble_get([0xAB, "high"], None).value == 0x0A

# After:
assert _builtin_nibble_get([typed_from_runtime(0xAB), typed_from_runtime("high")], None).value == 0x0A
```

For `SymbolicValue` args:
```python
# Before:
sym = SymbolicValue(name="x")
assert _builtin_nibble_get([sym, "high"], None).value is _UNCOMPUTABLE

# After:
sym = SymbolicValue(name="x")
assert _builtin_nibble_get([typed_from_runtime(sym), typed_from_runtime("high")], None).value is _UNCOMPUTABLE
```

Apply to ALL test calls across all test classes in the file.

`tests/unit/test_byte_builtins_result.py` — same pattern. Add `typed_from_runtime` import and wrap all 11 test method call sites.

- [ ] **Step 3: Run unit tests to verify**

Run: `poetry run python -m pytest tests/unit/test_byte_builtins.py tests/unit/test_byte_builtins_result.py -v`
Expected: PASS

---

### Task 4: Migrate IOProvider to `list[TypedValue]` args

**Files:**
- Modify: `interpreter/cobol/io_provider.py` (line 47 — `handle_call` signature + unwrap)
- Modify: `tests/unit/test_cobol_io_provider.py`

**Do NOT commit after this task.**

- [ ] **Step 1: Update `handle_call` to accept and unwrap TypedValue args**

`interpreter/cobol/io_provider.py` — add `from interpreter.typed_value import TypedValue` to imports. Change `handle_call`:
```python
def handle_call(self, func_name: str, args: list[TypedValue]) -> Any:
    method_name = _COBOL_IO_DISPATCH.get(func_name)
    if method_name is None:
        logger.debug("CobolIOProvider: unknown func %s", func_name)
        return _UNCOMPUTABLE
    method = getattr(self, method_name)
    return method(*[a.value for a in args])
```

- [ ] **Step 2: Update unit tests to pass TypedValue args**

`tests/unit/test_cobol_io_provider.py` — add `from interpreter.typed_value import typed_from_runtime` to imports. Wrap ALL 27 `handle_call` arg lists. Calls with empty args `[]` need no change.

```python
# Before:
provider.handle_call("__cobol_accept", ["CONSOLE"])
provider.handle_call("__cobol_open_file", ["F1", "INPUT"])
provider.handle_call("__cobol_write_record", ["OUT-FILE", "DATA1"])
provider.handle_call("__cobol_bogus", [])  # empty — no change

# After:
provider.handle_call("__cobol_accept", [typed_from_runtime("CONSOLE")])
provider.handle_call("__cobol_open_file", [typed_from_runtime("F1"), typed_from_runtime("INPUT")])
provider.handle_call("__cobol_write_record", [typed_from_runtime("OUT-FILE"), typed_from_runtime("DATA1")])
provider.handle_call("__cobol_bogus", [])  # empty — no change
```

Apply to ALL 27 `handle_call` invocations in the file. Most have 1-2 args that need wrapping. Empty-arg calls (`[]`) at lines 59 and 120 stay unchanged.

- [ ] **Step 3: Run unit tests to verify**

Run: `poetry run python -m pytest tests/unit/test_cobol_io_provider.py -v`
Expected: PASS

---

## Chunk 3: Executor call sites — the big switch (single atomic commit)

### Task 5: Switch executor call sites from `_resolve_reg` to `_resolve_binop_operand` and update all downstream unwrap points

This is the keystone task. All builtins now accept `list[TypedValue]`, so we switch the three entry points and update every downstream consumer in executor.py.

**Files:**
- Modify: `interpreter/executor.py`

- [ ] **Step 1: Switch the three call-site entry points**

`_handle_call_function` (line 1126):
```python
# Before:
args = [_resolve_reg(vm, a) for a in arg_regs]
# After:
args = [_resolve_binop_operand(vm, a) for a in arg_regs]
```

`_handle_call_method` (lines 1236, 1239):
```python
# Before:
obj_val = _resolve_reg(vm, inst.operands[0])
args = [_resolve_reg(vm, a) for a in arg_regs]
# After:
obj_val = _resolve_binop_operand(vm, inst.operands[0])
args = [_resolve_binop_operand(vm, a) for a in arg_regs]
```

`_handle_call_unknown` (lines 1351, 1353):
```python
# Before:
target_val = _resolve_reg(vm, inst.operands[0])
args = [_resolve_reg(vm, a) for a in arg_regs]
# After:
target_val = _resolve_binop_operand(vm, inst.operands[0])
args = [_resolve_binop_operand(vm, a) for a in arg_regs]
```

Add `_resolve_binop_operand` to the import from `interpreter.vm` if not already present.

- [ ] **Step 2: Update `_try_builtin_call` reasoning strings**

Lines 941, 956-958:
```python
# UNCOMPUTABLE path:
args_desc = ", ".join(_symbolic_name(a.value) for a in args)

# Success path:
reasoning=(
    f"builtin {func_name}"
    f"({', '.join(repr(a.value) for a in args)}) = {result.value!r}"
),
```

- [ ] **Step 3: Update `_handle_call_function` downstream consumers**

IOProvider reasoning (line 1139):
```python
reasoning=f"io_provider {func_name}({[a.value for a in args]!r}) = {result!r}",
```

Scala-style apply (line 1167):
```python
if len(args) == 1 and isinstance(args[0].value, int):
    ...
    idx_key = str(args[0].value)
    ...
    reasoning=f"heap call-index {func_name}({args[0].value}) = {tv!r}",
```

Native indexing (lines 1189, 1191, 1195):
```python
and isinstance(args[0].value, int)
element = func_val[args[0].value]
reasoning=f"native call-index {func_name}({args[0].value}) = {element!r}",
```

Call resolver unwrap (lines 1164, 1222):
```python
return call_resolver.resolve_call(func_name, [a.value for a in args], inst, vm)
```

Overload resolver unwrap (line 990):
```python
winner = overload_resolver.resolve(sigs, [a.value for a in args])
```

- [ ] **Step 4: Update `_try_class_constructor_call` param binding**

Lines 1016-1024 — remove `typed_from_runtime` wrapping (both Python-style and Java-style):
```python
# Python-style (line 1018):
new_vars[params[i + 1]] = arg    # was: typed_from_runtime(arg)

# Java-style (line 1024):
new_vars[params[i]] = arg        # was: typed_from_runtime(arg)
```

Constructor reasoning (line 1037):
```python
f"({', '.join(repr(a.value) for a in args)}) → {addr},"
```

- [ ] **Step 5: Update `_try_user_function_call` param binding**

Lines 1064-1068 — remove `typed_from_runtime`:
```python
param_vars = {
    params[i]: arg
    for i, arg in enumerate(args)
    if i < len(params)
}
```

User function reasoning (lines 1099-1101):
```python
f"({', '.join(repr(a.value) for a in args)}),"
```

- [ ] **Step 6: Update `_handle_call_method` downstream consumers**

FUNC_REF dispatch (lines 1242-1246) — unwrap both the `_parse_func_ref` check AND the `_try_user_function_call` call:
```python
func_ref = _parse_func_ref(obj_val.value)
if func_ref.matched:
    return _try_user_function_call(
        obj_val.value, args, inst, vm, cfg, registry, current_label
    )
```

Method builtin reasoning (line 1258):
```python
reasoning=f"method builtin {method_name}({obj_val.value!r}, {[a.value for a in args]}) = {result.value!r}",
```

`_heap_addr` and `_symbolic_name` (lines 1262, 1269):
```python
addr = _heap_addr(obj_val.value)
obj_desc = _symbolic_name(obj_val.value)
```

Call resolver unwrap (lines 1270, 1309):
```python
return call_resolver.resolve_method(obj_desc, method_name, [a.value for a in args], inst, vm)
return call_resolver.resolve_method(type_hint, method_name, [a.value for a in args], inst, vm)
```

Overload resolver unwrap (lines 1282, 1302):
```python
winner = overload_resolver.resolve(sigs, [a.value for a in args])
```

Param binding (lines 1314-1317) — remove `typed_from_runtime`:
```python
new_vars[params[0]] = obj_val    # was: typed_from_runtime(obj_val)
new_vars[params[i + 1]] = arg   # was: typed_from_runtime(arg)
```

Method reasoning (lines 1330-1333):
```python
f"({', '.join(repr(a.value) for a in args)}),"
```

- [ ] **Step 7: Update `_handle_call_unknown` downstream consumers**

FUNC_REF dispatch (line 1356) — pass unwrapped `target_val.value`:
```python
user_result = _try_user_function_call(
    target_val.value, args, inst, vm, cfg, registry, current_label
)
```

Call resolver unwrap (lines 1362-1363):
```python
target_desc = _symbolic_name(target_val.value)
return call_resolver.resolve_call(target_desc, [a.value for a in args], inst, vm)
```

- [ ] **Step 8: Update internal helper type annotations**

Change signatures from `list[Any]` to `list[TypedValue]` for:
- `_try_builtin_call` (line 932)
- `_try_class_constructor_call` (line 965)
- `_try_user_function_call` (line 1047)

Add `TypedValue` to imports from `interpreter.typed_value` if not already present.

- [ ] **Step 9: Run the full test suite**

Run: `poetry run python -m pytest -x -q`
Expected: ALL tests pass (11,530+). If failures occur, debug and fix before proceeding.

---

## Chunk 4: Verification, commit, and cleanup

### Task 6: Full verification, atomic commit, and push

**Files:**
- All modified files from Tasks 1-5
- Modify: `README.md`

- [ ] **Step 1: Run full test suite (final verification)**

Run: `poetry run python -m pytest -x -q`
Expected: ALL tests pass. Record exact count.

- [ ] **Step 2: Verify migration completeness**

Verify no `_resolve_reg` remains in call handlers:
```bash
grep -n "_resolve_reg" interpreter/executor.py
```
Confirm `_handle_call_function`, `_handle_call_method`, and `_handle_call_unknown` no longer use `_resolve_reg`. It should only remain in non-call paths (LOAD_VAR, STORE_VAR, BINOP, etc.).

Verify no `typed_from_runtime(arg)` or `typed_from_runtime(obj_val)` remains in param binding:
```bash
grep -n "typed_from_runtime(arg)" interpreter/executor.py
grep -n "typed_from_runtime(obj_val)" interpreter/executor.py
```
Expected: No matches — all param binding now uses TypedValue directly.

- [ ] **Step 3: Format all code**

```bash
poetry run python -m black .
```

- [ ] **Step 4: Atomic commit — all production and test changes together**

```bash
git add interpreter/builtins.py interpreter/cobol/byte_builtins.py interpreter/cobol/io_provider.py interpreter/executor.py tests/unit/test_pure_builtins_result.py tests/unit/test_builtin_len_array.py tests/unit/test_builtins.py tests/unit/test_builtin_keys.py tests/unit/test_array_of_builtin_result.py tests/unit/test_object_rest_builtin_result.py tests/unit/test_delegating_builtins_result.py tests/unit/test_byte_builtins.py tests/unit/test_byte_builtins_result.py tests/unit/test_cobol_io_provider.py
git commit -m "feat: migrate builtins to receive list[TypedValue] args (red-dragon-x9r)"
```

- [ ] **Step 5: Update README and commit**

Add a line noting the TypedValue args migration to the README changelog section.

```bash
poetry run python -m black .
git add README.md
git commit -m "docs: update README for TypedValue args migration"
```

- [ ] **Step 6: Push to main**

```bash
git push origin main
```
