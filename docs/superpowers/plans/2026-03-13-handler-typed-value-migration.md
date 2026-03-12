# Handler TypedValue Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all executor handlers to produce TypedValue directly in register_writes/var_writes, eliminating the serialize/deserialize roundtrip for local execution.

**Architecture:** Split `apply_update` into a typed path (stores TypedValue directly with lightweight coercion) and a `materialize_raw_update` adapter for LLM responses. Migrate handlers incrementally, one group per commit. The LLM path is unchanged.

**Tech Stack:** Python 3.13+, Pydantic (StateUpdate model), pytest

**Spec:** `docs/superpowers/specs/2026-03-12-handler-typed-value-migration-design.md`

---

## Chunk 1: Foundation

### Task 1: Create materialize_raw_update and refactor apply_update

**Files:**
- Modify: `interpreter/vm.py:62-148` (apply_update + new materialize_raw_update)
- Modify: `interpreter/run.py:140-168` (_handle_call_dispatch_setup)
- Modify: `interpreter/run.py:170-202` (_handle_return_flow)
- Modify: `interpreter/run.py:269-319` (execute_cfg main loop)
- Modify: `interpreter/run.py:413-458` (execute_cfg_traced main loop)
- Modify: `interpreter/run.py:648-661` (_format_val)
- Create: `tests/unit/test_materialize_raw_update.py`

**Context:** Currently `apply_update` does everything: deserialize dicts back to objects, coerce types, wrap in TypedValue. We split this into:
- `materialize_raw_update(raw_update, vm, type_env, conversion_rules)` — the old logic: deserialize + coerce + wrap → returns a new StateUpdate with TypedValue values
- `apply_update(vm, update, type_env, conversion_rules)` — stores TypedValue directly with lightweight coercion check

During the transition, handlers still produce raw values. The execution loop calls `materialize_raw_update` for **all** updates (both local and LLM). Once handlers are migrated, only the LLM path will call `materialize_raw_update`.

- [ ] **Step 1: Write failing tests for materialize_raw_update**

Create `tests/unit/test_materialize_raw_update.py`:

