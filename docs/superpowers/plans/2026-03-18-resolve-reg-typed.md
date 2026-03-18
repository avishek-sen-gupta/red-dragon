# Fix _resolve_reg() TypedValue Unwrapping — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change `_resolve_reg()` to return `TypedValue` instead of bare values, preserving parameterized type information (e.g., `pointer(scalar("Dog"))`) through the register→handler→storage pipeline.

**Architecture:** Modify the single function `_resolve_reg` in `interpreter/vm.py` to return `TypedValue`. Update all 26 callers: 7 "write" callsites drop their redundant `typed_from_runtime()` wrapping, 19 "read" callsites add `.value` to extract bare values. Delete the now-redundant `_resolve_binop_operand` and replace its 8 callsites with `_resolve_reg`.

**Tech Stack:** Python 3.13+, pytest, poetry

**Spec:** `docs/superpowers/specs/2026-03-18-resolve-reg-typed-design.md`

---

### Task 1: Unit tests for `_resolve_reg` returning `TypedValue`

**Files:**
- Create: `tests/unit/test_resolve_reg_typed.py`

These tests define the new contract: `_resolve_reg` returns `TypedValue`, preserving parameterized types.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for _resolve_reg returning TypedValue."""

from interpreter.vm import _resolve_reg, VMState
from interpreter.vm_types import Pointer, StackFrame
from interpreter.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.type_expr import pointer, scalar, UNKNOWN


def _make_vm(**registers: object) -> VMState:
    """Create a minimal VMState with the given registers."""
    frame = StackFrame(function_name="test")
    frame.registers.update(registers)
    return VMState(call_stack=[frame])


class TestResolveRegReturnsTypedValue:
    def test_returns_typed_value_for_typed_register(self):
        """A register holding a TypedValue should be returned as-is."""
        tv = typed(Pointer(base="obj_0", offset=0), pointer(scalar("Dog")))
        vm = _make_vm(**{"%0": tv})
        result = _resolve_reg(vm, "%0")
        assert isinstance(result, TypedValue)
        assert result is tv

    def test_preserves_parameterized_type(self):
        """pointer(scalar('Dog')) must survive the resolve."""
        expected_type = pointer(scalar("Dog"))
        tv = typed(Pointer(base="obj_0", offset=0), expected_type)
        vm = _make_vm(**{"%0": tv})
        result = _resolve_reg(vm, "%0")
        assert result.type == expected_type

    def test_wraps_bare_register_value_via_typed_from_runtime(self):
        """A register holding a bare int should be wrapped as TypedValue."""
        vm = _make_vm(**{"%0": 42})
        result = _resolve_reg(vm, "%0")
        assert isinstance(result, TypedValue)
        assert result.value == 42

    def test_wraps_non_register_operand(self):
        """A non-register operand (e.g., literal string) is wrapped."""
        vm = _make_vm()
        result = _resolve_reg(vm, "hello")
        assert isinstance(result, TypedValue)
        assert result.value == "hello"

    def test_wraps_missing_register(self):
        """An unset register returns the register name wrapped."""
        vm = _make_vm()
        result = _resolve_reg(vm, "%99")
        assert isinstance(result, TypedValue)
        assert result.value == "%99"

    def test_bare_pointer_in_register_gets_unknown_type(self):
        """A bare Pointer (not wrapped in TypedValue) gets UNKNOWN type."""
        vm = _make_vm(**{"%0": Pointer(base="obj_0", offset=0)})
        result = _resolve_reg(vm, "%0")
        assert isinstance(result, TypedValue)
        assert isinstance(result.value, Pointer)
        assert result.type == UNKNOWN
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_resolve_reg_typed.py -v`
Expected: FAIL — `_resolve_reg` currently returns bare values, not `TypedValue`

- [ ] **Step 3: Commit test-only**

```bash
git add tests/unit/test_resolve_reg_typed.py
git commit -m "test: add unit tests for _resolve_reg returning TypedValue"
```

---

### Task 2: Change `_resolve_reg` to return `TypedValue` + update all callers

This is the core change. Because all callers depend on `_resolve_reg`'s return type, they must all be updated atomically for the test suite to pass.

**Files:**
- Modify: `interpreter/vm.py:329-340` (the `_resolve_reg` definition)
- Modify: `interpreter/vm.py:383-395` (`_resolve_typed_reg` — internal caller)
- Modify: `interpreter/executor.py` (24 callsites)
- Modify: `interpreter/backend.py:95` (1 callsite)

#### 2A: Change `_resolve_reg` in `vm.py`

- [ ] **Step 4: Modify `_resolve_reg` to return `TypedValue`**

In `interpreter/vm.py`, replace lines 329-340:

```python
def _resolve_reg(vm: VMState, operand: str) -> TypedValue:
    """Resolve a register name to its TypedValue.

    Returns the TypedValue as-is if the register holds one, otherwise
    wraps the raw value via typed_from_runtime().
    """
    if isinstance(operand, str) and operand.startswith("%"):
        frame = vm.current_frame
        val = frame.registers.get(operand, operand)
        if isinstance(val, TypedValue):
            return val
        return typed_from_runtime(val)
    return typed_from_runtime(operand)
```

Also update the return type annotation import if needed. The function signature changes from `-> Any` to `-> TypedValue`.

- [ ] **Step 5: Update `_resolve_typed_reg` in `vm.py:394`**

In `interpreter/vm.py`, line 394 currently reads:
```python
val = _resolve_reg(vm, operand)
return _coerce_value(val, operand, type_env, conversion_rules)
```

Change to:
```python
val = _resolve_reg(vm, operand).value
return _coerce_value(val, operand, type_env, conversion_rules)
```

`_coerce_value` calls `runtime_type_name(val)` which expects a bare value.

#### 2B: Update 6 write callsites — drop `typed_from_runtime`

These callsites currently re-wrap with `typed_from_runtime()`. Since `_resolve_reg` now returns `TypedValue`, use it directly.

- [ ] **Step 6: Update `_handle_decl_var` (executor.py:187-191)**

Before:
```python
val = _resolve_reg(vm, inst.operands[1])
return ExecutionResult.success(
    StateUpdate(
        var_writes={name: typed_from_runtime(val)},
        reasoning=f"decl {name} = {val!r}",
    )
)
```

After:
```python
tv = _resolve_reg(vm, inst.operands[1])
return ExecutionResult.success(
    StateUpdate(
        var_writes={name: tv},
        reasoning=f"decl {name} = {tv.value!r}",
    )
)
```

- [ ] **Step 7: Update `_handle_store_var` (executor.py:216-241)**

Before:
```python
val = _resolve_reg(vm, inst.operands[1])
tv = typed_from_runtime(val)
```

After:
```python
tv = _resolve_reg(vm, inst.operands[1])
```

Delete the `tv = typed_from_runtime(val)` line. The variable `tv` is now assigned directly from `_resolve_reg`.

Also update the three reasoning strings on lines 223, 232, 239 from `{val!r}` to `{tv.value!r}`.

- [ ] **Step 8: Update `_handle_store_indirect` (executor.py:422, 431)**

Line 422 is a **write** callsite. Change:
```python
val = _resolve_reg(vm, inst.operands[1])
```
to:
```python
tv = _resolve_reg(vm, inst.operands[1])
```

And line 431 change `typed_from_runtime(val)` to just `tv`:
```python
value=tv,
```

Update reasoning on line 434 from `{val!r}` to `{tv.value!r}`.

- [ ] **Step 9: Update `_handle_store_field` (executor.py:534, 554)**

Line 534 is a **write** callsite. Change:
```python
val = _resolve_reg(vm, inst.operands[2])
```
to:
```python
tv = _resolve_reg(vm, inst.operands[2])
```

Line 554 change `typed_from_runtime(val)` to `tv`:
```python
value=tv,
```

Update reasoning strings on lines 545 and 557 from `{val!r}` to `{tv.value!r}`.

- [ ] **Step 10: Update `_handle_store_index` (executor.py:685, 705)**

Line 685 is a **write** callsite. Change:
```python
val = _resolve_reg(vm, inst.operands[2])
```
to:
```python
tv = _resolve_reg(vm, inst.operands[2])
```

Line 705 change `typed_from_runtime(val)` to `tv`:
```python
value=tv,
```

Update reasoning strings on lines 696 and 708 from `{val!r}` to `{tv.value!r}`.

- [ ] **Step 11: Update `_handle_return` (executor.py:775-776)**

Before:
```python
val = _resolve_reg(vm, inst.operands[0])
tv = typed_from_runtime(val)
```

After:
```python
tv = _resolve_reg(vm, inst.operands[0])
```

Delete the `tv = typed_from_runtime(val)` line. `tv` is now assigned directly.

#### 2C: Update 18 read callsites — add `.value`

These callsites need bare values for `_heap_addr()`, `isinstance()`, `bool()`, `int()`, dict lookups, list indexing, `_is_symbolic()`, `_serialize_value()`.

- [ ] **Step 12: Update `_handle_load_indirect` (executor.py:327)**

```python
obj_val = _resolve_reg(vm, inst.operands[0]).value
```

- [ ] **Step 13: Update `_handle_load_field_indirect` (executor.py:373-374)**

```python
obj_val = _resolve_reg(vm, inst.operands[0]).value
field_name = _resolve_reg(vm, inst.operands[1]).value
```

- [ ] **Step 14: Update `_handle_store_indirect` read callsite (executor.py:421)**

Line 421 is a **read** callsite (the object pointer, not the value being stored):
```python
obj_val = _resolve_reg(vm, inst.operands[0]).value
```

- [ ] **Step 15: Update `_handle_store_field` read callsite (executor.py:532)**

```python
obj_val = _resolve_reg(vm, inst.operands[0]).value
```

- [ ] **Step 16: Update `_handle_load_field` (executor.py:630)**

```python
obj_val = _resolve_reg(vm, inst.operands[0]).value
```

- [ ] **Step 17: Update `_handle_store_index` read callsites (executor.py:683-684)**

```python
arr_val = _resolve_reg(vm, inst.operands[0]).value
idx_val = _resolve_reg(vm, inst.operands[1]).value
```

- [ ] **Step 18: Update `_handle_load_index` (executor.py:716-717)**

```python
arr_val = _resolve_reg(vm, inst.operands[0]).value
idx_val = _resolve_reg(vm, inst.operands[1]).value
```

- [ ] **Step 19: Update `_handle_throw` (executor.py:789)**

```python
val = _resolve_reg(vm, inst.operands[0]).value if inst.operands else None
```

- [ ] **Step 20: Update `_handle_branch_if` (executor.py:835)**

```python
cond_val = _resolve_reg(vm, inst.operands[0]).value
```

- [ ] **Step 21: Update `_handle_alloc_region` (executor.py:1057)**

```python
size = _resolve_reg(vm, inst.operands[0]).value
```

- [ ] **Step 22: Update `_handle_write_region` (executor.py:1084-1087)**

```python
region_addr = _resolve_reg(vm, inst.operands[0]).value
offset = _resolve_reg(vm, inst.operands[1]).value
...
value = _resolve_reg(vm, inst.operands[3]).value
```

- [ ] **Step 23: Update `_handle_load_region` (executor.py:1126-1127)**

```python
region_addr = _resolve_reg(vm, inst.operands[0]).value
offset = _resolve_reg(vm, inst.operands[1]).value
```

- [ ] **Step 24: Update `backend.py:95`**

Before:
```python
val = _resolve_reg(state, op)
if val is not raw:  # was a register reference
    resolved[str(op)] = _serialize_value(val)
```

After:
```python
tv = _resolve_reg(state, op)
if tv.value is not raw:  # was a register reference
    resolved[str(op)] = _serialize_value(tv.value)
```

#### 2D: Remove `typed_from_runtime` import from executor.py if now unused

- [ ] **Step 25: Check and clean up imports**

After removing `typed_from_runtime` from all write callsites, check if `executor.py` still imports it. If only the 6 write callsites used it and no other callsites remain, remove the import. If other callsites in executor.py still use `typed_from_runtime` (e.g., `_handle_load_index` line 727 for native indexing, or `_unwrap_builtin_result`), keep the import.

Run: `poetry run python -m pytest tests/unit/test_resolve_reg_typed.py -v`
Expected: PASS — the new unit tests should now pass.

- [ ] **Step 26: Run the full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All ~11944 tests pass.

- [ ] **Step 27: Format and commit**

```bash
poetry run python -m black .
git add interpreter/vm.py interpreter/executor.py interpreter/backend.py
git commit -m "feat: make _resolve_reg return TypedValue, preserving parameterized types

Downstream handlers that store values (DECL_VAR, STORE_VAR, STORE_FIELD,
etc.) no longer lose type info by re-wrapping through typed_from_runtime().
Read callsites extract .value for bare-value operations."
```

---

### Task 3: Delete `_resolve_binop_operand` and replace its 8 callsites

Now that `_resolve_reg` returns `TypedValue` (identical behavior to `_resolve_binop_operand`), the latter is redundant.

**Files:**
- Modify: `interpreter/vm.py:343-355` (delete `_resolve_binop_operand`)
- Modify: `interpreter/executor.py` (8 callsites)

- [ ] **Step 28: Replace all 8 callsites in executor.py**

Replace every `_resolve_binop_operand(` with `_resolve_reg(` in these locations:

| Line | Handler | Code |
|------|---------|------|
| 866 | `_handle_binop` | `lhs_typed = _resolve_reg(vm, inst.operands[1])` |
| 867 | `_handle_binop` | `rhs_typed = _resolve_reg(vm, inst.operands[2])` |
| 960 | `_handle_unop` | `operand_typed = _resolve_reg(vm, inst.operands[1])` |
| 1377 | `_handle_call_function` | `args = [_resolve_reg(vm, a) for a in arg_regs]` |
| 1500 | `_handle_call_method` | `obj_val = _resolve_reg(vm, inst.operands[0])` |
| 1503 | `_handle_call_method` | `args = [_resolve_reg(vm, a) for a in arg_regs]` |
| 1649 | `_handle_call_unknown` | `target_val = _resolve_reg(vm, inst.operands[0])` |
| 1651 | `_handle_call_unknown` | `args = [_resolve_reg(vm, a) for a in arg_regs]` |

Also remove `_resolve_binop_operand` from the import line in executor.py:
```python
from interpreter.vm import VMState, StateUpdate, _resolve_reg, _serialize_value
```
(Remove `_resolve_binop_operand` from the import list.)

- [ ] **Step 29: Delete `_resolve_binop_operand` definition in vm.py:343-355**

Delete the entire function:
```python
def _resolve_binop_operand(vm: VMState, operand: str) -> TypedValue:
    ...
```

- [ ] **Step 30: Run the full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All ~11944 tests pass.

- [ ] **Step 31: Format and commit**

```bash
poetry run python -m black .
git add interpreter/vm.py interpreter/executor.py
git commit -m "refactor: delete redundant _resolve_binop_operand, use _resolve_reg

_resolve_reg now returns TypedValue, making _resolve_binop_operand
identical. Replace all 8 callsites."
```

---

### Task 4: Integration tests for type preservation

**Files:**
- Create: `tests/integration/test_resolve_reg_type_preservation.py`

These tests verify the end-to-end fix: parameterized types survive from NEW_OBJECT through DECL_VAR to `local_vars`.

- [ ] **Step 32: Write integration tests**

```python
"""Integration tests: parameterized types survive through _resolve_reg pipeline."""

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import TypedValue
from interpreter.type_expr import pointer, scalar
from interpreter.vm_types import Pointer


def _typed_locals(vm):
    """Return local_vars dict preserving TypedValue wrappers."""
    return vm.call_stack[0].local_vars


class TestTypePreservationThroughResolveReg:
    def test_java_new_object_preserves_pointer_type(self):
        """pointer(scalar('Dog')) must survive NEW_OBJECT → DECL_VAR → local_vars."""
        vm = run("class Dog {} Dog d = new Dog();", language=Language.JAVA, max_steps=100)
        tv = _typed_locals(vm)["d"]
        assert isinstance(tv, TypedValue)
        assert isinstance(tv.value, Pointer)
        assert tv.type == pointer(scalar("Dog"))

    def test_python_class_preserves_pointer_type(self):
        vm = run(
            "class Cat:\n    pass\nc = Cat()\n",
            language=Language.PYTHON,
            max_steps=100,
        )
        tv = _typed_locals(vm)["c"]
        assert isinstance(tv, TypedValue)
        assert isinstance(tv.value, Pointer)
        assert tv.type == pointer(scalar("Cat"))

    def test_store_var_preserves_type_through_reassignment(self):
        """Type must survive a STORE_VAR (reassignment), not just DECL_VAR."""
        vm = run(
            "class Foo {} Foo x = new Foo(); Foo y = x;",
            language=Language.JAVA,
            max_steps=100,
        )
        tv_x = _typed_locals(vm)["x"]
        tv_y = _typed_locals(vm)["y"]
        assert tv_x.type == pointer(scalar("Foo"))
        assert tv_y.type == pointer(scalar("Foo"))

    def test_array_preserves_pointer_type(self):
        """Array pointer type should be preserved too."""
        vm = run("x = [1, 2, 3]\n", language=Language.PYTHON, max_steps=100)
        tv = _typed_locals(vm)["x"]
        assert isinstance(tv, TypedValue)
        assert isinstance(tv.value, Pointer)
        assert tv.type == pointer(scalar("Array"))

    def test_return_value_preserves_type(self):
        """Return value through RETURN should preserve TypedValue."""
        code = """\
