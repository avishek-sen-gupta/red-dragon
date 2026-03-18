# Pointer Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate all heap object references from bare string addresses to `Pointer` objects with correct parameterized types on `TypedValue`.

**Architecture:** Bottom-up incremental. First make consumers Pointer-ready (`_heap_addr()` shim), then unify dual code paths in LOAD_FIELD/STORE_FIELD, then convert creation sites one by one. Each step is independently testable with all 11909 tests staying green.

**Tech Stack:** Python 3.13+, `Pointer` dataclass in `interpreter/vm_types.py`, `pointer(scalar(...))` type expression in `interpreter/type_expr.py`.

**Spec:** `docs/superpowers/specs/2026-03-18-pointer-migration-design.md`

---

### Task 1: Update `_heap_addr()` to handle Pointer objects

**Files:**
- Modify: `interpreter/vm.py:306-324`
- Test: `tests/unit/test_heap_addr_pointer.py` (create)

- [ ] **Step 1: Write the failing test**

```python
"""Tests for _heap_addr() Pointer support."""

from interpreter.vm import _heap_addr
from interpreter.vm_types import Pointer, SymbolicValue


class TestHeapAddrPointer:
    def test_extracts_base_from_pointer(self):
        p = Pointer(base="obj_0", offset=0)
        assert _heap_addr(p) == "obj_0"

    def test_extracts_base_from_pointer_with_offset(self):
        p = Pointer(base="arr_5", offset=3)
        assert _heap_addr(p) == "arr_5"

    def test_still_handles_bare_string(self):
        assert _heap_addr("obj_0") == "obj_0"

    def test_still_handles_symbolic_value(self):
        sym = SymbolicValue(name="sym_0")
        assert _heap_addr(sym) == "sym_0"

    def test_returns_empty_for_int(self):
        assert _heap_addr(42) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_heap_addr_pointer.py -v`
Expected: FAIL on `test_extracts_base_from_pointer` — `_heap_addr(Pointer(...))` returns `""`.

- [ ] **Step 3: Add Pointer branch to `_heap_addr()`**

In `interpreter/vm.py`, add before the `isinstance(val, str)` check:

```python
if isinstance(val, Pointer):
    return val.base
```

Add import: `from interpreter.vm_types import Pointer` (if not already imported).

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_heap_addr_pointer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: 11909 passed (zero behavior change — nothing produces Pointers yet)

- [ ] **Step 6: Commit**

```bash
poetry run python -m black .
git add interpreter/vm.py tests/unit/test_heap_addr_pointer.py
git commit -m "feat: make _heap_addr() handle Pointer objects for migration readiness"
```

---

### Task 2: Unify LOAD_FIELD — delete Pointer early-return branches

The `isinstance(obj_val, Pointer)` early-return branches (lines 629-647) skip `__method_missing__`, Box delegation, and symbolic caching. Delete them so all objects flow through the unified `_heap_addr()` path.

**Files:**
- Modify: `interpreter/executor.py:618-693`
- Test: existing tests (no new tests — behavior must stay identical)

- [ ] **Step 1: Delete the Pointer early-return branches**

In `_handle_load_field`, delete lines 628-647 (the two `isinstance(obj_val, Pointer)` blocks):

```python
    # DELETE THIS BLOCK (lines 628-647):
    # Pointer field/dereference access
    if isinstance(obj_val, Pointer) and obj_val.base in vm.heap:
        heap_obj = vm.heap[obj_val.base]
        # ptr->field — struct pointer field access (reads field from the object)
        if field_name in heap_obj.fields:
            tv = heap_obj.fields[field_name]
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: tv},
                    reasoning=f"load {obj_val.base}.{field_name} = {tv!r} (via Pointer)",
                )
            )
    if isinstance(obj_val, Pointer) and obj_val.base not in vm.heap:
        sym = vm.fresh_symbolic(hint=f"*{obj_val}")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"load *{obj_val} (not on heap) → {sym.name}",
            )
        )
```

The `_heap_addr()` path (line 648+) now handles everything — including Pointers, since Task 1 updated `_heap_addr()`.

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL PASS — the unified path is a strict superset of the Pointer branch. One semantic improvement: repeated LOAD_FIELD on a Pointer-not-on-heap object now returns the same cached symbolic value (deduplication) instead of a fresh symbolic each time. This is better behavior.

