# HeapObject.fields TypedValue Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store TypedValue in HeapObject.fields instead of raw values, eliminating the unwrap/re-wrap roundtrip that loses type information.

**Architecture:** Change write sites (apply_update, builtins, executor) to store TypedValue in fields. Change read sites (load_field, load_index, builtins) to pass through TypedValue or unwrap explicitly. Use isinstance guards during transition to handle both raw and TypedValue.

**Tech Stack:** Python 3.13+, pytest, interpreter core (vm.py, executor.py, builtins.py, vm_types.py)

**Spec:** `docs/superpowers/specs/2026-03-13-heap-fields-typed-value-migration-design.md`

**Important — intermediate breakage:** Tasks 1-4 change write sites to store TypedValue, but read sites still call `typed_from_runtime()` unconditionally until Tasks 5-7. The existing test suite will be broken between Chunk 1 and Chunk 2 completion. Per-task commits are logical waypoints — the full suite should only be expected green after Task 8. Do NOT push individual intermediate commits.

**Deliberately unchanged:** `_handle_load_var` non-alias path (executor.py ~line 144-148) reads from `local_vars` (not heap fields), so it's unaffected by this migration. `_builtin_object_rest` copies field values which are already TypedValue after this migration — no change needed.

---

## Chunk 1: Write sites — apply_update and builtins

### Task 1: Migrate apply_update heap_writes to store TypedValue

**Files:**
- Modify: `interpreter/vm.py:252-261`
- Test: `tests/unit/test_heap_writes_typed.py`

- [ ] **Step 1: Update existing unit test to expect TypedValue in fields**

In `tests/unit/test_heap_writes_typed.py`, class `TestMaterializeHeapWrites`, update `test_raw_int_heap_write_materialized` to also verify that after `apply_update`, the heap field stores TypedValue. Add a new test:

```python
def test_apply_update_stores_typed_value_in_heap(self):
    """apply_update should store TypedValue directly in HeapObject.fields."""
    from interpreter.vm import apply_update
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="main"))
    vm.heap["obj_0"] = HeapObject(type_hint="Point")
    tv = typed(42, scalar(TypeName.INT))
    update = StateUpdate(
        heap_writes=[HeapWrite(obj_addr="obj_0", field="x", value=tv)],
        reasoning="test",
    )
    apply_update(update, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
    field_val = vm.heap["obj_0"].fields["x"]
    assert isinstance(field_val, TypedValue), f"Expected TypedValue, got {type(field_val)}"
    assert field_val.value == 42
    assert field_val.type == scalar(TypeName.INT)
```

Add import for `apply_update`:
```python
from interpreter.vm import materialize_raw_update, apply_update
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_heap_writes_typed.py::TestMaterializeHeapWrites::test_apply_update_stores_typed_value_in_heap -v`
Expected: FAIL — field stores raw `42`, not `TypedValue(42, INT)`

- [ ] **Step 3: Implement — change apply_update heap_writes loop**

In `interpreter/vm.py`, find the heap writes section (~line 252-261):

```python
    # Heap writes — unwrap TypedValue, heap storage stays raw (Phase 2)
    for hw in update.heap_writes:
        if hw.obj_addr not in vm.heap:
            vm.heap[hw.obj_addr] = HeapObject()
        val = (
            hw.value.value
            if isinstance(hw.value, TypedValue)
            else _deserialize_value(hw.value, vm)
        )
        vm.heap[hw.obj_addr].fields[hw.field] = val
```

Replace with:

```python
    # Heap writes — store TypedValue directly (Phase 2)
    for hw in update.heap_writes:
        if hw.obj_addr not in vm.heap:
            vm.heap[hw.obj_addr] = HeapObject()
        val = (
            hw.value
            if isinstance(hw.value, TypedValue)
            else typed_from_runtime(_deserialize_value(hw.value, vm))
        )
        vm.heap[hw.obj_addr].fields[hw.field] = val
```