```python
"""Unit tests for materialize_raw_update."""

from types import MappingProxyType

from interpreter.type_environment import TypeEnvironment
from interpreter.type_expr import UNKNOWN, scalar
from interpreter.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.identity_conversion_rules import IdentityConversionRules
from interpreter.vm import materialize_raw_update, apply_update
from interpreter.vm_types import StateUpdate, VMState, StackFrame, SymbolicValue, Pointer


_EMPTY_TYPE_ENV = TypeEnvironment(
    register_types=MappingProxyType({}),
    var_types=MappingProxyType({}),
)
_IDENTITY_RULES = IdentityConversionRules()


class TestMaterializeRawUpdate:
    """Tests for materialize_raw_update — converts raw StateUpdate to TypedValue."""

    def test_int_register_write(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        raw = StateUpdate(register_writes={"%0": 42}, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        tv = result.register_writes["%0"]
        assert isinstance(tv, TypedValue)
        assert tv.value == 42
        assert tv.type == scalar("Int")

    def test_string_register_write(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        raw = StateUpdate(register_writes={"%0": "hello"}, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        tv = result.register_writes["%0"]
        assert isinstance(tv, TypedValue)
        assert tv.value == "hello"
        assert tv.type == scalar("String")

    def test_symbolic_dict_deserialized(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        sym_dict = {"__symbolic__": True, "name": "sym_0", "type_hint": "Int", "constraints": []}
        raw = StateUpdate(register_writes={"%0": sym_dict}, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        tv = result.register_writes["%0"]
        assert isinstance(tv, TypedValue)
        assert isinstance(tv.value, SymbolicValue)
        assert tv.value.name == "sym_0"

    def test_pointer_dict_deserialized(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        ptr_dict = {"__pointer__": True, "base": "mem_0", "offset": 4}
        raw = StateUpdate(register_writes={"%0": ptr_dict}, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        tv = result.register_writes["%0"]
        assert isinstance(tv, TypedValue)
        assert isinstance(tv.value, Pointer)
        assert tv.value.base == "mem_0"
        assert tv.value.offset == 4

    def test_var_write_materialized(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        raw = StateUpdate(var_writes={"x": 10}, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        tv = result.var_writes["x"]
        assert isinstance(tv, TypedValue)
        assert tv.value == 10
        assert tv.type == scalar("Int")

    def test_non_register_var_fields_unchanged(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        raw = StateUpdate(
            register_writes={"%0": 42},
            reasoning="test",
            next_label="block_1",
            path_condition="x > 0",
        )
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        assert result.next_label == "block_1"
        assert result.path_condition == "x > 0"
        assert result.reasoning == "test"

    def test_already_typed_value_passes_through(self):
        """During migration, some values may already be TypedValue."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        tv = typed(42, scalar("Int"))
        raw = StateUpdate(register_writes={"%0": tv}, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        assert result.register_writes["%0"] is tv


class TestApplyUpdateTypedPath:
    """Tests for apply_update receiving TypedValue directly."""

    def test_stores_typed_value_directly(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        tv = typed(42, scalar("Int"))
        update = StateUpdate(register_writes={"%0": tv}, reasoning="test")
        apply_update(vm, update, type_env=_EMPTY_TYPE_ENV, conversion_rules=_IDENTITY_RULES)
        assert vm.current_frame.registers["%0"] is tv

    def test_stores_typed_var_directly(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        tv = typed(10, scalar("Int"))
        update = StateUpdate(var_writes={"x": tv}, reasoning="test")
        apply_update(vm, update, type_env=_EMPTY_TYPE_ENV, conversion_rules=_IDENTITY_RULES)
        assert vm.current_frame.local_vars["x"] is tv

    def test_heap_alias_unwraps_value(self):
        from interpreter.vm_types import HeapObject
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        vm.heap["mem_0"] = HeapObject(fields={"0": None})
        vm.current_frame.var_heap_aliases["x"] = Pointer(base="mem_0", offset=0)
        tv = typed(42, scalar("Int"))
        update = StateUpdate(var_writes={"x": tv}, reasoning="test")
        apply_update(vm, update, type_env=_EMPTY_TYPE_ENV, conversion_rules=_IDENTITY_RULES)
        # Heap gets raw value, not TypedValue
        assert vm.heap["mem_0"].fields["0"] == 42

    def test_closure_binding_unwraps_value(self):
        from interpreter.vm_types import ClosureEnvironment
        vm = VMState()
        env = ClosureEnvironment(bindings={})
        vm.closures["env_0"] = env
        vm.call_stack.append(StackFrame(
            function_name="inner",
            closure_env_id="env_0",
            captured_var_names=frozenset({"x"}),
        ))
        tv = typed(42, scalar("Int"))
        update = StateUpdate(var_writes={"x": tv}, reasoning="test")
        apply_update(vm, update, type_env=_EMPTY_TYPE_ENV, conversion_rules=_IDENTITY_RULES)
        # Closure binding gets raw value
        assert env.bindings["x"] == 42
        # Local var gets TypedValue
        assert vm.current_frame.local_vars["x"] is tv

    def test_register_coercion_when_declared_type_differs(self):
        """When type_env declares a different type for a register, coerce."""
        from interpreter.default_conversion_rules import DefaultTypeConversionRules
        type_env = TypeEnvironment(
            register_types=MappingProxyType({"%0": scalar("Float")}),
            var_types=MappingProxyType({}),
        )
        rules = DefaultTypeConversionRules()
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        tv = typed(42, scalar("Int"))
        update = StateUpdate(register_writes={"%0": tv}, reasoning="test")
        apply_update(vm, update, type_env=type_env, conversion_rules=rules)
        result = vm.current_frame.registers["%0"]
        assert isinstance(result, TypedValue)
        assert isinstance(result.value, float)
        assert result.type == scalar("Float")


class TestFormatVal:
    """Tests for _format_val handling TypedValue."""

    def test_format_typed_int(self):
        from interpreter.run import _format_val
        assert _format_val(typed(42, scalar("Int"))) == "42"

    def test_format_typed_symbolic(self):
        from interpreter.run import _format_val
        sym = SymbolicValue(name="sym_0", type_hint="Int")
        assert "sym_0" in _format_val(typed(sym, UNKNOWN))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_materialize_raw_update.py -v`
Expected: FAIL — `materialize_raw_update` does not exist yet

- [ ] **Step 3: Implement materialize_raw_update and refactor apply_update**

In `interpreter/vm.py`, add `materialize_raw_update` (extracts the current deserialize+coerce+wrap logic) and refactor `apply_update` to expect TypedValue:

```python
def materialize_raw_update(
    raw_update: StateUpdate,
    vm: VMState,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    conversion_rules: TypeConversionRules = _IDENTITY_RULES,
) -> StateUpdate:
    """Transform a raw StateUpdate (from LLM) into one with TypedValue values.

    Deserializes symbolic/pointer dicts, applies type coercion, and wraps
    all register_writes and var_writes values in TypedValue. Other fields
    are passed through unchanged.
    """
    typed_reg_writes: dict[str, Any] = {}
    for reg, val in raw_update.register_writes.items():
        if isinstance(val, TypedValue):
            typed_reg_writes[reg] = val
            continue
        deserialized = _deserialize_value(val, vm)
        coerced = _coerce_value(deserialized, reg, type_env, conversion_rules)
        declared_type = type_env.register_types.get(reg, UNKNOWN)
        inferred_type = declared_type or typed_from_runtime(coerced).type
        typed_reg_writes[reg] = typed(coerced, inferred_type)

    typed_var_writes: dict[str, Any] = {}
    for var, val in raw_update.var_writes.items():
        if isinstance(val, TypedValue):
            typed_var_writes[var] = val
            continue
        deserialized = _deserialize_value(val, vm)
        declared_type = type_env.var_types.get(var, UNKNOWN)
        inferred_type = declared_type or typed_from_runtime(deserialized).type
        typed_var_writes[var] = typed(deserialized, inferred_type)

    return raw_update.model_copy(
        update={
            "register_writes": typed_reg_writes,
            "var_writes": typed_var_writes,
        }
    )


def apply_update(
    vm: VMState,
    update: StateUpdate,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    conversion_rules: TypeConversionRules = _IDENTITY_RULES,
):
    """Apply a StateUpdate to the VM. Expects TypedValue in register/var writes."""
    frame = vm.current_frame

    # New regions
    for addr, size in update.new_regions.items():
        vm.regions[addr] = bytearray(size)

    # Region writes
    for rw in update.region_writes:
        vm.regions[rw.region_addr][rw.offset : rw.offset + len(rw.data)] = bytes(
            rw.data
        )

    # Continuation writes
    for name, label in update.continuation_writes.items():
        vm.continuations[name] = label

    # Continuation clear (fired by RESUME_CONTINUATION)
    if update.continuation_clear:
        vm.continuations.pop(update.continuation_clear, None)

    # New objects
    for obj in update.new_objects:
        vm.heap[obj.addr] = HeapObject(type_hint=obj.type_hint)

    # Register writes — expects TypedValue, applies lightweight coercion
    for reg, tv in update.register_writes.items():
        declared = type_env.register_types.get(reg, UNKNOWN)
        if declared and tv.type != declared:
            coerced = _coerce_value(tv.value, reg, type_env, conversion_rules)
            frame.registers[reg] = typed(coerced, declared)
        else:
            frame.registers[reg] = tv

    # Heap writes (stay raw — red-dragon-gny)
    for hw in update.heap_writes:
        if hw.obj_addr not in vm.heap:
            vm.heap[hw.obj_addr] = HeapObject()
        vm.heap[hw.obj_addr].fields[hw.field] = _deserialize_value(hw.value, vm)

    # Path condition
    if update.path_condition:
        vm.path_conditions.append(update.path_condition)

    # Call push
    if update.call_push:
        vm.call_stack.append(
            StackFrame(
                function_name=update.call_push.function_name,
                return_label=update.call_push.return_label,
                closure_env_id=update.call_push.closure_env_id,
                captured_var_names=frozenset(update.call_push.captured_var_names),
            )
        )

    # Variable writes — expects TypedValue
    target_frame = vm.current_frame
    for var, tv in update.var_writes.items():
        raw_val = tv.value
        alias_ptr = target_frame.var_heap_aliases.get(var)
        if alias_ptr and alias_ptr.base in vm.heap:
            vm.heap[alias_ptr.base].fields[str(alias_ptr.offset)] = raw_val
        else:
            target_frame.local_vars[var] = tv
        if target_frame.closure_env_id and var in target_frame.captured_var_names:
            env = vm.closures.get(target_frame.closure_env_id)
            if env:
                env.bindings[var] = raw_val

    # Call pop
    if update.call_pop and len(vm.call_stack) > 1:
        vm.call_stack.pop()
```

- [ ] **Step 4: Update execution loop to call materialize_raw_update**

In `interpreter/run.py`, update `execute_cfg` (around lines 269-319):

```python
# Add to imports at top:
from interpreter.vm import materialize_raw_update

# In the execution loop, AFTER getting the update:
        result = _try_execute_locally(
            instruction,
            vm,
            cfg=cfg,
            registry=registry,
            current_label=current_label,
            ip=ip,
            call_resolver=call_resolver,
            overload_resolver=overload_resolver,
            type_env=type_env,
            binop_coercion=binop_coercion,
        )
        used_llm = False
        if result.handled:
            update = materialize_raw_update(result.update, vm, type_env, conversion_rules)
        else:
            if llm is None:
                llm = get_backend(config.backend)
            raw_update = llm.interpret_instruction(instruction, vm)
            update = materialize_raw_update(raw_update, vm, type_env, conversion_rules)
            used_llm = True
            llm_calls += 1
```

Apply the same change in `execute_cfg_traced` (around lines 413-433). The structure is identical: replace the `result.update` and `llm.interpret_instruction` usages with `materialize_raw_update` wrapping.

**Note on `_handle_call_dispatch_setup`:** This function receives the `update` parameter from the execution loop caller, which has already been materialized. No changes needed inside `_handle_call_dispatch_setup` itself — it just calls `apply_update` on the pre-materialized update.

**Important:** During the transition, ALL updates go through `materialize_raw_update`. The `materialize_raw_update` function already handles the case where a value is already TypedValue (passes through). As handlers are migrated, they'll produce TypedValue that passes through; unmigrated handlers produce raw values that get materialized.

- [ ] **Step 5: Fix _handle_return_flow to wrap return value in TypedValue**

In `interpreter/run.py`, update `_handle_return_flow` (line 192-193):

