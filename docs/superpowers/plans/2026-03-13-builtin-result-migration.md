# BuiltinResult Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** All builtins return `BuiltinResult(value, new_objects, heap_writes)` — no builtin directly mutates `vm.heap`.

**Architecture:** Add `BuiltinResult` dataclass to `vm_types.py`. Migrate builtins bottom-up: pure first, then heap-mutating, then delegating. Bridge callers with isinstance during migration, remove bridge at end.

**Tech Stack:** Python 3.13, pytest, dataclasses

**Spec:** `docs/superpowers/specs/2026-03-13-builtin-result-migration-design.md`

---

## Chunk 1: Foundation + Pure Builtins

### Task 1: Add `BuiltinResult` dataclass

**Files:**
- Modify: `interpreter/vm_types.py` (add dataclass after `NewObject`)
- Test: `tests/unit/test_builtin_result.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_builtin_result.py
"""Unit tests for BuiltinResult dataclass."""

from interpreter.vm_types import BuiltinResult, NewObject, HeapWrite


class TestBuiltinResult:
    def test_pure_result_has_empty_side_effects(self):
        result = BuiltinResult(value=42)
        assert result.value == 42
        assert result.new_objects == []
        assert result.heap_writes == []

    def test_result_with_new_objects(self):
        obj = NewObject(addr="arr_0", type_hint="array")
        result = BuiltinResult(value="arr_0", new_objects=[obj])
        assert result.new_objects == [obj]
        assert result.heap_writes == []

    def test_result_with_heap_writes(self):
        from interpreter.typed_value import typed_from_runtime

        hw = HeapWrite(obj_addr="arr_0", field="0", value=typed_from_runtime(10))
        result = BuiltinResult(value="arr_0", heap_writes=[hw])
        assert result.heap_writes[0].field == "0"

    def test_result_with_all_fields(self):
        from interpreter.typed_value import typed_from_runtime

        obj = NewObject(addr="arr_0", type_hint="array")
        hw = HeapWrite(obj_addr="arr_0", field="length", value=typed_from_runtime(1))
        result = BuiltinResult(
            value="arr_0", new_objects=[obj], heap_writes=[hw]
        )
        assert result.value == "arr_0"
        assert len(result.new_objects) == 1
        assert len(result.heap_writes) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_builtin_result.py -v`
Expected: FAIL with `ImportError: cannot import name 'BuiltinResult'`

- [ ] **Step 3: Write minimal implementation**

Add to `interpreter/vm_types.py` after `NewObject`:

```python
@dataclass
class BuiltinResult:
    """Uniform return type for all builtins.

    Pure builtins return BuiltinResult(value=...) with empty side-effect lists.
    Heap-mutating builtins express mutations as new_objects + heap_writes.
    """

    value: Any
    new_objects: list[NewObject] = field(default_factory=list)
    heap_writes: list[HeapWrite] = field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_builtin_result.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add interpreter/vm_types.py tests/unit/test_builtin_result.py
git commit -m "feat: add BuiltinResult dataclass to vm_types"
```

---

### Task 2: Bridge callers to handle both raw and BuiltinResult

**Files:**
- Modify: `interpreter/executor.py:929-958` (`_try_builtin_call`)
- Modify: `interpreter/executor.py:1243-1253` (METHOD_TABLE dispatch)
- Test: existing integration tests (no new tests — this is a transparent bridge)

The bridge lets us migrate builtins one at a time without breaking anything. Each caller checks `isinstance(result, BuiltinResult)` and unwraps accordingly. This isinstance is temporary — removed in Task 8.

- [ ] **Step 1: Add BuiltinResult import to executor.py**

Add `BuiltinResult` to the existing `from interpreter.vm_types import ...` line in executor.py.

- [ ] **Step 2: Update `_try_builtin_call` with bridge**