Add `typed_from_runtime` to the imports from `interpreter.typed_value` if not already present.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_heap_writes_typed.py::TestMaterializeHeapWrites::test_apply_update_stores_typed_value_in_heap -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/vm.py tests/unit/test_heap_writes_typed.py
git commit -m "feat(typed-value): apply_update stores TypedValue in HeapObject.fields"
```

### Task 2: Migrate apply_update alias var_writes to store TypedValue in heap

**Files:**
- Modify: `interpreter/vm.py:289-294`
- Test: `tests/unit/test_pointer_aliasing.py`

- [ ] **Step 1: Write failing test**

In `tests/unit/test_pointer_aliasing.py`, add a test that verifies alias var_writes store TypedValue in heap fields. First read the file to understand existing test patterns, then add:

```python
def test_alias_var_write_stores_typed_value_in_heap(self):
    """Alias var_write should store TypedValue in HeapObject.fields."""
    from types import MappingProxyType
    from interpreter.vm import apply_update
    from interpreter.type_environment import TypeEnvironment
    from interpreter.identity_conversion_rules import IdentityConversionRules

    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="main"))
    vm.heap["mem_0"] = HeapObject(type_hint=None, fields={"0": 0})
    ptr = Pointer(base="mem_0", offset=0)
    vm.current_frame.var_heap_aliases["x"] = ptr
    tv = typed(99, scalar(TypeName.INT))
    update = StateUpdate(
        var_writes={"x": tv},
        reasoning="test",
    )
    type_env = TypeEnvironment(
        register_types=MappingProxyType({}),
        var_types=MappingProxyType({}),
    )
    apply_update(update, vm, type_env, IdentityConversionRules())
    field_val = vm.heap["mem_0"].fields["0"]
    assert isinstance(field_val, TypedValue), f"Expected TypedValue, got {type(field_val)}"
    assert field_val.value == 99
```

Add necessary imports at top of file if missing: `TypedValue`, `typed`, `scalar`, `TypeName`, `StateUpdate`.

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_pointer_aliasing.py::test_alias_var_write_stores_typed_value_in_heap -v`
Expected: FAIL — field stores raw `99`

- [ ] **Step 3: Implement — change alias var_writes in apply_update**

In `interpreter/vm.py`, find the alias var_writes section (~line 289-294):

```python
        raw_val = tv.value
        # Alias-aware: if variable is backed by a heap object, write there
        alias_ptr = target_frame.var_heap_aliases.get(var)
        if alias_ptr and alias_ptr.base in vm.heap:
            # Heap stays raw
            vm.heap[alias_ptr.base].fields[str(alias_ptr.offset)] = raw_val
```

Replace with:

```python
        # Alias-aware: if variable is backed by a heap object, write there
        alias_ptr = target_frame.var_heap_aliases.get(var)
        if alias_ptr and alias_ptr.base in vm.heap:
            vm.heap[alias_ptr.base].fields[str(alias_ptr.offset)] = tv
```

Note: `tv` is already guaranteed to be TypedValue at this point (line 284-288 ensures this). Remove the `raw_val = tv.value` line only if it's not used elsewhere in the block — check that `raw_val` is still needed for the closure bindings path at line 301. If it is, keep the line but only use `raw_val` for closures, not for heap writes.