```python
    # Before:
    if return_frame.result_reg and update.return_value is not None:
        caller_frame.registers[return_frame.result_reg] = _deserialize_value(
            update.return_value, vm
        )
    # After:
    if return_frame.result_reg and update.return_value is not None:
        raw = _deserialize_value(update.return_value, vm)
        caller_frame.registers[return_frame.result_reg] = typed_from_runtime(raw)
```

Add `typed_from_runtime` to the imports from `interpreter.typed_value`.

- [ ] **Step 6: Update _format_val to handle TypedValue**

In `interpreter/run.py`, update `_format_val` (lines 648-661):

```python
def _format_val(v: Any) -> str:
    """Format a value for verbose display."""
    if isinstance(v, TypedValue):
        return _format_val(v.value)
    if isinstance(v, SymbolicValue):
        if v.constraints:
            return f"{v.name} [{', '.join(v.constraints)}]"
        return f"{v.name}" + (f" ({v.type_hint})" if v.type_hint else "")
    if isinstance(v, dict) and v.get("__symbolic__"):
        name = v.get("name", "?")
        constraints = v.get("constraints", [])
        if constraints:
            return f"{name} [{', '.join(str(c) for c in constraints)}]"
        hint = v.get("type_hint", "")
        return f"{name}" + (f" ({hint})" if hint else "")
    return repr(v)
```

- [ ] **Step 7: Run tests to verify foundation works**

Run: `poetry run python -m pytest tests/unit/test_materialize_raw_update.py -v`
Expected: All PASS

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All 11,400+ tests pass (no regressions)

- [ ] **Step 8: Format and commit**

```bash
poetry run python -m black .
git add interpreter/vm.py interpreter/run.py tests/unit/test_materialize_raw_update.py
git commit -m "feat: add materialize_raw_update, refactor apply_update for TypedValue

Split apply_update into typed path (stores directly) and
materialize_raw_update adapter (deserialize+coerce+wrap for LLM path).
All updates flow through materialize_raw_update during transition."
```

---

## Chunk 2: Simple handler migration

### Task 2: Migrate _handle_const and _handle_store_var

**Files:**
- Modify: `interpreter/executor.py:77-125` (_handle_const)
- Modify: `interpreter/executor.py:162-172` (_handle_store_var)
- Modify: `interpreter/executor.py` (imports)

**Context:** These are the simplest handlers — they each have one `register_writes` or `var_writes` site.

- [ ] **Step 1: Migrate _handle_const**

In `interpreter/executor.py`, add `typed_from_runtime` to imports:
```python
from interpreter.typed_value import TypedValue, typed_from_runtime
```

Change `_handle_const` return (line 122):
```python
    # Before:
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: val},
            reasoning=f"const {raw!r} → {inst.result_reg}",
        )
    )
    # After:
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: typed_from_runtime(val)},
            reasoning=f"const {raw!r} → {inst.result_reg}",
        )
    )
```

- [ ] **Step 2: Migrate _handle_store_var**

Change `_handle_store_var` (line 169):
```python
    # Before:
    var_writes={name: _serialize_value(val)},
    # After:
    var_writes={name: typed_from_runtime(val)},
```

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All tests pass

- [ ] **Step 4: Format and commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "feat(typed-value): migrate _handle_const and _handle_store_var to TypedValue"
```

### Task 3: Migrate _handle_load_var

**Files:**
- Modify: `interpreter/executor.py:128-159` (_handle_load_var)

**Context:** `_handle_load_var` has three return paths:
1. Heap alias read → `_serialize_value(val)` (line 139)
2. Found in local_vars → `_serialize_value(val)` (line 148), but `val` is already unwrapped from TypedValue at line 145
3. Not found → `sym.to_dict()` (line 156)

- [ ] **Step 1: Migrate all three return paths**

```python
def _handle_load_var(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    name = inst.operands[0]
    # Alias-aware: if variable is backed by a heap object, read from heap
    for f in reversed(vm.call_stack):
        alias_ptr = f.var_heap_aliases.get(name)
        if alias_ptr and alias_ptr.base in vm.heap:
            val = vm.heap[alias_ptr.base].fields.get(str(alias_ptr.offset))
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: typed_from_runtime(val)},
                    reasoning=f"load {name} = {val!r} (via heap alias {alias_ptr.base})",
                )
            )
        if name in f.local_vars:
            stored = f.local_vars[name]
            val = stored.value if isinstance(stored, TypedValue) else stored
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: typed_from_runtime(val)},
                    reasoning=f"load {name} = {val!r} → {inst.result_reg}",
                )
            )
    # Variable not found — create symbolic
    sym = vm.fresh_symbolic(hint=name)
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: typed(sym, UNKNOWN)},
            reasoning=f"load {name} (not found) → symbolic {sym.name}",
        )
    )