```python
def _try_builtin_call(
    func_name: str,
    args: list[Any],
    inst: IRInstruction,
    vm: VMState,
) -> ExecutionResult:
    """Attempt to handle a call via the builtin table."""
    if func_name not in Builtins.TABLE:
        return ExecutionResult.not_handled()
    raw = Builtins.TABLE[func_name](args, vm)
    # Bridge: handle both BuiltinResult (migrated) and raw values (not yet migrated)
    if isinstance(raw, BuiltinResult):
        if raw.value is Operators.UNCOMPUTABLE:
            args_desc = ", ".join(_symbolic_name(a) for a in args)
            sym = vm.fresh_symbolic(hint=f"{func_name}({args_desc})")
            sym.constraints = [f"{func_name}({args_desc})"]
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: typed(sym, UNKNOWN)},
                    reasoning=f"builtin {func_name}({args_desc}) → symbolic {sym.name} (uncomputable)",
                )
            )
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: typed_from_runtime(raw.value)},
                new_objects=raw.new_objects,
                heap_writes=raw.heap_writes,
                reasoning=(
                    f"builtin {func_name}"
                    f"({', '.join(repr(a) for a in args)}) = {raw.value!r}"
                ),
            )
        )
    # Legacy path: raw return value (pre-migration builtins)
    result = raw
    if result is Operators.UNCOMPUTABLE:
        args_desc = ", ".join(_symbolic_name(a) for a in args)
        sym = vm.fresh_symbolic(hint=f"{func_name}({args_desc})")
        sym.constraints = [f"{func_name}({args_desc})"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"builtin {func_name}({args_desc}) → symbolic {sym.name} (uncomputable)",
            )
        )
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: typed_from_runtime(result)},
            reasoning=(
                f"builtin {func_name}"
                f"({', '.join(repr(a) for a in args)}) = {result!r}"
            ),
        )
    )
```

- [ ] **Step 3: Update METHOD_TABLE dispatch with bridge**

```python
    method_fn = Builtins.METHOD_TABLE.get(method_name)
    if method_fn is not None:
        raw = method_fn(obj_val, args, vm)
        if isinstance(raw, BuiltinResult):
            if raw.value is not Operators.UNCOMPUTABLE:
                return ExecutionResult.success(
                    StateUpdate(
                        register_writes={inst.result_reg: typed_from_runtime(raw.value)},
                        new_objects=raw.new_objects,
                        heap_writes=raw.heap_writes,
                        reasoning=f"method builtin {method_name}({obj_val!r}, {args}) = {raw.value!r}",
                    )
                )
        elif raw is not Operators.UNCOMPUTABLE:
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: typed_from_runtime(raw)},
                    reasoning=f"method builtin {method_name}({obj_val!r}, {args}) = {raw!r}",
                )
            )
```

- [ ] **Step 4: Run full test suite to verify bridge is transparent**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass (11,274+), no behavior change

- [ ] **Step 5: Commit**

```bash
git add interpreter/executor.py
git commit -m "feat: add BuiltinResult bridge in executor callers"
```

---

### Task 3: Migrate pure builtins to BuiltinResult

**Files:**
- Modify: `interpreter/builtins.py` (10 pure builtins)
- Modify: `interpreter/builtins.py` imports (add BuiltinResult)
- Test: `tests/unit/test_pure_builtins_result.py`
- Modify: `tests/unit/test_builtin_len_array.py` (unwrap `.value`)

Pure builtins: `_builtin_len`, `_builtin_range`, `_builtin_print`, `_builtin_int`, `_builtin_float`, `_builtin_str`, `_builtin_bool`, `_builtin_abs`, `_builtin_max`, `_builtin_min`.

- [ ] **Step 1: Write failing tests for pure builtins returning BuiltinResult**

```python
# tests/unit/test_pure_builtins_result.py
"""Unit tests verifying pure builtins return BuiltinResult with empty side-effect lists."""

from interpreter.builtins import (
    _builtin_len,
    _builtin_range,
    _builtin_print,
    _builtin_int,
    _builtin_float,
    _builtin_str,
    _builtin_bool,
    _builtin_abs,
    _builtin_max,
    _builtin_min,
)
from interpreter.vm import VMState, Operators
from interpreter.vm_types import BuiltinResult, HeapObject
from interpreter.typed_value import typed
from interpreter.type_expr import scalar
from interpreter.constants import TypeName


class TestPureBuiltinsReturnBuiltinResult:
    def test_len_returns_builtin_result(self):
        vm = VMState()
        vm.heap["arr_0"] = HeapObject(
            type_hint="array",
            fields={
                "0": typed(10, scalar(TypeName.INT)),
                "length": typed(1, scalar(TypeName.INT)),
            },
        )
        result = _builtin_len(["arr_0"], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 1
        assert result.new_objects == []
        assert result.heap_writes == []

    def test_range_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_range([3], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == [0, 1, 2]
        assert result.new_objects == []

    def test_print_returns_builtin_result_with_none(self):
        vm = VMState()
        result = _builtin_print(["hello"], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is None

    def test_int_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_int(["42"], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 42

    def test_float_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_float(["3.14"], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 3.14

    def test_str_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_str([42], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == "42"

    def test_bool_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_bool([1], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is True

    def test_abs_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_abs([-5], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 5

    def test_max_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_max([1, 5, 3], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 5

    def test_min_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_min([1, 5, 3], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == 1

    def test_uncomputable_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_len([], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_pure_builtins_result.py -v`