Actually, `raw_val` IS still used at line 301 for closure bindings (`env.bindings[var] = raw_val`). So keep `raw_val = tv.value` but change the heap write to use `tv` instead of `raw_val`.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_pointer_aliasing.py::test_alias_var_write_stores_typed_value_in_heap -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/vm.py tests/unit/test_pointer_aliasing.py
git commit -m "feat(typed-value): alias var_writes store TypedValue in heap fields"
```

### Task 3: Migrate _builtin_array_of to wrap values in TypedValue

**Files:**
- Modify: `interpreter/builtins.py:123-130`
- Test: `tests/unit/test_builtins.py`

- [ ] **Step 1: Write failing test**

In `tests/unit/test_builtins.py`, add a test that verifies `_builtin_array_of` stores TypedValue in fields. First read the file to understand existing patterns, then add:

```python
def test_array_of_stores_typed_value_in_fields(self):
    """_builtin_array_of should store TypedValue in HeapObject.fields."""
    from interpreter.typed_value import TypedValue
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="main"))
    addr = _builtin_array_of([10, 20, 30], vm)
    heap_obj = vm.heap[addr]
    assert isinstance(heap_obj.fields["0"], TypedValue), "Element should be TypedValue"
    assert heap_obj.fields["0"].value == 10
    assert isinstance(heap_obj.fields["length"], TypedValue), "Length should be TypedValue"
    assert heap_obj.fields["length"].value == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_builtins.py::TestBuiltinArrayOf::test_array_of_stores_typed_value_in_fields -v`
(Adjust class name to match existing test structure.)
Expected: FAIL — fields store raw values

- [ ] **Step 3: Implement — update _builtin_array_of**

In `interpreter/builtins.py`, find `_builtin_array_of` (~line 123-130):

```python
def _builtin_array_of(args: list[Any], vm: VMState) -> Any:
    """Create a heap-allocated array from arguments (arrayOf, intArrayOf, Array, etc.)."""
    addr = f"{ARR_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    fields = {str(i): val for i, val in enumerate(args)}
    fields["length"] = len(args)
    vm.heap[addr] = HeapObject(type_hint="array", fields=fields)
    return addr
```

Replace with:

```python
def _builtin_array_of(args: list[Any], vm: VMState) -> Any:
    """Create a heap-allocated array from arguments (arrayOf, intArrayOf, Array, etc.)."""
    addr = f"{ARR_ADDR_PREFIX}{vm.symbolic_counter}"
    vm.symbolic_counter += 1
    fields = {
        str(i): val if isinstance(val, TypedValue) else typed_from_runtime(val)
        for i, val in enumerate(args)
    }
    fields["length"] = typed(len(args), scalar(TypeName.INT))
    vm.heap[addr] = HeapObject(type_hint="array", fields=fields)
    return addr
```

Add imports at top of `builtins.py`:
```python
from interpreter.constants import ARR_ADDR_PREFIX, TypeName
from interpreter.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.type_expr import scalar
```

Remove `TypeName` from the existing `ARR_ADDR_PREFIX` import if it's not there, or adjust the import line to include both.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_builtins.py::TestBuiltinArrayOf::test_array_of_stores_typed_value_in_fields -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/builtins.py tests/unit/test_builtins.py
git commit -m "feat(typed-value): _builtin_array_of stores TypedValue in heap fields"
```

### Task 4: Migrate _handle_load_field symbolic cache and _handle_address_of

**Files:**
- Modify: `interpreter/executor.py:229,439`
- Test: `tests/unit/test_heap_writes_typed.py`

- [ ] **Step 1: Write failing tests**

In `tests/unit/test_heap_writes_typed.py`, add:

```python
class TestHeapFieldsStoreTypedValue:
    """Tests verifying HeapObject.fields stores TypedValue after Phase 2."""

    def test_symbolic_cache_stores_typed_value(self):
        """_handle_load_field symbolic cache should store typed(sym, UNKNOWN) in fields."""
        from interpreter.executor import _handle_load_field
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        vm.heap["obj_0"] = HeapObject(type_hint="Foo")
        vm.current_frame.registers["%0"] = typed("obj_0", UNKNOWN)
        inst = IRInstruction(opcode=Opcode.LOAD_FIELD, operands=["%0", "bar"], result_reg="%1")
        _handle_load_field(inst, vm)
        field_val = vm.heap["obj_0"].fields["bar"]
        assert isinstance(field_val, TypedValue), f"Expected TypedValue, got {type(field_val)}"

    def test_address_of_stores_typed_value(self):
        """_handle_address_of should store typed value in promoted heap object."""
        from interpreter.executor import _handle_address_of
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        vm.current_frame.local_vars["x"] = typed(42, scalar(TypeName.INT))
        inst = IRInstruction(opcode=Opcode.ADDRESS_OF, operands=["x"], result_reg="%0")
        _handle_address_of(inst, vm)
        # Find the promoted heap object
        heap_objs = [obj for obj in vm.heap.values() if obj.fields.get("0") is not None]
        assert len(heap_objs) == 1
        field_val = heap_objs[0].fields["0"]
        assert isinstance(field_val, TypedValue), f"Expected TypedValue, got {type(field_val)}"
        assert field_val.value == 42
```