```

Add `typed` and `UNKNOWN` to imports:
```python
from interpreter.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.type_expr import UNKNOWN, scalar
```

(`UNKNOWN` and `scalar` may already be imported — check first.)

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All tests pass

- [ ] **Step 3: Format and commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "feat(typed-value): migrate _handle_load_var to TypedValue"
```

### Task 4: Migrate _handle_load_field

**Files:**
- Modify: `interpreter/executor.py:363-440` (_handle_load_field)

**Context:** `_handle_load_field` has 6 return paths producing register_writes:
1. Pointer dereference `*ptr` → `_serialize_value(val)` (line 376)
2. Pointer field `ptr->field` → `_serialize_value(val)` (line 385)
3. Pointer not on heap → `sym.to_dict()` (line 393)
4. Function pointer deref → raw `obj_val` string (line 405)
5. Object not on heap → `sym.to_dict()` (line 419)
6. Field found → `_serialize_value(val)` (line 428)
7. Field not found → `sym.to_dict()` (line 437)

- [ ] **Step 1: Migrate all return paths**

Replace each occurrence:
- `_serialize_value(val)` → `typed_from_runtime(val)`
- `sym.to_dict()` → `typed(sym, UNKNOWN)`
- Raw string `obj_val` (function pointer deref, line 405) → `typed_from_runtime(obj_val)`

Full replacement for lines 376, 385, 393, 405, 419, 428, 437:

```python
# Line 376: register_writes={inst.result_reg: _serialize_value(val)},
register_writes={inst.result_reg: typed_from_runtime(val)},

# Line 385: register_writes={inst.result_reg: _serialize_value(val)},
register_writes={inst.result_reg: typed_from_runtime(val)},

# Line 393: register_writes={inst.result_reg: sym.to_dict()},
register_writes={inst.result_reg: typed(sym, UNKNOWN)},

# Line 405: register_writes={inst.result_reg: obj_val},
register_writes={inst.result_reg: typed_from_runtime(obj_val)},

# Line 419: register_writes={inst.result_reg: sym.to_dict()},
register_writes={inst.result_reg: typed(sym, UNKNOWN)},

# Line 428: register_writes={inst.result_reg: _serialize_value(val)},
register_writes={inst.result_reg: typed_from_runtime(val)},

# Line 437: register_writes={inst.result_reg: sym.to_dict()},
register_writes={inst.result_reg: typed(sym, UNKNOWN)},
```

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All tests pass

- [ ] **Step 3: Format and commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "feat(typed-value): migrate _handle_load_field to TypedValue"
```

### Task 5: Migrate _handle_load_index

**Files:**
- Modify: `interpreter/executor.py:476-531` (_handle_load_index)

**Context:** 5 return paths:
1. Native list indexing → `_serialize_value(element)` (line 490)
2. Native string indexing → `_serialize_value(element)` (line 498)
3. Array not on heap → `sym.to_dict()` (line 511)
4. Index found in heap → `_serialize_value(val)` (line 521)
5. Index not found → `sym.to_dict()` (line 528)

- [ ] **Step 1: Migrate all return paths**

Replace each occurrence:
- `_serialize_value(element)` → `typed_from_runtime(element)` (lines 490, 498)
- `sym.to_dict()` → `typed(sym, UNKNOWN)` (lines 511, 528)
- `_serialize_value(val)` → `typed_from_runtime(val)` (line 521)

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All tests pass

- [ ] **Step 3: Format and commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "feat(typed-value): migrate _handle_load_index to TypedValue"
```

### Task 6: Migrate _handle_symbolic

**Files:**
- Modify: `interpreter/executor.py:247-271` (_handle_symbolic)

**Context:** 2 return paths:
1. Parameter bound by caller → `_serialize_value(val)` (line 261)
2. Create symbolic → `sym.to_dict()` (line 268)

- [ ] **Step 1: Migrate both return paths**

```python
# Line 261: register_writes={inst.result_reg: _serialize_value(val)},
register_writes={inst.result_reg: typed_from_runtime(val)},

# Line 268: register_writes={inst.result_reg: sym.to_dict()},
register_writes={inst.result_reg: typed(sym, UNKNOWN)},
```

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All tests pass

- [ ] **Step 3: Format and commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "feat(typed-value): migrate _handle_symbolic to TypedValue"
```

---

## Chunk 3: Object, operator, and region handlers

### Task 7: Migrate _handle_new_object, _handle_new_array, _handle_address_of

**Files:**
- Modify: `interpreter/executor.py:274-311` (_handle_new_object, _handle_new_array)
- Modify: `interpreter/executor.py:175-235` (_handle_address_of)

**Context:**
- `_handle_new_object` (line 293): heap address string → `typed(addr, UNKNOWN)` (object references, not strings)
- `_handle_new_array` (line 308): heap address string → `typed(addr, UNKNOWN)`
- `_handle_address_of` (lines 187, 205, 218, 232): Pointer objects and raw strings → wrap each

- [ ] **Step 1: Migrate _handle_new_object and _handle_new_array**

```python
# _handle_new_object line 293:
register_writes={inst.result_reg: typed(addr, UNKNOWN)},