- [ ] **Step 3: Commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "refactor: unify LOAD_FIELD by removing Pointer early-return branches"
```

---

### Task 3: Unify STORE_FIELD — delete Pointer early-return branch

Same as Task 2 but for `_handle_store_field`. The Pointer branch (lines 517-529) skips synthetic heap materialisation.

**Files:**
- Modify: `interpreter/executor.py:510-555`
- Test: existing tests

- [ ] **Step 1: Delete the Pointer early-return branch**

In `_handle_store_field`, delete lines 516-529:

```python
    # DELETE THIS BLOCK (lines 516-529):
    # Pointer field/dereference write
    if isinstance(obj_val, Pointer):
        target_field = field_name
        return ExecutionResult.success(
            StateUpdate(
                heap_writes=[
                    HeapWrite(
                        obj_addr=obj_val.base,
                        field=target_field,
                        value=typed_from_runtime(val),
                    )
                ],
                reasoning=f"store {obj_val.base}.{target_field} = {val!r} (via Pointer)",
            )
        )
```

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "refactor: unify STORE_FIELD by removing Pointer early-return branch"
```

---

### Task 4: Convert `NEW_OBJECT` and `_try_class_constructor_call` to produce Pointer

These MUST be converted together — most class instantiation goes through `_try_class_constructor_call`, not `_handle_new_object`. Converting only one would leave mixed Pointer/string state.

**Files:**
- Modify: `interpreter/executor.py:472-492,1262-1295`
- Modify: `tests/unit/test_class_instantiation.py:94-96,174-176`
- Test: `tests/unit/test_new_object_pointer.py` (create)

- [ ] **Step 1: Write the failing test**

```python
"""Tests that NEW_OBJECT produces a Pointer with correct parameterized type."""

from interpreter.executor import LocalExecutor
from interpreter.ir import IRInstruction, Opcode
from interpreter.vm import VMState
from interpreter.vm_types import Pointer, StackFrame, StateUpdate
from interpreter.type_expr import pointer, scalar
from interpreter.typed_value import unwrap


class TestNewObjectPointer:
    def test_result_is_pointer(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="<main>"))
        inst = IRInstruction(
            opcode=Opcode.NEW_OBJECT,
            result_reg="%obj",
            operands=["Point"],
        )
        result = LocalExecutor.execute(inst=inst, vm=vm)
        assert result.handled
        tv = result.update.register_writes["%obj"]
        assert isinstance(tv.value, Pointer)
        assert tv.value.base.startswith("obj_")
        assert tv.value.offset == 0
        assert tv.type == pointer(scalar("Point"))

    def test_no_type_hint_uses_object(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="<main>"))
        inst = IRInstruction(
            opcode=Opcode.NEW_OBJECT,
            result_reg="%obj",
            operands=[],
        )
        result = LocalExecutor.execute(inst=inst, vm=vm)
        tv = result.update.register_writes["%obj"]
        assert isinstance(tv.value, Pointer)
        assert tv.type == pointer(scalar("Object"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_new_object_pointer.py -v`
Expected: FAIL — `tv.value` is a string, not a Pointer.

- [ ] **Step 3: Update `_handle_new_object`**

In `interpreter/executor.py`, change `_handle_new_object` (line 486-489):

From:
```python
register_writes={inst.result_reg: typed(addr, UNKNOWN)},
```

To:
```python
register_writes={inst.result_reg: typed(
    Pointer(base=addr, offset=0),
    pointer(scalar(type_hint or "Object")),
)},
```

Add imports at top of file: `from interpreter.type_expr import pointer` (if not present; `scalar` and `UNKNOWN` should already be imported).