Add imports for `_handle_load_field`, `_handle_address_of`, `Opcode`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_heap_writes_typed.py::TestHeapFieldsStoreTypedValue -v`
Expected: FAIL — fields store raw values

- [ ] **Step 3: Implement — update symbolic cache and address_of**

In `interpreter/executor.py`, line 439:

Change:
```python
    heap_obj.fields[field_name] = sym
```

To:
```python
    heap_obj.fields[field_name] = typed(sym, UNKNOWN)
```

In `interpreter/executor.py`, line 229:

Change:
```python
    vm.heap[mem_addr] = HeapObject(type_hint=None, fields={"0": current_val})
```

To:
```python
    vm.heap[mem_addr] = HeapObject(type_hint=None, fields={"0": typed_from_runtime(current_val)})
```

Verify `typed` and `typed_from_runtime` are already imported in executor.py (they should be from Phase 1).

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_heap_writes_typed.py::TestHeapFieldsStoreTypedValue -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/executor.py tests/unit/test_heap_writes_typed.py
git commit -m "feat(typed-value): symbolic cache and address_of store TypedValue in heap fields"
```

## Chunk 2: Read sites — pass through TypedValue

### Task 5: Update _handle_load_field read sites to pass through TypedValue

**Files:**
- Modify: `interpreter/executor.py:378,387,430`

- [ ] **Step 1: Write failing test**

In `tests/unit/test_heap_writes_typed.py`, add:

```python
    def test_load_field_passes_through_typed_value(self):
        """_handle_load_field should pass through TypedValue from heap without re-wrapping."""
        from interpreter.executor import _handle_load_field
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        original_tv = typed(42, scalar(TypeName.INT))
        vm.heap["obj_0"] = HeapObject(type_hint="Point", fields={"x": original_tv})
        vm.current_frame.registers["%0"] = typed("obj_0", UNKNOWN)
        inst = IRInstruction(opcode=Opcode.LOAD_FIELD, operands=["%0", "x"], result_reg="%1")
        result = _handle_load_field(inst, vm)
        loaded_tv = result.update.register_writes["%1"]
        assert loaded_tv is original_tv, "Should pass through the exact same TypedValue object"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_heap_writes_typed.py::TestHeapFieldsStoreTypedValue::test_load_field_passes_through_typed_value -v`
Expected: FAIL — `typed_from_runtime` creates a new TypedValue instead of passing through

- [ ] **Step 3: Implement — update all 3 read sites in _handle_load_field**

In `interpreter/executor.py`:

**Site 1 (~line 378):** pointer dereference path:
Change:
```python
            val = heap_obj.fields.get(str(obj_val.offset))
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: typed_from_runtime(val)},
```
To:
```python
            val = heap_obj.fields.get(str(obj_val.offset))
            tv = val if isinstance(val, TypedValue) else typed_from_runtime(val)
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: tv},
```

**Site 2 (~line 387):** pointer field path:
Change:
```python
            val = heap_obj.fields[field_name]
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: typed_from_runtime(val)},
```
To:
```python
            val = heap_obj.fields[field_name]
            tv = val if isinstance(val, TypedValue) else typed_from_runtime(val)
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: tv},
```

**Site 3 (~line 430):** regular field path:
Change:
```python
        val = heap_obj.fields[field_name]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: typed_from_runtime(val)},
```
To:
```python
        val = heap_obj.fields[field_name]
        tv = val if isinstance(val, TypedValue) else typed_from_runtime(val)
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: tv},
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_heap_writes_typed.py::TestHeapFieldsStoreTypedValue::test_load_field_passes_through_typed_value -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/executor.py tests/unit/test_heap_writes_typed.py
git commit -m "feat(typed-value): _handle_load_field passes through TypedValue from heap"
```