Expected: FAIL — builtins return raw values, not BuiltinResult

- [ ] **Step 3: Migrate all 10 pure builtins**

Add `BuiltinResult` import to builtins.py:
```python
from interpreter.vm_types import HeapObject, BuiltinResult
```

Change each pure builtin's return statements from `return value` to `return BuiltinResult(value=value)`. Example for `_builtin_len`:

```python
def _builtin_len(args: list[Any], vm: VMState) -> BuiltinResult:
    if not args:
        return BuiltinResult(value=_UNCOMPUTABLE)
    val = args[0]
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

Apply same pattern to: `_builtin_range`, `_builtin_print`, `_builtin_int`, `_builtin_float`, `_builtin_str`, `_builtin_bool`, `_builtin_abs`, `_builtin_max`, `_builtin_min`.

Return type annotation changes from `-> Any` to `-> BuiltinResult`.

- [ ] **Step 4: Update test_builtin_len_array.py to unwrap .value**

Tests call `_builtin_len` and `_builtin_array_of` directly. `_builtin_len` now returns `BuiltinResult`, so unwrap `.value`:

```python
# In each test that calls _builtin_len directly:
result = _builtin_len([addr], vm)
# Before: assert result == 3
# After:  assert result.value == 3
```

Note: `_builtin_array_of` is NOT migrated yet (Task 4), so those calls still return raw addresses. Only `_builtin_len` calls need `.value` unwrapping.

- [ ] **Step 5: Update test_builtin_keys.py to unwrap _builtin_len .value**

`test_len_of_keys_result` calls `_builtin_len([keys_addr], vm)` and asserts `length == 3`. After this task, `_builtin_len` returns `BuiltinResult`, so unwrap:

```python
def test_len_of_keys_result(self):
    vm = VMState()
    vm.heap["obj_0"] = HeapObject(
        type_hint="object",
        fields={
            k: typed_from_runtime(v) for k, v in {"x": 1, "y": 2, "z": 3}.items()
        },
    )
    keys_addr = Builtins.TABLE["keys"](["obj_0"], vm)
    length = _builtin_len([keys_addr], vm)
    assert length.value == 3
```

- [ ] **Step 6: Run tests to verify**

Run: `poetry run python -m pytest tests/unit/test_pure_builtins_result.py tests/unit/test_builtin_len_array.py tests/unit/test_builtin_keys.py -v`
Expected: All pass

- [ ] **Step 7: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All 11,274+ tests pass (bridge in executor handles BuiltinResult)

- [ ] **Step 8: Commit**

```bash
git add interpreter/builtins.py tests/unit/test_pure_builtins_result.py tests/unit/test_builtin_len_array.py tests/unit/test_builtin_keys.py
git commit -m "feat: migrate pure builtins to return BuiltinResult"
```

---

## Chunk 2: Heap-Mutating + Delegating Builtins

### Task 4: Migrate `_builtin_array_of` to BuiltinResult

**Files:**
- Modify: `interpreter/builtins.py:125-135` (`_builtin_array_of`)
- Test: `tests/unit/test_array_of_builtin_result.py`
- Modify: `tests/unit/test_builtin_len_array.py` (unwrap `_builtin_array_of` `.value`)

This is the key migration — `_builtin_array_of` currently does `vm.heap[addr] = HeapObject(...)`. After migration, it returns `BuiltinResult` with `new_objects` and `heap_writes`, and the **caller** (`_try_builtin_call`) applies them via `StateUpdate`.

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_array_of_builtin_result.py
"""Unit tests for _builtin_array_of returning BuiltinResult with heap side effects."""

from interpreter.builtins import _builtin_array_of
from interpreter.vm import VMState
from interpreter.vm_types import BuiltinResult
from interpreter.typed_value import TypedValue


class TestArrayOfBuiltinResult:
    def test_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_array_of([10, 20, 30], vm)
        assert isinstance(result, BuiltinResult)

    def test_value_is_heap_address(self):
        vm = VMState()
        result = _builtin_array_of([10], vm)
        assert isinstance(result.value, str)
        assert result.value.startswith("arr_")

    def test_new_objects_contains_array(self):
        vm = VMState()
        result = _builtin_array_of([10], vm)
        assert len(result.new_objects) == 1
        assert result.new_objects[0].addr == result.value
        assert result.new_objects[0].type_hint == "array"

    def test_heap_writes_contain_elements_and_length(self):
        vm = VMState()
        result = _builtin_array_of([10, 20], vm)
        fields = {hw.field: hw.value for hw in result.heap_writes}
        assert "0" in fields
        assert "1" in fields
        assert "length" in fields
        assert isinstance(fields["0"], TypedValue)
        assert fields["0"].value == 10
        assert fields["length"].value == 2

    def test_does_not_mutate_heap(self):
        vm = VMState()
        result = _builtin_array_of([10], vm)
        assert result.value not in vm.heap

    def test_empty_array(self):
        vm = VMState()
        result = _builtin_array_of([], vm)
        assert len(result.new_objects) == 1
        length_writes = [hw for hw in result.heap_writes if hw.field == "length"]
        assert len(length_writes) == 1
        assert length_writes[0].value.value == 0

    def test_increments_symbolic_counter(self):
        vm = VMState()
        _builtin_array_of([1], vm)
        assert vm.symbolic_counter == 1
        _builtin_array_of([2], vm)
        assert vm.symbolic_counter == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_array_of_builtin_result.py -v`