class Box {}
Box make() { return new Box(); }
Box b = make();
"""
        vm = run(code, language=Language.JAVA, max_steps=200)
        tv = _typed_locals(vm)["b"]
        assert isinstance(tv, TypedValue)
        assert isinstance(tv.value, Pointer)
        assert tv.type == pointer(scalar("Box"))
```

- [ ] **Step 33: Run integration tests**

Run: `poetry run python -m pytest tests/integration/test_resolve_reg_type_preservation.py -v`
Expected: PASS

- [ ] **Step 34: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass (count should be ~11944 + new tests).

- [ ] **Step 35: Format and commit**

```bash
poetry run python -m black .
git add tests/unit/test_resolve_reg_typed.py tests/integration/test_resolve_reg_type_preservation.py
git commit -m "test: add integration tests for TypedValue type preservation through pipeline"
```

---

### Task 5: Update test count in MEMORY.md and close beads issue

**Files:**
- Modify: `/Users/asgupta/.claude/projects/-Users-asgupta-code-red-dragon/memory/MEMORY.md`

- [ ] **Step 36: Run full test suite and note final count**

Run: `poetry run python -m pytest --tb=short -q`
Record the exact passing count.

- [ ] **Step 37: Update MEMORY.md test count**

Update the test count line in MEMORY.md to reflect the new total.

- [ ] **Step 38: Close beads issue**

```bash
bd update red-dragon-s47a --status closed
```

- [ ] **Step 39: Final commit**

```bash
git add -A
git commit -m "chore: update test count and close beads issue red-dragon-s47a"
```