### Task 6: Update _handle_load_index, _handle_load_var alias, and call-index read sites

**Files:**
- Modify: `interpreter/executor.py:135,523,1178`

- [ ] **Step 1: Write failing tests**

In `tests/unit/test_heap_writes_typed.py`, add:

```python
    def test_load_index_passes_through_typed_value(self):
        """_handle_load_index should pass through TypedValue from heap."""
        from interpreter.executor import _handle_load_index
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        original_tv = typed(99, scalar(TypeName.INT))
        vm.heap["arr_0"] = HeapObject(type_hint="array", fields={"0": original_tv, "length": typed(1, scalar(TypeName.INT))})
        vm.current_frame.registers["%0"] = typed("arr_0", UNKNOWN)
        vm.current_frame.registers["%1"] = typed(0, scalar(TypeName.INT))
        inst = IRInstruction(opcode=Opcode.LOAD_INDEX, operands=["%0", "%1"], result_reg="%2")
        result = _handle_load_index(inst, vm)
        loaded_tv = result.update.register_writes["%2"]
        assert loaded_tv is original_tv, "Should pass through the exact same TypedValue object"

    def test_load_var_alias_passes_through_typed_value(self):
        """_handle_load_var alias path should pass through TypedValue from heap."""
        from interpreter.executor import _handle_load_var
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        original_tv = typed(77, scalar(TypeName.INT))
        vm.heap["mem_0"] = HeapObject(type_hint=None, fields={"0": original_tv})
        ptr = Pointer(base="mem_0", offset=0)
        vm.current_frame.var_heap_aliases["x"] = ptr
        inst = IRInstruction(opcode=Opcode.LOAD_VAR, operands=["x"], result_reg="%0")
        result = _handle_load_var(inst, vm)
        loaded_tv = result.update.register_writes["%0"]
        assert loaded_tv is original_tv, "Should pass through the exact same TypedValue object"
```

Also add a test for the call-index read site:

```python
    def test_call_index_passes_through_typed_value(self):
        """Scala-style arr(i) call-index should pass through TypedValue from heap."""
        from interpreter.executor import _handle_call_builtin_or_dispatch
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        original_tv = typed(55, scalar(TypeName.INT))
        vm.heap["arr_0"] = HeapObject(type_hint="array", fields={"0": original_tv})
        vm.current_frame.registers["%0"] = typed("arr_0", UNKNOWN)
        vm.current_frame.registers["%1"] = typed(0, scalar(TypeName.INT))
        inst = IRInstruction(opcode=Opcode.CALL_FUNCTION, operands=["%0", "%1"], result_reg="%2")
        result = _handle_call_builtin_or_dispatch(inst, vm)
        loaded_tv = result.update.register_writes["%2"]
        assert loaded_tv is original_tv, "Should pass through the exact same TypedValue object"
```

Add imports for `_handle_load_index`, `_handle_load_var`, `_handle_call_builtin_or_dispatch`, `Pointer`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_heap_writes_typed.py::TestHeapFieldsStoreTypedValue::test_load_index_passes_through_typed_value tests/unit/test_heap_writes_typed.py::TestHeapFieldsStoreTypedValue::test_load_var_alias_passes_through_typed_value -v`
Expected: FAIL

- [ ] **Step 3: Implement — update all 3 read sites**

In `interpreter/executor.py`:

**_handle_load_var alias path (~line 135):**
Change:
```python
            val = vm.heap[alias_ptr.base].fields.get(str(alias_ptr.offset))
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: typed_from_runtime(val)},
```
To:
```python
            val = vm.heap[alias_ptr.base].fields.get(str(alias_ptr.offset))
            tv = val if isinstance(val, TypedValue) else typed_from_runtime(val)
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: tv},
```

**_handle_load_index (~line 523):**
Change:
```python
        val = heap_obj.fields[key]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: typed_from_runtime(val)},