# _handle_new_array line 308:
register_writes={inst.result_reg: typed(addr, UNKNOWN)},
```

- [ ] **Step 2: Migrate _handle_address_of**

```python
# Line 187 (already aliased Pointer):
register_writes={inst.result_reg: typed(ptr, scalar(TypeName.POINTER))},

# Line 205 (function ref, identity):
register_writes={inst.result_reg: typed_from_runtime(current_val)},

# Line 218 (existing heap object):
register_writes={inst.result_reg: typed(ptr, scalar(TypeName.POINTER))},

# Line 232 (promoted to heap):
register_writes={inst.result_reg: typed(ptr, scalar(TypeName.POINTER))},
```

Add `TypeName` to imports if not already imported:
```python
from interpreter.constants import TypeName
```

(`TypeName` may need to be imported from `interpreter.constants` — check what's already imported.)

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All tests pass

- [ ] **Step 4: Format and commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "feat(typed-value): migrate _handle_new_object, _handle_new_array, _handle_address_of to TypedValue"
```

### Task 8: Migrate _handle_binop

**Files:**
- Modify: `interpreter/executor.py:620-715` (_handle_binop)

**Context:** `_handle_binop` has 6 return paths:
1. Pointer diff (line 655) → raw int `diff`
2. Pointer compare (line 663) → raw `result`
3. Pointer arithmetic (line 679) → `result_ptr` Pointer
4. Symbolic short-circuit (line 692) → raw `sym` SymbolicValue
5. Uncomputable (line 706) → raw `sym` SymbolicValue
6. Computed result (line 712) → raw `result`

`_handle_binop` already uses `_resolve_binop_operand` which returns TypedValue, and uses `binop_coercion.result_type()` for type info. The result type can be computed from the coercion strategy.

- [ ] **Step 1: Migrate all return paths**

```python
# Line 655 (pointer diff):
register_writes={inst.result_reg: typed(diff, scalar(TypeName.INT))},

# Line 663 (pointer compare):
register_writes={inst.result_reg: typed(result, scalar(TypeName.BOOL))},

# Line 679 (pointer arithmetic):
register_writes={inst.result_reg: typed(result_ptr, scalar(TypeName.POINTER))},

# Line 692 (symbolic):
register_writes={inst.result_reg: typed(sym, UNKNOWN)},

# Line 706 (uncomputable symbolic):
register_writes={inst.result_reg: typed(sym, UNKNOWN)},

# Line 712 (computed):
register_writes={inst.result_reg: typed(result, binop_coercion.result_type(oper, lhs_typed, rhs_typed))},
```

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All tests pass

- [ ] **Step 3: Format and commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "feat(typed-value): migrate _handle_binop to TypedValue"
```

### Task 9: Migrate _handle_unop

**Files:**
- Modify: `interpreter/executor.py:718-758` (_handle_unop)

**Context:** 4 return paths:
1. Address-of identity (line 729) → raw `operand`
2. Symbolic (line 739) → `sym.to_dict()`
3. Uncomputable (line 749) → `sym.to_dict()`
4. Computed (line 755) → raw `result`

- [ ] **Step 1: Migrate all return paths**

```python
# Line 729 (address-of identity):
register_writes={inst.result_reg: typed_from_runtime(operand)},

# Line 739 (symbolic):
register_writes={inst.result_reg: typed(sym, UNKNOWN)},

# Line 749 (uncomputable):
register_writes={inst.result_reg: typed(sym, UNKNOWN)},

# Line 755 (computed):
register_writes={inst.result_reg: typed_from_runtime(result)},
```

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All tests pass

- [ ] **Step 3: Format and commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "feat(typed-value): migrate _handle_unop to TypedValue"
```

### Task 10: Migrate _handle_alloc_region and _handle_load_region

**Files:**
- Modify: `interpreter/executor.py:803-907` (_handle_alloc_region, _handle_load_region)

**Context:**
- `_handle_alloc_region`: symbolic size → `sym.to_dict()` (line 812); concrete → raw `addr` string (line 821)
- `_handle_load_region`: symbolic args → `sym.to_dict()` (line 884, 894); concrete → raw `data` list (line 904)

- [ ] **Step 1: Migrate all return paths**

```python
# _handle_alloc_region:
# Line 812 (symbolic): sym.to_dict() → typed(sym, UNKNOWN)
register_writes={inst.result_reg: typed(sym, UNKNOWN)},

# Line 821 (concrete addr): addr → typed(addr, UNKNOWN)
register_writes={inst.result_reg: typed(addr, UNKNOWN)},

# _handle_load_region:
# Line 884 (symbolic): sym.to_dict() → typed(sym, UNKNOWN)
register_writes={inst.result_reg: typed(sym, UNKNOWN)},

# Line 894 (unknown region): sym.to_dict() → typed(sym, UNKNOWN)
register_writes={inst.result_reg: typed(sym, UNKNOWN)},

# Line 904 (concrete data): data → typed(data, UNKNOWN)
register_writes={inst.result_reg: typed(data, UNKNOWN)},
```

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All tests pass