- [ ] **Step 4: Run new test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_new_object_pointer.py -v`
Expected: PASS

- [ ] **Step 5: Fix `test_class_instantiation.py` assertions**

In `tests/unit/test_class_instantiation.py`, update both test methods:

Line 95-96 (Java test) — replace:
```python
assert isinstance(vars_["d"], str)
assert vars_["d"].startswith("obj_")
```
with:
```python
assert isinstance(vars_["d"], Pointer)
assert vars_["d"].base.startswith("obj_")
```

Line 175-176 (JavaScript test) — same replacement.

Line 98 — replace:
```python
assert vm.heap[vars_["d"]].type_hint == "Dog"
```
with:
```python
assert vm.heap[vars_["d"].base].type_hint == "Dog"
```

Line 178 — replace:
```python
heap_obj = vm.heap[vars_["d"]]
```
with:
```python
heap_obj = vm.heap[vars_["d"].base]
```

Add import: `from interpreter.vm_types import Pointer`

- [ ] **Step 6: Update `_try_class_constructor_call` — all 4 bare-address writes**

In `_try_class_constructor_call`, create a shared typed pointer value after line 1265:
```python
ptr_tv = typed(Pointer(base=addr, offset=0), pointer(type_hint))
```

Then replace all 4 occurrences of `typed(addr, UNKNOWN)`:

Line 1270 (no-init path `register_writes`):
```python
register_writes={inst.result_reg: ptr_tv},
```

Line 1282 (explicit self/this):
```python
new_vars[params[0]] = ptr_tv
```

Line 1288 (implicit this):
```python
new_vars[constants.PARAM_THIS] = ptr_tv
```

Line 1295 (with-init path `register_writes`):
```python
register_writes={inst.result_reg: ptr_tv},
```

- [ ] **Step 7: Run full test suite and fix any other breakages**

Run: `poetry run python -m pytest --tb=short -q`

This is the biggest change — both `NEW_OBJECT` and constructor calls now produce Pointers. Expect some test failures where tests unwrap local vars and check heap addresses. For each failure:
- If the test does `vm.heap[vars_["x"]]`, change to `vm.heap[vars_["x"].base]`
- If the test does `isinstance(vars_["x"], str)`, change to `isinstance(vars_["x"], Pointer)`
- If the test does `vars_["x"].startswith("obj_")`, change to `vars_["x"].base.startswith("obj_")`

- [ ] **Step 8: Commit**

```bash
poetry run python -m black .
git add interpreter/executor.py tests/
git commit -m "feat: NEW_OBJECT and _try_class_constructor_call produce Pointer with parameterized type"
```

---

### Task 5: Convert `NEW_ARRAY` to produce Pointer

**Files:**
- Modify: `interpreter/executor.py:495-507`
- Modify: `tests/unit/test_array_of_builtin_result.py` (if it tests NEW_ARRAY)
- Test: `tests/unit/test_new_array_pointer.py` (create)

- [ ] **Step 1: Write the failing test**

```python
"""Tests that NEW_ARRAY produces a Pointer with correct parameterized type."""

from interpreter.executor import LocalExecutor
from interpreter.ir import IRInstruction, Opcode
from interpreter.vm import VMState
from interpreter.vm_types import Pointer, StackFrame
from interpreter.type_expr import pointer, scalar