Expected: FAIL — `_builtin_array_of` returns raw string, not BuiltinResult

- [ ] **Step 3: Implement**

```python
def _builtin_array_of(args: list[Any], vm: VMState) -> BuiltinResult:
    """Create a heap-allocated array from arguments (arrayOf, intArrayOf, Array, etc.)."""
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

Add `NewObject, HeapWrite` to imports from `vm_types` (alongside `HeapObject, BuiltinResult`).

- [ ] **Step 4: Update test_builtin_len_array.py**

Tests that call `_builtin_array_of` then `_builtin_len` need to apply the side effects manually (since there's no executor in unit tests):

```python
def _apply_builtin_result(vm: VMState, result: BuiltinResult) -> None:
    """Apply BuiltinResult side effects to VM for unit testing.

    Uses apply_update from vm.py to mirror the real executor path.
    Requires vm.call_stack to be non-empty (apply_update accesses current_frame).
    """
    from interpreter.vm_types import StateUpdate
    from interpreter.vm import apply_update

    apply_update(
        vm,
        StateUpdate(
            new_objects=result.new_objects,
            heap_writes=result.heap_writes,
        ),
    )
```

**Important:** All tests using `_apply_builtin_result` must push a StackFrame before use, since `apply_update` accesses `vm.current_frame`:

```python
from interpreter.vm_types import StackFrame

# In each test setup or at the start of each test:
vm = VMState()
vm.call_stack.append(StackFrame(function_name="test"))
```

Update each test:
```python
def test_len_of_arrayOf_three_elements(self):
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="test"))
    result = _builtin_array_of([10, 5, 3], vm)
    _apply_builtin_result(vm, result)
    length = _builtin_len([result.value], vm)
    assert length.value == 3
```

Apply the same `vm.call_stack.append(StackFrame(function_name="test"))` to all 3 tests in `test_builtin_len_array.py` that call `_apply_builtin_result` (the 2 tests with pre-built HeapObjects don't call it and need no change).

- [ ] **Step 5: Update test_builtin_keys.py (all 4 test methods)**

`_builtin_keys` delegates to `_builtin_array_of` which now returns `BuiltinResult`. `_builtin_keys` passes through the BuiltinResult, so its return is also BuiltinResult. All 4 tests need to apply side effects and unwrap `.value`:

All 4 tests need `StackFrame` push + `_apply_builtin_result` + `.value` unwrapping:

```python
def test_keys_of_two_field_object(self):
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="test"))
    vm.heap["obj_0"] = HeapObject(
        type_hint="object",
        fields={k: typed_from_runtime(v) for k, v in {"a": 10, "b": 5}.items()},
    )
    result = Builtins.TABLE["keys"](["obj_0"], vm)
    _apply_builtin_result(vm, result)
    assert isinstance(result.value, str)
    assert result.value in vm.heap
    keys_obj = vm.heap[result.value]
    assert keys_obj.fields["length"].value == 2
    key_values = {keys_obj.fields["0"].value, keys_obj.fields["1"].value}
    assert key_values == {"a", "b"}