```
To:
```python
        val = heap_obj.fields[key]
        tv = val if isinstance(val, TypedValue) else typed_from_runtime(val)
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: tv},
```

**Call-index site (~line 1178):**
Change:
```python
                element = heap_obj.fields[idx_key]
                return ExecutionResult.success(
                    StateUpdate(
                        register_writes={inst.result_reg: typed_from_runtime(element)},
```
To:
```python
                element = heap_obj.fields[idx_key]
                tv = element if isinstance(element, TypedValue) else typed_from_runtime(element)
                return ExecutionResult.success(
                    StateUpdate(
                        register_writes={inst.result_reg: tv},
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_heap_writes_typed.py::TestHeapFieldsStoreTypedValue -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/executor.py tests/unit/test_heap_writes_typed.py
git commit -m "feat(typed-value): load_index, load_var alias, call-index pass through TypedValue"
```

### Task 7: Update builtin read sites (_builtin_len, _slice_heap_array)

**Files:**
- Modify: `interpreter/builtins.py:18-30,176-183`
- Test: `tests/unit/test_builtins.py`

- [ ] **Step 1: Write failing tests**

In `tests/unit/test_builtins.py`, add tests that exercise `_builtin_len` and `_builtin_slice` with TypedValue fields. First read the file to understand existing patterns, then add:

```python
def test_len_unwraps_typed_value_length(self):
    """_builtin_len should unwrap TypedValue from length field."""
    from interpreter.typed_value import TypedValue, typed
    from interpreter.type_expr import scalar
    from interpreter.constants import TypeName
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="main"))
    vm.heap["arr_0"] = HeapObject(
        type_hint="array",
        fields={"length": typed(5, scalar(TypeName.INT))},
    )
    result = _builtin_len(["arr_0"], vm)
    assert result == 5, f"Expected 5, got {result}"
    assert isinstance(result, int), f"Expected int, got {type(result)}"
```

Also add a test for `_slice_heap_array` with TypedValue length:

```python
def test_slice_heap_array_unwraps_typed_value_length(self):
    """_slice_heap_array should unwrap TypedValue from length field."""
    from interpreter.typed_value import TypedValue, typed
    from interpreter.type_expr import scalar
    from interpreter.constants import TypeName
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="main"))
    fields = {
        "0": typed(10, scalar(TypeName.INT)),
        "1": typed(20, scalar(TypeName.INT)),
        "2": typed(30, scalar(TypeName.INT)),
        "length": typed(3, scalar(TypeName.INT)),
    }
    heap_obj = HeapObject(type_hint="array", fields=fields)
    result = _slice_heap_array(heap_obj, slice(1, 3), vm)
    # Should return a new array address, not _UNCOMPUTABLE
    assert isinstance(result, str), f"Expected array address, got {result}"
    new_arr = vm.heap[result]
    assert new_arr.fields["length"].value == 2
```

Import `_slice_heap_array` at the top of the test file or inline.

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_builtins.py::<test_class>::test_len_unwraps_typed_value_length tests/unit/test_builtins.py::<test_class>::test_slice_heap_array_unwraps_typed_value_length -v`
Expected: FAIL — `_builtin_len` returns TypedValue; `_slice_heap_array` returns `_UNCOMPUTABLE`

- [ ] **Step 3: Implement — update _builtin_len and _slice_heap_array**

In `interpreter/builtins.py`, `_builtin_len` (~line 18-30):

Change:
```python
def _builtin_len(args: list[Any], vm: VMState) -> Any:
    if not args:
        return _UNCOMPUTABLE
    val = args[0]
    addr = _heap_addr(val)
    if addr and addr in vm.heap:
        fields = vm.heap[addr].fields
        if "length" in fields:
            return fields["length"]
        return len(fields)
```

To:
```python
def _builtin_len(args: list[Any], vm: VMState) -> Any:
    if not args:
        return _UNCOMPUTABLE
    val = args[0]
    addr = _heap_addr(val)
    if addr and addr in vm.heap:
        fields = vm.heap[addr].fields
        if "length" in fields:
            length = fields["length"]
            return length.value if isinstance(length, TypedValue) else length
        return len(fields)
```