class TestNewArrayPointer:
    def test_result_is_pointer(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="<main>"))
        inst = IRInstruction(
            opcode=Opcode.NEW_ARRAY,
            result_reg="%arr",
            operands=["int"],
        )
        result = LocalExecutor.execute(inst=inst, vm=vm)
        tv = result.update.register_writes["%arr"]
        assert isinstance(tv.value, Pointer)
        assert tv.value.base.startswith("arr_")
        assert tv.value.offset == 0
        assert tv.type == pointer(scalar("int"))

    def test_no_type_hint_uses_array(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="<main>"))
        inst = IRInstruction(
            opcode=Opcode.NEW_ARRAY,
            result_reg="%arr",
            operands=[],
        )
        result = LocalExecutor.execute(inst=inst, vm=vm)
        tv = result.update.register_writes["%arr"]
        assert isinstance(tv.value, Pointer)
        assert tv.type == pointer(scalar("Array"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_new_array_pointer.py -v`
Expected: FAIL

- [ ] **Step 3: Update `_handle_new_array`**

In `interpreter/executor.py`, change `_handle_new_array` (line 501-504):

From:
```python
register_writes={inst.result_reg: typed(addr, UNKNOWN)},
```

To:
```python
register_writes={inst.result_reg: typed(
    Pointer(base=addr, offset=0),
    pointer(scalar(type_hint or "Array")),
)},
```

- [ ] **Step 4: Run full test suite and fix breakages**

Run: `poetry run python -m pytest --tb=short -q`

Same patterns as Task 4: update tests that check array address strings to check `Pointer.base` instead.

- [ ] **Step 5: Commit**

```bash
poetry run python -m black .
git add interpreter/executor.py tests/
git commit -m "feat: NEW_ARRAY produces Pointer with parameterized type"
```

---

### Task 6: Convert builtins to return Pointer in `BuiltinResult.value`

`_builtin_array_of` and `_builtin_object_rest` return bare string addresses in `BuiltinResult.value`. The consumption sites at `executor.py:1218` and `:1535` call `typed_from_runtime(result.value)` on this value, which would produce `UNKNOWN` type for Pointers. Fix both sides: builtins return `TypedValue` (already typed), consumption sites check for it.

**Files:**
- Modify: `interpreter/builtins.py:127-142,201-225`
- Modify: `interpreter/executor.py:1218,1535`
- Modify: `tests/unit/test_array_of_builtin_result.py`
- Test: existing + updated tests

- [ ] **Step 1: Update `_builtin_array_of` to return TypedValue**

In `interpreter/builtins.py`, change `_builtin_array_of` (line 136-137):

From:
```python
    return BuiltinResult(
        value=addr,
```

To:
```python
    return BuiltinResult(
        value=typed(Pointer(base=addr, offset=0), pointer(scalar("Array"))),
```

Add imports: `from interpreter.vm_types import Pointer` and `from interpreter.type_expr import pointer, scalar` (verify which are already imported).

- [ ] **Step 2: Update `_builtin_object_rest` to return TypedValue**

In `interpreter/builtins.py`, change `_builtin_object_rest` (line 218-219):

From:
```python
    return BuiltinResult(
        value=rest_addr,
```

To:
```python
    return BuiltinResult(
        value=typed(Pointer(base=rest_addr, offset=0), pointer(scalar("Object"))),
```

- [ ] **Step 3: Update consumption sites in executor.py**

At line 1218, change:
```python
register_writes={inst.result_reg: typed_from_runtime(result.value)},
```
To:
```python
register_writes={
    inst.result_reg: _unwrap_builtin_result(result, func_name)
},
```

Same change at line 1535 (using `method_name` instead of `func_name`).

Add a helper function near the builtin dispatch code:

```python
def _unwrap_builtin_result(result: BuiltinResult, name: str) -> TypedValue:
    """Extract TypedValue from BuiltinResult, warning if bare value received."""
    if isinstance(result.value, TypedValue):
        return result.value
    logger.warning("Builtin %s returned bare value %r, expected TypedValue", name, type(result.value).__name__)
    return typed_from_runtime(result.value)
```

Add import: `from interpreter.typed_value import TypedValue` (if not already imported in executor.py).

- [ ] **Step 4: Update `test_array_of_builtin_result.py`**

Line 20-21 — replace:
```python
assert isinstance(result.value, str)
assert result.value.startswith("arr_")
```
with:
```python
assert isinstance(result.value, TypedValue)
assert isinstance(result.value.value, Pointer)
assert result.value.value.base.startswith("arr_")
```

Line 27 — replace:
```python
assert result.new_objects[0].addr == result.value
```
with:
```python
assert result.new_objects[0].addr == result.value.value.base
```

Line 44 — replace:
```python
assert result.value not in vm.heap
```
with:
```python
assert result.value.value.base not in vm.heap
```

Add imports: `from interpreter.vm_types import Pointer` and `from interpreter.typed_value import TypedValue`.

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
poetry run python -m black .
git add interpreter/builtins.py interpreter/executor.py tests/
git commit -m "feat: builtins return Pointer in TypedValue, consumption sites handle it"
```

---

### Task 7: Replace `field_fallback.py` private `_heap_addr()` with shared one

**Prerequisite:** Tasks 4, 5, and 6 MUST be committed and passing before this task. The shared `_heap_addr()` accepts any string (including `arr_` prefixes), unlike the private one which only accepts `obj_`-prefixed strings.

**Files:**
- Modify: `interpreter/field_fallback.py:58-61`
- Test: existing tests

- [ ] **Step 1: Replace private `_heap_addr` with shared import**

In `interpreter/field_fallback.py`:

Add import:
```python
from interpreter.vm import _heap_addr as vm_heap_addr
```

Replace the `_heap_addr` method (lines 58-61):
```python
    def _heap_addr(self, value: object) -> str | None:
        addr = vm_heap_addr(value)
        return addr if addr else None
```

This delegates to the shared function which handles Pointer, str, SymbolicValue, and dict. The return type changes from `str | None` to match — `vm_heap_addr` returns `""` for unknown, so convert to `None`.

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
poetry run python -m black .
git add interpreter/field_fallback.py
git commit -m "refactor: field_fallback uses shared _heap_addr() instead of private string-prefix check"
```

---

### Task 8: Delete dead BINOP string-synthesis code

**Files:**
- Modify: `interpreter/executor.py:889-908`
- Test: existing tests

- [ ] **Step 1: Simplify BINOP pointer detection**

In `_handle_binop`, replace lines 891-908:

From:
```python
    lhs_ptr = (
        lhs
        if isinstance(lhs, Pointer)
        else (
            Pointer(base=lhs, offset=0)
            if isinstance(lhs, str) and _heap_addr(lhs) and _heap_addr(lhs) in vm.heap
            else None
        )
    )
    rhs_ptr = (
        rhs
        if isinstance(rhs, Pointer)
        else (
            Pointer(base=rhs, offset=0)
            if isinstance(rhs, str) and _heap_addr(rhs) and _heap_addr(rhs) in vm.heap
            else None
        )
    )
```

To:
```python
    lhs_ptr = lhs if isinstance(lhs, Pointer) else None
    rhs_ptr = rhs if isinstance(rhs, Pointer) else None
```

Also update the comment on line 889-890 — remove "Also handles heap address strings (array decay to pointer in C)":

From:
```python
    # Pointer arithmetic: Pointer +/- int or int + Pointer
    # Also handles heap address strings (array decay to pointer in C)
```

To:
```python
    # Pointer arithmetic: Pointer +/- int or int + Pointer
```

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL PASS — no code path produces bare string object/array heap addresses anymore. (`ALLOC_REGION` still produces bare `rgn_` strings — these are byte buffers, not typed heap objects, and are intentionally excluded from this migration.)

- [ ] **Step 3: Commit**

```bash
poetry run python -m black .
git add interpreter/executor.py
git commit -m "refactor: delete dead BINOP string-to-Pointer synthesis (all refs are Pointer now)"
```

---

### Task 9: Update CLAUDE.md with design principle

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the principle to Programming Patterns**

In `CLAUDE.md`, in the `## Programming Patterns` section, add after the last bullet:

```markdown
- **Do not encode information in string representations.** Use typed objects (`Pointer`, `FuncRef`, `ClassRef`, etc.) to carry structured data. Never use string prefixes, patterns, or regex to deduce what a value represents — use `isinstance` checks on the actual type.
```

- [ ] **Step 2: Update README if needed**

Check if the README mentions heap addresses or string representations. If so, update to reflect that heap references are now `Pointer` objects.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: add 'no stringly-typed information' principle to CLAUDE.md"
```

---

### Task 10: Add integration test asserting correct types on heap references

Verify that the end-to-end pipeline produces correctly typed Pointer values for struct instantiation across multiple languages.

**Files:**
- Create: `tests/integration/test_pointer_types.py`

- [ ] **Step 1: Write the integration test**

```python
"""Integration tests verifying heap references carry correct Pointer types."""

from interpreter.constants import Language
from interpreter.run import run
from interpreter.vm_types import Pointer
from interpreter.type_expr import pointer, scalar


def _typed_locals(vm):
    return vm.call_stack[0].local_vars


class TestHeapReferenceTypes:
    def test_java_new_produces_pointer_type(self):
        vm = run("class Dog {} Dog d = new Dog();", language=Language.JAVA, max_steps=100)
        tv = _typed_locals(vm)["d"]
        assert isinstance(tv.value, Pointer)
        assert tv.type == pointer(scalar("Dog"))

    def test_python_new_produces_pointer_type(self):
        vm = run("class Cat:\n  pass\nc = Cat()\n", language=Language.PYTHON, max_steps=100)
        tv = _typed_locals(vm)["c"]
        assert isinstance(tv.value, Pointer)
        assert tv.type == pointer(scalar("Cat"))

    def test_rust_struct_produces_pointer_type(self):
        vm = run(
            "struct Point { x: i32 }\nlet p = Point { x: 42 };\n",
            language=Language.RUST,
            max_steps=200,
        )
        tv = _typed_locals(vm)["p"]
        assert isinstance(tv.value, Pointer)
        assert tv.type == pointer(scalar("Point"))

    def test_array_produces_pointer_type(self):
        vm = run("x = [1, 2, 3]\n", language="python", max_steps=100)
        tv = _typed_locals(vm)["x"]
        assert isinstance(tv.value, Pointer)
        # Array type varies — just check it's a Pointer, not a string
```

- [ ] **Step 2: Run test**

Run: `poetry run python -m pytest tests/integration/test_pointer_types.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
poetry run python -m black .
git add tests/integration/test_pointer_types.py
git commit -m "test: add integration tests verifying Pointer types on heap references"
```