def test_keys_of_empty_object(self):
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="test"))
    vm.heap["obj_0"] = HeapObject(type_hint="object", fields={})
    result = Builtins.TABLE["keys"](["obj_0"], vm)
    _apply_builtin_result(vm, result)
    assert result.value in vm.heap
    assert vm.heap[result.value].fields["length"].value == 0

def test_keys_excludes_length_field(self):
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="test"))
    vm.heap["arr_0"] = HeapObject(
        type_hint="array",
        fields={
            k: typed_from_runtime(v)
            for k, v in {"0": 10, "1": 20, "length": 2}.items()
        },
    )
    result = Builtins.TABLE["keys"](["arr_0"], vm)
    _apply_builtin_result(vm, result)
    keys_obj = vm.heap[result.value]
    assert keys_obj.fields["length"].value == 2
    key_values = {keys_obj.fields["0"].value, keys_obj.fields["1"].value}
    assert key_values == {"0", "1"}

def test_len_of_keys_result(self):
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="test"))
    vm.heap["obj_0"] = HeapObject(
        type_hint="object",
        fields={
            k: typed_from_runtime(v) for k, v in {"x": 1, "y": 2, "z": 3}.items()
        },
    )
    keys_result = Builtins.TABLE["keys"](["obj_0"], vm)
    _apply_builtin_result(vm, keys_result)
    length = _builtin_len([keys_result.value], vm)
    assert length.value == 3
```

- [ ] **Step 6: Run tests to verify**

Run: `poetry run python -m pytest tests/unit/test_array_of_builtin_result.py tests/unit/test_builtin_len_array.py tests/unit/test_builtin_keys.py -v`
Expected: All pass

- [ ] **Step 7: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All 11,274+ tests pass

- [ ] **Step 8: Commit**

```bash
git add interpreter/builtins.py tests/unit/test_array_of_builtin_result.py tests/unit/test_builtin_len_array.py tests/unit/test_builtin_keys.py
git commit -m "feat: migrate _builtin_array_of to return BuiltinResult with heap side effects"
```

---

### Task 5: Migrate `_builtin_object_rest` to BuiltinResult

**Files:**
- Modify: `interpreter/builtins.py:192-213` (`_builtin_object_rest`)
- Test: `tests/unit/test_object_rest_builtin_result.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_object_rest_builtin_result.py
"""Unit tests for _builtin_object_rest returning BuiltinResult."""

from interpreter.builtins import _builtin_object_rest
from interpreter.vm import VMState, Operators
from interpreter.vm_types import BuiltinResult, HeapObject
from interpreter.typed_value import typed_from_runtime, TypedValue