- [ ] **Step 3: Format and commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "feat(typed-value): migrate _handle_alloc_region and _handle_load_region to TypedValue"
```

---

## Chunk 4: Call handlers and cleanup

### Task 11: Migrate _try_builtin_call and _handle_call_function I/O path

**Files:**
- Modify: `interpreter/executor.py:913-942` (_try_builtin_call)
- Modify: `interpreter/executor.py:1091-1201` (_handle_call_function)

**Context:**
- `_try_builtin_call`: uncomputable → `sym.to_dict()` (line 930); computed → `_serialize_value(result)` (line 936)
- `_handle_call_function` I/O provider path: computed → `_serialize_value(result)` (line 1116); uncomputable → `sym.to_dict()` (line 1124)
- Scala apply / native call-index paths: `_serialize_value(element)` (lines 1155, 1173)

- [ ] **Step 1: Migrate _try_builtin_call**

```python
# Line 930 (uncomputable): sym.to_dict() → typed(sym, UNKNOWN)
register_writes={inst.result_reg: typed(sym, UNKNOWN)},

# Line 936 (computed): _serialize_value(result) → typed_from_runtime(result)
register_writes={inst.result_reg: typed_from_runtime(result)},
```

- [ ] **Step 2: Migrate _handle_call_function I/O and index paths**

```python
# Line 1116 (I/O provider result): _serialize_value(result) → typed_from_runtime(result)
register_writes={inst.result_reg: typed_from_runtime(result)},

# Line 1124 (I/O uncomputable): sym.to_dict() → typed(sym, UNKNOWN)
register_writes={inst.result_reg: typed(sym, UNKNOWN)},

# Line 1155 (Scala apply): _serialize_value(element) → typed_from_runtime(element)
register_writes={inst.result_reg: typed_from_runtime(element)},

# Line 1173 (native call-index): _serialize_value(element) → typed_from_runtime(element)
register_writes={inst.result_reg: typed_from_runtime(element)},
```

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All tests pass

- [ ] **Step 4: Format and commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "feat(typed-value): migrate _try_builtin_call and _handle_call_function I/O paths to TypedValue"
```

### Task 12: Migrate _try_class_constructor_call

**Files:**
- Modify: `interpreter/executor.py:945-1023` (_try_class_constructor_call)

**Context:** This handler produces both `register_writes` (heap address) and `var_writes` (constructor parameters):
- Line 985: register_writes → raw `addr` string (no __init__ path)
- Line 997: var_writes self/this → raw `addr` string
- Lines 1000, 1006: var_writes params → `_serialize_value(arg)`
- Line 1010: register_writes → raw `addr` string (with __init__ path)

- [ ] **Step 1: Migrate register_writes and var_writes**

```python
# Line 985 (no __init__):
register_writes={inst.result_reg: typed(addr, UNKNOWN)},

# Line 997 (self/this):
new_vars[params[0]] = typed(addr, UNKNOWN)
# ... or for Java-style:
new_vars[constants.PARAM_THIS] = typed(addr, UNKNOWN)

# Lines 1000, 1006 (params):
new_vars[params[i + 1]] = typed_from_runtime(arg)
# ... or for Java-style:
new_vars[params[i]] = typed_from_runtime(arg)

# Line 1010 (with __init__):
register_writes={inst.result_reg: typed(addr, UNKNOWN)},
```

The full replacement for the var_writes section:
```python
    if has_explicit_self:
        new_vars[params[0]] = typed(addr, UNKNOWN)
        for i, arg in enumerate(args):
            if i + 1 < len(params):
                new_vars[params[i + 1]] = typed_from_runtime(arg)
    else:
        new_vars[constants.PARAM_THIS] = typed(addr, UNKNOWN)
        for i, arg in enumerate(args):
            if i < len(params):
                new_vars[params[i]] = typed_from_runtime(arg)
```

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All tests pass

- [ ] **Step 3: Format and commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "feat(typed-value): migrate _try_class_constructor_call to TypedValue"
```

### Task 13: Migrate _try_user_function_call

**Files:**
- Modify: `interpreter/executor.py:1026-1085` (_try_user_function_call)

**Context:** Produces only `var_writes` (parameter bindings and closure captures):
- Line 1046: params → `_serialize_value(arg)`
- Line 1051: arguments array → `_builtin_array_of([_serialize_value(a) ...])` — returns a heap address string
- Line 1061: closure captures → `_serialize_value(v)` for each captured variable

- [ ] **Step 1: Migrate var_writes**

```python
    params = registry.func_params.get(flabel, [])
    param_vars = {
        params[i]: typed_from_runtime(arg)
        for i, arg in enumerate(args)
        if i < len(params)
    }
    # arguments array: _builtin_array_of returns a heap address string
    param_vars["arguments"] = typed(_builtin_array_of(list(args), vm), UNKNOWN)

    # Closure captures
    closure_env: ClosureEnvironment | None = None
    captured: dict[str, Any] = {}
    if fr.closure_id:
        closure_env = vm.closures.get(fr.closure_id)
        if closure_env:
            captured = closure_env.bindings

    new_vars = {k: typed_from_runtime(v) for k, v in captured.items()} if captured else {}
    new_vars.update(param_vars)