In `interpreter/builtins.py`, `_slice_heap_array` (~line 176-183):

Change:
```python
def _slice_heap_array(heap_obj: HeapObject, py_slice: slice, vm: VMState) -> Any:
    """Apply a Python slice to a heap-backed array and return a new heap array."""
    length = heap_obj.fields.get("length", len(heap_obj.fields))
    if not isinstance(length, int):
        return _UNCOMPUTABLE
    indices = range(length)[py_slice]
    elements = [heap_obj.fields.get(str(i)) for i in indices]
    return _builtin_array_of(elements, vm)
```

To:
```python
def _slice_heap_array(heap_obj: HeapObject, py_slice: slice, vm: VMState) -> Any:
    """Apply a Python slice to a heap-backed array and return a new heap array."""
    length_raw = heap_obj.fields.get("length", len(heap_obj.fields))
    length = length_raw.value if isinstance(length_raw, TypedValue) else length_raw
    if not isinstance(length, int):
        return _UNCOMPUTABLE
    indices = range(length)[py_slice]
    elements = [heap_obj.fields.get(str(i)) for i in indices]
    return _builtin_array_of(elements, vm)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_builtins.py::<test_class>::test_len_unwraps_typed_value_length -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/builtins.py tests/unit/test_builtins.py
git commit -m "feat(typed-value): _builtin_len and _slice_heap_array unwrap TypedValue"
```

## Chunk 3: Fix broken test assertions and run full suite

### Task 8: Update test assertions that expect raw values in heap fields

**Files:**
- Modify: `tests/unit/test_builtins.py` (~33 assertions)
- Modify: `tests/unit/test_builtin_keys.py` (~5 assertions)
- Modify: `tests/unit/test_pointer_aliasing.py` (~5 assertions)
- Modify: `tests/unit/test_materialize_raw_update.py` (~1 assertion)
- Modify: `tests/unit/test_class_instantiation.py` (~1 assertion)
- Modify: `tests/unit/test_unresolved_call.py` (~1 assertion)
- Modify: `tests/integration/test_rest_pattern_execution.py` (~5 assertions)
- Modify: `tests/integration/test_field_init_method_chaining.py` (~1 assertion)
- Modify: `tests/unit/test_data_layout.py` (~31 assertions)
- Modify: `tests/unit/test_occurs_layout.py` (~9 assertions)

- [ ] **Step 1: Run full test suite to identify all failures**

Run: `poetry run python -m pytest --tb=line -q 2>&1 | head -100`

This will show all failures. The pattern is always the same: tests assert `heap_obj.fields[key] == raw_value` but now get `TypedValue(raw_value, type)`.

- [ ] **Step 2: Fix assertions across all test files**

For each failing assertion, change the pattern from:

```python
assert heap_obj.fields["key"] == raw_value
```

To:

```python
assert heap_obj.fields["key"].value == raw_value
```

Or for isinstance checks:

```python
assert isinstance(heap_obj.fields["key"], int)
```

To:

```python
assert heap_obj.fields["key"].value == expected  # check value directly
```

For tests that write directly to `heap_obj.fields`, wrap the value:

```python
# Before:
vm.heap["obj_0"].fields["x"] = 10
# After:
vm.heap["obj_0"].fields["x"] = typed(10, scalar(TypeName.INT))
```

Or use `typed_from_runtime`:

```python
vm.heap["obj_0"].fields["x"] = typed_from_runtime(10)
```

**Important:** The `test_data_layout.py` and `test_occurs_layout.py` tests are for COBOL data layout which stores raw field values. These tests construct HeapObjects directly in test setup — update the field writes to use `typed_from_runtime()` and the field reads to use `.value`.

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass (11,474+ with new tests)

- [ ] **Step 4: Run black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: update heap field assertions for TypedValue storage (Phase 2)"
```

- [ ] **Step 6: Format and final verification**

Run: `poetry run python -m black .`
Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass (11,474+)

- [ ] **Step 7: Close the issue and push**

```bash
bd update red-dragon-x2t --status closed
git push origin main
```