class TestObjectRestBuiltinResult:
    def test_returns_builtin_result(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={
                "a": typed_from_runtime(1),
                "b": typed_from_runtime(2),
                "c": typed_from_runtime(3),
            },
        )
        result = _builtin_object_rest(["obj_0", "a"], vm)
        assert isinstance(result, BuiltinResult)

    def test_new_objects_contains_rest_object(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={
                "a": typed_from_runtime(1),
                "b": typed_from_runtime(2),
            },
        )
        result = _builtin_object_rest(["obj_0", "a"], vm)
        assert len(result.new_objects) == 1
        assert result.new_objects[0].addr == result.value
        assert result.new_objects[0].type_hint == "object"

    def test_heap_writes_contain_rest_fields(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={
                "a": typed_from_runtime(1),
                "b": typed_from_runtime(2),
                "c": typed_from_runtime(3),
            },
        )
        result = _builtin_object_rest(["obj_0", "a"], vm)
        fields = {hw.field: hw.value for hw in result.heap_writes}
        assert "a" not in fields
        assert "b" in fields
        assert "c" in fields

    def test_does_not_mutate_heap(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={"a": typed_from_runtime(1), "b": typed_from_runtime(2)},
        )
        result = _builtin_object_rest(["obj_0", "a"], vm)
        assert result.value not in vm.heap

    def test_uncomputable_no_args_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_object_rest([], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE

    def test_uncomputable_source_not_on_heap(self):
        vm = VMState()
        result = _builtin_object_rest(["nonexistent_addr", "a"], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE
        assert result.new_objects == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_object_rest_builtin_result.py -v`
Expected: FAIL

- [ ] **Step 3: Implement**

```python
def _builtin_object_rest(args: list[Any], vm: VMState) -> BuiltinResult:
    """object_rest(obj, key1, key2, ...) — return new object without excluded keys."""
    if not args:
        return BuiltinResult(value=_UNCOMPUTABLE)
    obj_val = args[0]
    excluded_keys = set(args[1:])
    addr = _heap_addr(obj_val)
    if not addr or addr not in vm.heap:
        return BuiltinResult(value=_UNCOMPUTABLE)
    source_fields = vm.heap[addr].fields
    rest_fields = {
        k: v
        for k, v in source_fields.items()
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

- [ ] **Step 4: Run tests to verify**

Run: `poetry run python -m pytest tests/unit/test_object_rest_builtin_result.py -v`
Expected: All pass

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All 11,274+ tests pass

- [ ] **Step 6: Commit**

```bash
git add interpreter/builtins.py tests/unit/test_object_rest_builtin_result.py
git commit -m "feat: migrate _builtin_object_rest to return BuiltinResult"
```

---

### Task 6: Migrate partially-delegating builtins

**Files:**
- Modify: `interpreter/builtins.py` (`_builtin_keys`, `_builtin_slice`, `_slice_heap_array`, `_method_slice`)
- Test: `tests/unit/test_delegating_builtins_result.py`

These builtins delegate to `_builtin_array_of` on happy paths (which already returns `BuiltinResult`) but have their own UNCOMPUTABLE/string return paths that need explicit `BuiltinResult` wrapping.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_delegating_builtins_result.py
"""Unit tests for partially-delegating builtins returning BuiltinResult."""

from interpreter.builtins import _builtin_keys, _builtin_slice, _slice_heap_array, _method_slice
from interpreter.vm import VMState, Operators
from interpreter.vm_types import BuiltinResult, HeapObject
from interpreter.typed_value import typed, typed_from_runtime
from interpreter.type_expr import scalar
from interpreter.constants import TypeName


class TestBuiltinKeysResult:
    def test_uncomputable_no_args_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_keys([], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE

    def test_uncomputable_not_on_heap_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_keys(["nonexistent"], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE

    def test_happy_path_returns_builtin_result(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject(
            type_hint="object",
            fields={"a": typed_from_runtime(1)},
        )
        result = _builtin_keys(["obj_0"], vm)
        assert isinstance(result, BuiltinResult)
        assert isinstance(result.value, str)
        assert len(result.new_objects) == 1


class TestBuiltinSliceResult:
    def test_uncomputable_bad_args_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_slice([1], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE

    def test_native_list_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_slice([[10, 20, 30], 0, 2], vm)
        assert isinstance(result, BuiltinResult)
        assert isinstance(result.value, str)  # heap address from _builtin_array_of

    def test_native_string_returns_builtin_result(self):
        vm = VMState()
        result = _builtin_slice(["hello", 1, 3], vm)
        assert isinstance(result, BuiltinResult)
        assert result.value == "el"
        assert result.new_objects == []

    def test_heap_array_returns_builtin_result(self):
        vm = VMState()
        vm.heap["arr_0"] = HeapObject(
            type_hint="array",
            fields={
                "0": typed(10, scalar(TypeName.INT)),
                "1": typed(20, scalar(TypeName.INT)),
                "2": typed(30, scalar(TypeName.INT)),
                "length": typed(3, scalar(TypeName.INT)),
            },
        )
        result = _builtin_slice(["arr_0", 0, 2], vm)
        assert isinstance(result, BuiltinResult)
        assert isinstance(result.value, str)
        assert len(result.new_objects) == 1


class TestSliceHeapArrayResult:
    def test_returns_builtin_result(self):
        heap_obj = HeapObject(
            type_hint="array",
            fields={
                "0": typed(10, scalar(TypeName.INT)),
                "1": typed(20, scalar(TypeName.INT)),
                "length": typed(2, scalar(TypeName.INT)),
            },
        )
        vm = VMState()
        result = _slice_heap_array(heap_obj, slice(0, 1), vm)
        assert isinstance(result, BuiltinResult)
        assert isinstance(result.value, str)
        assert len(result.new_objects) == 1

    def test_uncomputable_non_int_length(self):
        heap_obj = HeapObject(
            type_hint="array",
            fields={"length": typed("unknown", scalar(TypeName.STRING))},
        )
        vm = VMState()
        result = _slice_heap_array(heap_obj, slice(0, 1), vm)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE


class TestMethodSliceResult:
    def test_returns_builtin_result(self):
        vm = VMState()
        result = _method_slice([10, 20, 30], [0, 2], vm)
        assert isinstance(result, BuiltinResult)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_delegating_builtins_result.py -v`
Expected: FAIL

- [ ] **Step 3: Implement**

`_builtin_keys`: wrap UNCOMPUTABLE returns, pass through `_builtin_array_of` BuiltinResult:
```python
def _builtin_keys(args: list[Any], vm: VMState) -> BuiltinResult:
    if not args:
        return BuiltinResult(value=_UNCOMPUTABLE)
    val = args[0]
    addr = _heap_addr(val)
    if not addr or addr not in vm.heap:
        return BuiltinResult(value=_UNCOMPUTABLE)
    field_names = [k for k in vm.heap[addr].fields if k != "length"]
    return _builtin_array_of(field_names, vm)
```

`_builtin_slice`: wrap UNCOMPUTABLE and string returns:
```python
def _builtin_slice(args: list[Any], vm: VMState) -> BuiltinResult:
    if len(args) < 2 or any(_is_symbolic(a) for a in args):
        return BuiltinResult(value=_UNCOMPUTABLE)
    collection = args[0]
    raw_start, raw_stop, raw_step = (
        args[1],
        _arg_or_none(args, 2),
        _arg_or_none(args, 3),
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

`_slice_heap_array`: wrap UNCOMPUTABLE, pass through:
```python
def _slice_heap_array(heap_obj: HeapObject, py_slice: slice, vm: VMState) -> BuiltinResult:
    length_raw = heap_obj.fields.get("length", len(heap_obj.fields))
    length = length_raw.value if isinstance(length_raw, TypedValue) else length_raw
    if not isinstance(length, int):
        return BuiltinResult(value=_UNCOMPUTABLE)
    indices = range(length)[py_slice]
    elements = [heap_obj.fields.get(str(i)) for i in indices]
    return _builtin_array_of(elements, vm)
```

`_method_slice`: pure passthrough, return type changes:
```python
def _method_slice(obj: Any, args: list[Any], vm: VMState) -> BuiltinResult:
    return _builtin_slice([obj, *args], vm)
```

- [ ] **Step 4: Run tests to verify**

Run: `poetry run python -m pytest tests/unit/test_delegating_builtins_result.py tests/unit/test_builtin_keys.py -v`
Expected: All pass

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All 11,274+ tests pass

- [ ] **Step 6: Commit**

```bash
git add interpreter/builtins.py tests/unit/test_delegating_builtins_result.py
git commit -m "feat: migrate delegating builtins to return BuiltinResult"
```

---

## Chunk 3: BYTE_BUILTINS + Cleanup

### Task 7: Migrate BYTE_BUILTINS to BuiltinResult

**Files:**
- Modify: `interpreter/cobol/byte_builtins.py` (21 builtins)
- Test: `tests/unit/test_byte_builtins_result.py`

All BYTE_BUILTINS are pure (no heap writes). Each return statement changes from `return value` to `return BuiltinResult(value=value)`.

- [ ] **Step 1: Write failing tests (representative sample)**

```python
# tests/unit/test_byte_builtins_result.py
"""Unit tests verifying BYTE_BUILTINS return BuiltinResult."""

from interpreter.cobol.byte_builtins import (
    _builtin_nibble_get,
    _builtin_byte_from_int,
    _builtin_bytes_to_string,
    _builtin_list_get,
    _builtin_list_set,
    _builtin_make_list,
    _builtin_string_find,
    _builtin_cobol_prepare_digits,
    _builtin_int_to_binary_bytes,
    _builtin_cobol_blank_when_zero,
)
from interpreter.vm import Operators
from interpreter.vm_types import BuiltinResult


class TestByteBuiltinsReturnBuiltinResult:
    def test_nibble_get_returns_builtin_result(self):
        result = _builtin_nibble_get([0xAB, "high"], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == 0xA
        assert result.new_objects == []

    def test_byte_from_int_returns_builtin_result(self):
        result = _builtin_byte_from_int([256], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == 0

    def test_bytes_to_string_returns_builtin_result(self):
        result = _builtin_bytes_to_string([[72, 73], "ascii"], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == "HI"

    def test_list_get_returns_builtin_result(self):
        result = _builtin_list_get([[10, 20, 30], 1], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == 20

    def test_list_set_returns_builtin_result(self):
        result = _builtin_list_set([[1, 2, 3], 1, 99], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == [1, 99, 3]

    def test_make_list_returns_builtin_result(self):
        result = _builtin_make_list([3, 0], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == [0, 0, 0]

    def test_string_find_returns_builtin_result(self):
        result = _builtin_string_find(["hello", "ll"], None)
        assert isinstance(result, BuiltinResult)
        assert result.value == 2

    def test_uncomputable_returns_builtin_result(self):
        result = _builtin_nibble_get([], None)
        assert isinstance(result, BuiltinResult)
        assert result.value is Operators.UNCOMPUTABLE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_byte_builtins_result.py -v`
Expected: FAIL

- [ ] **Step 3: Migrate all BYTE_BUILTINS**

Add import to `interpreter/cobol/byte_builtins.py`:
```python
from interpreter.vm_types import BuiltinResult
```

For each of the 21 builtins, change every `return value` to `return BuiltinResult(value=value)` and update return type to `-> BuiltinResult`. This is a mechanical transformation — every `return _UNCOMPUTABLE` becomes `return BuiltinResult(value=_UNCOMPUTABLE)`, every `return computed_value` becomes `return BuiltinResult(value=computed_value)`.

- [ ] **Step 4: Run tests to verify**

Run: `poetry run python -m pytest tests/unit/test_byte_builtins_result.py -v`
Expected: All pass

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All 11,274+ tests pass

- [ ] **Step 6: Commit**

```bash
git add interpreter/cobol/byte_builtins.py tests/unit/test_byte_builtins_result.py
git commit -m "feat: migrate BYTE_BUILTINS to return BuiltinResult"
```

---

### Task 8: Remove isinstance bridge from callers

**Files:**
- Modify: `interpreter/executor.py` (`_try_builtin_call`, METHOD_TABLE dispatch)

Now that ALL builtins return `BuiltinResult`, remove the isinstance bridge and use `BuiltinResult` directly.

- [ ] **Step 1: Replace `_try_builtin_call` — remove legacy path**

```python
def _try_builtin_call(
    func_name: str,
    args: list[Any],
    inst: IRInstruction,
    vm: VMState,
) -> ExecutionResult:
    """Attempt to handle a call via the builtin table."""
    if func_name not in Builtins.TABLE:
        return ExecutionResult.not_handled()
    result = Builtins.TABLE[func_name](args, vm)
    if result.value is Operators.UNCOMPUTABLE:
        args_desc = ", ".join(_symbolic_name(a) for a in args)
        sym = vm.fresh_symbolic(hint=f"{func_name}({args_desc})")
        sym.constraints = [f"{func_name}({args_desc})"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"builtin {func_name}({args_desc}) → symbolic {sym.name} (uncomputable)",
            )
        )
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: typed_from_runtime(result.value)},
            new_objects=result.new_objects,
            heap_writes=result.heap_writes,
            reasoning=(
                f"builtin {func_name}"
                f"({', '.join(repr(a) for a in args)}) = {result.value!r}"
            ),
        )
    )
```

- [ ] **Step 2: Replace METHOD_TABLE dispatch — remove legacy path**

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
                    reasoning=f"method builtin {method_name}({obj_val!r}, {args}) = {result.value!r}",
                )
            )
```

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All 11,274+ tests pass

- [ ] **Step 4: Commit**

```bash
git add interpreter/executor.py
git commit -m "feat: remove isinstance bridge — all builtins now return BuiltinResult"
```

---

### Task 9: Format, final verification, and push

- [ ] **Step 1: Run Black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All 11,274+ tests pass, no regressions

- [ ] **Step 3: Verify no direct vm.heap mutation in builtins**

Run: `grep -n "vm\.heap\[" interpreter/builtins.py`
Expected: Only reads (in `_builtin_len`, `_builtin_keys`, `_builtin_slice`, `_builtin_object_rest`), NO writes.

Run: `grep -n "vm\.heap\[" interpreter/cobol/byte_builtins.py`
Expected: No matches.

- [ ] **Step 4: Commit formatting if needed, push**

```bash
git add -A && git commit -m "style: format with black" || true
git push origin main
```