```

Note: `_builtin_array_of` no longer receives `_serialize_value`-wrapped args. Since `_builtin_array_of` writes raw values to heap fields (which stay raw per spec), and the args to builtin functions are raw values from `_resolve_reg`, we pass them directly. The args list elements here are already raw (resolved from registers).

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All tests pass

- [ ] **Step 3: Format and commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "feat(typed-value): migrate _try_user_function_call to TypedValue"
```

### Task 14: Migrate _handle_call_method

**Files:**
- Modify: `interpreter/executor.py:1204-1312` (_handle_call_method)

**Context:**
- Line 1234: method builtin result → `_serialize_value(result)`
- Line 1291: var_writes self/this → `_serialize_value(obj_val)`
- Line 1294: var_writes params → `_serialize_value(arg)`
- Line 1296: arguments array → `_builtin_array_of([_serialize_value(a) ...])`

- [ ] **Step 1: Migrate register_writes and var_writes**

```python
# Line 1234 (method builtin):
register_writes={inst.result_reg: typed_from_runtime(result)},

# Lines 1288-1296 (method dispatch var_writes):
    params = registry.func_params.get(func_label, [])
    new_vars: dict[str, Any] = {}
    if params:
        new_vars[params[0]] = typed_from_runtime(obj_val)
    for i, arg in enumerate(args):
        if i + 1 < len(params):
            new_vars[params[i + 1]] = typed_from_runtime(arg)
    new_vars["arguments"] = typed(_builtin_array_of(list(args), vm), UNKNOWN)
```

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All tests pass

- [ ] **Step 3: Format and commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "feat(typed-value): migrate _handle_call_method to TypedValue"
```

### Task 15: Remove _serialize_value from executor.py and final cleanup

**Files:**
- Modify: `interpreter/executor.py` (imports)

**Context:** After all handlers are migrated, `_serialize_value` should no longer be used in executor.py. It may still be used in `_handle_store_field`, `_handle_store_index`, and `_handle_return` for `heap_writes` and `return_value` which stay raw (out of scope).

- [ ] **Step 1: Check remaining _serialize_value usages**

Run: `grep -n _serialize_value interpreter/executor.py`

Expected remaining usages (heap_writes and return_value — out of scope):
- `_handle_store_field` (lines 330, 355) — heap_writes
- `_handle_store_index` (line 468) — heap_writes
- `_handle_return` (line 538) — return_value

If there are other usages, migrate them first.

- [ ] **Step 2: Verify _serialize_value is only used for out-of-scope paths**

If the remaining usages are only `heap_writes` and `return_value`, `_serialize_value` must stay in the import. Do NOT remove it yet. Update the import comment:

```python
from interpreter.vm import (
    ...
    _serialize_value,  # used for heap_writes and return_value (stays raw until red-dragon-gny/n9m)
    ...
)
```

- [ ] **Step 3: Update execution loop to skip materialize_raw_update for local path**

Now that all handlers produce TypedValue, update `execute_cfg` and `execute_cfg_traced` to only call `materialize_raw_update` for the LLM path:

```python
        if result.handled:
            update = result.update  # already has TypedValue
        else:
            if llm is None:
                llm = get_backend(config.backend)
            raw_update = llm.interpret_instruction(instruction, vm)
            update = materialize_raw_update(raw_update, vm, type_env, conversion_rules)
            used_llm = True
            llm_calls += 1
```

Apply the same change in `execute_cfg_traced`. (`_handle_call_dispatch_setup` receives pre-materialized updates from the caller — no changes needed there.)

- [ ] **Step 4: Run full test suite**

Run: `poetry run python -m pytest -x --timeout=60`
Expected: All 11,400+ tests pass

- [ ] **Step 5: Format and commit**

```bash
poetry run python -m black .
git add interpreter/executor.py interpreter/run.py
git commit -m "feat(typed-value): complete handler migration, skip materialize for local path

All executor handlers now produce TypedValue directly.
materialize_raw_update only called for LLM responses."
```

### Task 16: Update README and close issue

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README with TypedValue migration status**

Add a note in the relevant section about the TypedValue migration being complete for handlers.

- [ ] **Step 2: Close the Beads issue**

```bash
bd update red-dragon-132 --status closed
```

- [ ] **Step 3: Final commit and push**

```bash
git add README.md
git commit -m "docs: update README for handler TypedValue migration"
git push origin main
```
