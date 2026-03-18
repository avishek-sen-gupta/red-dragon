# Rust Box Auto-Deref Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Rust Box a real object with transparent field/method delegation via a general-purpose `__method_missing__` VM protocol and new `LOAD_FIELD_INDIRECT` opcode.

**Architecture:** The VM gains two features: (1) `LOAD_FIELD_INDIRECT` opcode for dynamic field access by register name, (2) `__method_missing__` fallback in `LOAD_FIELD` and `CALL_METHOD`. Box is fully defined in IR prelude — its `__method_missing__` uses `LOAD_FIELD_INDIRECT` to delegate to `self.__boxed__`. `Box::new(x)` becomes real instantiation (no longer pass-through).

**Tech Stack:** Python 3.13+, pytest, tree-sitter (Rust grammar)

**Spec:** `docs/superpowers/specs/2026-03-18-rust-box-auto-deref-design.md`

---

## File Map

| File | Responsibility | Action |
|------|---------------|--------|
| `interpreter/ir.py` | Opcode enum | Add `LOAD_FIELD_INDIRECT` |
| `interpreter/executor.py` | VM instruction handlers | Add `_handle_load_field_indirect`, modify `_handle_load_field` and `_handle_call_method` |
| `interpreter/frontends/rust/declarations.py` | Box/Option prelude IR emission | Add `__method_missing__` to Box class |
| `interpreter/frontends/rust/expressions.py` | Rust expression lowering | Split `Box::new`/`String::from`, change `*expr` to `LOAD_FIELD` |
| `tests/unit/test_load_field_indirect.py` | Unit tests for new opcode | Create |
| `tests/unit/test_method_missing.py` | Unit tests for `__method_missing__` protocol | Create |
| `tests/unit/test_rust_box_option_lowering.py` | Existing Box lowering tests | Update |
| `tests/unit/test_rust_prelude.py` | Existing prelude tests | Update |
| `tests/integration/test_rust_box_deref.py` | Integration tests for Box delegation | Create |
| `tests/integration/test_rust_frontend_execution.py` | Existing Rust integration tests | Update |

---

## Task 1: Add `LOAD_FIELD_INDIRECT` Opcode + Executor Handler

**Files:**
- Modify: `interpreter/ir.py:46` (add opcode after `LOAD_INDIRECT`)
- Modify: `interpreter/executor.py` (add handler, register in dispatch table at ~line 1553)
- Create: `tests/unit/test_load_field_indirect.py`

- [ ] **Step 1: Write failing tests for `LOAD_FIELD_INDIRECT`**

Create `tests/unit/test_load_field_indirect.py`:

```python
"""Unit tests for LOAD_FIELD_INDIRECT opcode — dynamic field access by register name."""

import pytest

from interpreter.ir import IRInstruction, Opcode
from interpreter.executor import LocalExecutor
from interpreter.vm import VMState, HeapObject, StackFrame
from interpreter.cfg import CFG
from interpreter.registry import FunctionRegistry
from interpreter.typed_value import typed, TypedValue
from interpreter.type_expr import UNKNOWN, scalar


def _make_vm_with_object(fields: dict[str, TypedValue]) -> VMState:
    """Create a VM with a single heap object and return (vm, obj_addr)."""
    vm = VMState()
    addr = "obj_0"
    vm.heap[addr] = HeapObject(type_hint="TestObj", fields=fields)
    vm.call_stack.append(StackFrame(function_name="<test>", return_label=""))
    vm.call_stack[-1].registers["%obj"] = typed(addr, scalar("Object"))
    return vm


class TestLoadFieldIndirect:
    def test_loads_field_by_register_name(self):
        """LOAD_FIELD_INDIRECT resolves field name from a register."""
        vm = _make_vm_with_object({"x": typed(42, scalar("Int"))})
        vm.call_stack[-1].registers["%name"] = typed("x", scalar("String"))
        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD_INDIRECT,
            result_reg="%out",
            operands=["%obj", "%name"],
        )
        cfg = CFG()
        registry = FunctionRegistry()
        result = LocalExecutor.execute(inst, vm, cfg, registry)
        assert result.state_update.register_writes["%out"].value == 42

    def test_missing_field_returns_symbolic(self):
        """LOAD_FIELD_INDIRECT on a missing field produces a symbolic value."""
        vm = _make_vm_with_object({"x": typed(42, scalar("Int"))})
        vm.call_stack[-1].registers["%name"] = typed("y", scalar("String"))
        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD_INDIRECT,
            result_reg="%out",
            operands=["%obj", "%name"],
        )
        cfg = CFG()
        registry = FunctionRegistry()
        result = LocalExecutor.execute(inst, vm, cfg, registry)
        from interpreter.symbolic import SymbolicValue
        assert isinstance(result.state_update.register_writes["%out"].value, SymbolicValue)

    def test_non_heap_object_returns_symbolic(self):
        """LOAD_FIELD_INDIRECT on a non-heap value produces a symbolic value."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="<test>", return_label=""))
        vm.call_stack[-1].registers["%obj"] = typed(99, scalar("Int"))
        vm.call_stack[-1].registers["%name"] = typed("x", scalar("String"))
        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD_INDIRECT,
            result_reg="%out",
            operands=["%obj", "%name"],
        )
        cfg = CFG()
        registry = FunctionRegistry()
        result = LocalExecutor.execute(inst, vm, cfg, registry)
        from interpreter.symbolic import SymbolicValue
        assert isinstance(result.state_update.register_writes["%out"].value, SymbolicValue)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_load_field_indirect.py -v`
Expected: FAIL — `LOAD_FIELD_INDIRECT` not in Opcode enum

- [ ] **Step 3: Add opcode to enum**

In `interpreter/ir.py`, after line 46 (`LOAD_INDIRECT = "LOAD_INDIRECT"`), add:

```python
    LOAD_FIELD_INDIRECT = "LOAD_FIELD_INDIRECT"
```

- [ ] **Step 4: Write the executor handler**

In `interpreter/executor.py`, add the handler function (near the other `_handle_load_*` functions, around line 360):

```python
def _handle_load_field_indirect(
    inst: IRInstruction, vm: VMState, **kwargs: Any
) -> ExecutionResult:
    """LOAD_FIELD_INDIRECT %obj %name_reg: read field whose name is in a register."""
    obj_val = _resolve_reg(vm, inst.operands[0])
    field_name_val = _resolve_reg(vm, inst.operands[1])
    field_name = str(field_name_val) if not isinstance(field_name_val, str) else field_name_val

    addr = _heap_addr(obj_val)
    if not addr or addr not in vm.heap:
        obj_desc = _symbolic_name(obj_val)
        sym = vm.fresh_symbolic(hint=f"{obj_desc}.{field_name}")
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: typed(sym, UNKNOWN)},
                reasoning=f"load_field_indirect {obj_desc}.{field_name} (not on heap) → {sym.name}",
            )
        )

    heap_obj = vm.heap[addr]
    if field_name in heap_obj.fields:
        tv = heap_obj.fields[field_name]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: tv},
                reasoning=f"load_field_indirect {addr}.{field_name} = {tv!r}",
            )
        )

    # Field not found — check __method_missing__ before symbolic fallback
    # (critical for multi-level Box chaining: LOAD_FIELD_INDIRECT on an outer Box
    #  whose inner is also a Box triggers the inner Box's __method_missing__)
    mm = heap_obj.fields.get("__method_missing__")
    if mm is not None and isinstance(mm.value, BoundFuncRef):
        return _try_user_function_call(
            mm.value,
            [typed(addr, scalar("Object")), typed(field_name, scalar("String"))],
            inst,
            vm,
            kwargs.get("cfg", CFG()),
            kwargs.get("registry", FunctionRegistry()),
            kwargs.get("current_label", ""),
        )

    # No __method_missing__ — symbolic
    sym = vm.fresh_symbolic(hint=f"{addr}.{field_name}")
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: typed(sym, UNKNOWN)},
            reasoning=f"load_field_indirect {addr}.{field_name} (unknown) → {sym.name}",
        )
    )
```

**Note:** Import `BoundFuncRef` from `interpreter.func_ref` at the top of the handler, and ensure `_try_user_function_call`, `CFG`, `FunctionRegistry`, and `scalar` are accessible.

Register in the dispatch table (around line 1553):

```python
        Opcode.LOAD_FIELD_INDIRECT: _handle_load_field_indirect,
```

Add it after the `Opcode.LOAD_INDIRECT` entry.

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_load_field_indirect.py -v`
Expected: 3 PASS

- [ ] **Step 6: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass (no regressions)

- [ ] **Step 7: Commit**

```bash
poetry run python -m black interpreter/ir.py interpreter/executor.py tests/unit/test_load_field_indirect.py
git add interpreter/ir.py interpreter/executor.py tests/unit/test_load_field_indirect.py
git commit -m "feat: add LOAD_FIELD_INDIRECT opcode for dynamic field access by register name"
```

---

## Task 2: Add `__method_missing__` Fallback to `_handle_load_field`

**Files:**
- Modify: `interpreter/executor.py:505-561` (`_handle_load_field`)
- Create: `tests/unit/test_method_missing.py`

**Context:** `_handle_load_field` currently auto-materializes a symbolic value when a field is not found on a heap object (lines 553-561). The `__method_missing__` check must intercept *before* that symbolic materialization. If the object has a `__method_missing__` field (a BoundFuncRef), invoke it with the field name. If it doesn't, fall through to the existing symbolic path.

- [ ] **Step 1: Write failing test for `__method_missing__` on LOAD_FIELD**

Add to `tests/unit/test_method_missing.py`:

```python
"""Unit tests for __method_missing__ VM protocol."""

import pytest

from interpreter.ir import IRInstruction, Opcode
from interpreter.executor import LocalExecutor
from interpreter.vm import VMState, HeapObject, StackFrame
from interpreter.cfg import CFG, BasicBlock
from interpreter.registry import FunctionRegistry
from interpreter.typed_value import typed, TypedValue
from interpreter.type_expr import UNKNOWN, scalar
from interpreter.func_ref import FuncRef, BoundFuncRef
from interpreter.symbolic import SymbolicValue


def _make_vm_with_method_missing(inner_fields: dict[str, TypedValue]) -> tuple[VMState, CFG, FunctionRegistry]:
    """Create a VM with an outer object that has __method_missing__ pointing to a function
    that delegates to an inner object.

    Returns (vm, cfg, registry) with:
    - %outer register pointing to outer object (has __method_missing__ + __boxed__ fields)
    - inner object stored in outer.__boxed__, containing inner_fields
    """
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name="<test>", return_label=""))

    # Inner object with real fields
    inner_addr = "obj_0"
    vm.heap[inner_addr] = HeapObject(type_hint="Inner", fields=inner_fields)

    # __method_missing__ function: takes (self, name) → LOAD_FIELD_INDIRECT(self.__boxed__, name)
    mm_label = "func_mm_0"
    cfg = CFG()
    cfg.blocks[mm_label] = BasicBlock(label=mm_label, instructions=[
        IRInstruction(opcode=Opcode.LOAD_VAR, result_reg="%mm_self", operands=["self"]),
        IRInstruction(opcode=Opcode.LOAD_FIELD, result_reg="%mm_inner", operands=["%mm_self", "__boxed__"]),
        IRInstruction(opcode=Opcode.LOAD_VAR, result_reg="%mm_name", operands=["name"]),
        IRInstruction(opcode=Opcode.LOAD_FIELD_INDIRECT, result_reg="%mm_result", operands=["%mm_inner", "%mm_name"]),
        IRInstruction(opcode=Opcode.RETURN, operands=["%mm_result"]),
    ])

    mm_func_ref = BoundFuncRef(func_ref=FuncRef(name="__method_missing__", label=mm_label))

    # Outer object: has value→inner_addr and __method_missing__→func_ref
    outer_addr = "obj_1"
    vm.heap[outer_addr] = HeapObject(
        type_hint="Outer",
        fields={
            "__boxed__": typed(inner_addr, scalar("Object")),
            "__method_missing__": typed(mm_func_ref, UNKNOWN),
        },
    )
    vm.call_stack[-1].registers["%outer"] = typed(outer_addr, scalar("Object"))

    registry = FunctionRegistry()
    registry.func_params[mm_label] = ["self", "name"]

    return vm, cfg, registry


class TestMethodMissingLoadField:
    def test_delegates_to_inner_object_field(self):
        """LOAD_FIELD on outer.x delegates to inner.x via __method_missing__."""
        vm, cfg, registry = _make_vm_with_method_missing({"x": typed(42, scalar("Int"))})
        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD,
            result_reg="%out",
            operands=["%outer", "x"],
        )
        result = LocalExecutor.execute(inst, vm, cfg, registry)
        # __method_missing__ pushes a stack frame — it's a function call
        assert result.state_update.call_push is not None
        assert result.state_update.next_label == "func_mm_0"

    def test_existing_field_does_not_trigger_method_missing(self):
        """LOAD_FIELD for a field that exists returns it directly, no __method_missing__."""
        vm, cfg, registry = _make_vm_with_method_missing({"x": typed(42, scalar("Int"))})
        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD,
            result_reg="%out",
            operands=["%outer", "__boxed__"],  # "__boxed__" exists on outer
        )
        result = LocalExecutor.execute(inst, vm, cfg, registry)
        # Direct field access — no function call
        assert result.state_update.call_push is None

    def test_no_method_missing_falls_through_to_symbolic(self):
        """Objects without __method_missing__ still get symbolic fallback."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="<test>", return_label=""))
        addr = "obj_0"
        vm.heap[addr] = HeapObject(type_hint="Plain", fields={"a": typed(1, scalar("Int"))})
        vm.call_stack[-1].registers["%obj"] = typed(addr, scalar("Object"))
        inst = IRInstruction(
            opcode=Opcode.LOAD_FIELD,
            result_reg="%out",
            operands=["%obj", "missing_field"],
        )
        cfg = CFG()
        registry = FunctionRegistry()
        result = LocalExecutor.execute(inst, vm, cfg, registry)
        assert isinstance(result.state_update.register_writes["%out"].value, SymbolicValue)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_method_missing.py -v`
Expected: `test_delegates_to_inner_object_field` FAILS (no `__method_missing__` interception yet)

- [ ] **Step 3: Modify `_handle_load_field` to check `__method_missing__`**

In `interpreter/executor.py`, in the `_handle_load_field` function, replace the final block (lines ~553-561) where it creates a symbolic for missing fields:

**Current code (lines 553-561):**
```python
    # Field not found — create symbolic and cache it
    sym = vm.fresh_symbolic(hint=f"{addr}.{field_name}")
    heap_obj.fields[field_name] = typed(sym, UNKNOWN)
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: typed(sym, UNKNOWN)},
            reasoning=f"load {addr}.{field_name} (unknown) → {sym.name}",
        )
    )
```

**Replace with:**
```python
    # Field not found — check for __method_missing__ before symbolic fallback
    mm = heap_obj.fields.get("__method_missing__")
    if mm is not None and isinstance(mm.value, BoundFuncRef):
        return _try_user_function_call(
            mm.value,
            [typed(addr, scalar("Object")), typed(field_name, scalar("String"))],
            inst,
            vm,
            kwargs.get("cfg", CFG()),
            kwargs.get("registry", FunctionRegistry()),
            kwargs.get("current_label", ""),
        )

    # No __method_missing__ — create symbolic and cache it
    sym = vm.fresh_symbolic(hint=f"{addr}.{field_name}")
    heap_obj.fields[field_name] = typed(sym, UNKNOWN)
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: typed(sym, UNKNOWN)},
            reasoning=f"load {addr}.{field_name} (unknown) → {sym.name}",
        )
    )
```

**Important:** `_handle_load_field` currently only accepts `inst, vm, **kwargs`. It needs access to `cfg`, `registry`, and `current_label` to call `_try_user_function_call`. Check if these are already passed through `**kwargs` by the dispatcher. If not, update the function signature to accept them explicitly (matching the pattern used by `_handle_call_method`).

Look at `LocalExecutor.execute()` around line 1558 — it passes `cfg`, `registry`, `current_label` etc. as keyword args to all handlers. So they will be in `**kwargs`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_method_missing.py tests/unit/test_load_field_indirect.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
poetry run python -m black interpreter/executor.py tests/unit/test_method_missing.py
git add interpreter/executor.py tests/unit/test_method_missing.py
git commit -m "feat: add __method_missing__ fallback to LOAD_FIELD for transparent delegation"
```

---

## Task 3: Add `__method_missing__` Fallback to `_handle_call_method`

**Files:**
- Modify: `interpreter/executor.py:1374-1490` (`_handle_call_method`)
- Modify: `tests/unit/test_method_missing.py`

**Context:** `_handle_call_method` has two fallback sites. Per spec, `__method_missing__` is inserted at site (b): known type, but method not found after parent chain walk (around line 1457). At this point, the object is on the heap and we can check for `__method_missing__`. The VM calls `__method_missing__(name, *args)` and returns its result directly.

- [ ] **Step 1: Write failing test for `__method_missing__` on CALL_METHOD**

Add to `tests/unit/test_method_missing.py`:

```python
class TestMethodMissingCallMethod:
    def test_delegates_method_call_via_method_missing(self):
        """CALL_METHOD on outer.foo(arg) delegates to __method_missing__('foo', arg)."""
        vm, cfg, registry = _make_vm_with_method_missing({"x": typed(42, scalar("Int"))})

        # Register "Outer" as a known class so we hit site (b)
        registry.class_methods["Outer"] = {}  # no methods registered

        inst = IRInstruction(
            opcode=Opcode.CALL_METHOD,
            result_reg="%out",
            operands=["%outer", "some_method", "%arg1"],
        )
        vm.call_stack[-1].registers["%arg1"] = typed(10, scalar("Int"))
        result = LocalExecutor.execute(
            inst, vm, cfg, registry, current_label="entry"
        )
        # __method_missing__ should be called as a function
        assert result.state_update.call_push is not None
        assert result.state_update.next_label == "func_mm_0"

    def test_existing_method_does_not_trigger_method_missing(self):
        """CALL_METHOD for a method that exists dispatches normally."""
        vm, cfg, registry = _make_vm_with_method_missing({"x": typed(42, scalar("Int"))})

        # Register a real method for Outer
        real_method_label = "func_real_0"
        cfg.blocks[real_method_label] = BasicBlock(
            label=real_method_label,
            instructions=[
                IRInstruction(opcode=Opcode.CONST, result_reg="%r", operands=["99"]),
                IRInstruction(opcode=Opcode.RETURN, operands=["%r"]),
            ],
        )
        registry.class_methods["Outer"] = {"real_method": [real_method_label]}
        registry.func_params[real_method_label] = ["self"]

        inst = IRInstruction(
            opcode=Opcode.CALL_METHOD,
            result_reg="%out",
            operands=["%outer", "real_method"],
        )
        result = LocalExecutor.execute(
            inst, vm, cfg, registry, current_label="entry"
        )
        assert result.state_update.next_label == real_method_label
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_method_missing.py::TestMethodMissingCallMethod -v`
Expected: `test_delegates_method_call_via_method_missing` FAILS

- [ ] **Step 3: Modify `_handle_call_method` to check `__method_missing__` at site (b)**

In `interpreter/executor.py`, in `_handle_call_method`, replace the block around lines 1457-1461 (the "Known type but unknown method" fallback):

**Current code (~line 1457):**
```python
    if not func_label or func_label not in cfg.blocks:
        # Known type but unknown method — resolve via configured strategy
        return call_resolver.resolve_method(
            type_hint, method_name, [a.value for a in args], inst, vm
        )
```

**Replace with:**
```python
    if not func_label or func_label not in cfg.blocks:
        # Known type but unknown method — check __method_missing__ first
        if addr and addr in vm.heap:
            mm = vm.heap[addr].fields.get("__method_missing__")
            if mm is not None and isinstance(mm.value, BoundFuncRef):
                mm_args = [
                    typed(addr, scalar("Object")),
                    typed(method_name, scalar("String")),
                ] + list(args)
                return _try_user_function_call(
                    mm.value, mm_args, inst, vm, cfg, registry, current_label
                )
        # No __method_missing__ — resolve via configured strategy
        return call_resolver.resolve_method(
            type_hint, method_name, [a.value for a in args], inst, vm
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_method_missing.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
poetry run python -m black interpreter/executor.py tests/unit/test_method_missing.py
git add interpreter/executor.py tests/unit/test_method_missing.py
git commit -m "feat: add __method_missing__ fallback to CALL_METHOD for method delegation"
```

---

## Task 4: Add `__method_missing__` to Box Prelude Class

**Files:**
- Modify: `interpreter/frontends/rust/declarations.py:509-543` (`_emit_box_class`)
- Modify: `tests/unit/test_rust_prelude.py`

**Context:** The Box prelude class currently only has `__init__`. Add a `__method_missing__` method that:
1. Loads `self.__boxed__` (the inner object)
2. Loads the field name parameter
3. Uses `LOAD_FIELD_INDIRECT` to dynamically access the field on inner
4. Returns the result

`__method_missing__` ONLY does field delegation via `LOAD_FIELD_INDIRECT` and returns the result. For `LOAD_FIELD`, this is the final value. For `CALL_METHOD`, the VM calls `__method_missing__(self, name, *args)` and returns its result directly (Task 3 passes all args). Task 8 handles the method-call-on-returned-value case if needed.

- [ ] **Step 1: Write failing test for Box `__method_missing__` in prelude**

Add to `tests/unit/test_rust_prelude.py`:

```python
    def test_box_has_method_missing(self):
        """Box prelude class must define __method_missing__."""
        ir = _lower("let x = 1;")
        labels = [inst.label for inst in ir if inst.opcode == Opcode.LABEL and inst.label]
        assert any(
            "Box" in lbl and "__method_missing__" in lbl for lbl in labels
        ), f"No __method_missing__ label found for Box in: {labels}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_rust_prelude.py::TestRustPrelude::test_box_has_method_missing -v`
Expected: FAIL

- [ ] **Step 3: Add `__method_missing__` method to `_emit_box_class`**

In `interpreter/frontends/rust/declarations.py`, modify `_emit_box_class()`. After the `__init__` method body and before the end label, add a `__method_missing__` method:

```python
def _emit_box_class(ctx: TreeSitterEmitContext) -> None:
    """Emit Box class: __init__ + __method_missing__ for auto-deref delegation."""
    class_name = "Box"
    class_label = ctx.fresh_label(f"{constants.PRELUDE_CLASS_LABEL_PREFIX}{class_name}")
    end_label = ctx.fresh_label(
        f"{constants.PRELUDE_END_CLASS_LABEL_PREFIX}{class_name}"
    )
    init_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{class_name}___init__")
    init_end = ctx.fresh_label(f"end_{class_name}___init__")
    mm_label = ctx.fresh_label(
        f"{constants.FUNC_LABEL_PREFIX}{class_name}___method_missing__"
    )
    mm_end = ctx.fresh_label(f"end_{class_name}___method_missing__")

    # Class body — branch past it
    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=class_label)

    # __init__(self, value) body — unchanged
    ctx.emit(Opcode.BRANCH, label=init_end)
    ctx.emit(Opcode.LABEL, label=init_label)
    _emit_method_params(ctx, [constants.PARAM_SELF, "value"])
    self_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=self_reg, operands=[constants.PARAM_SELF])
    val_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=val_reg, operands=["value"])
    ctx.emit(Opcode.STORE_FIELD, operands=[self_reg, "__boxed__", val_reg])
    ctx.emit(Opcode.RETURN, operands=[self_reg])
    ctx.emit(Opcode.LABEL, label=init_end)

    # __method_missing__(self, name) body
    # Loads self.__boxed__, then LOAD_FIELD_INDIRECT(inner, name) and returns result
    ctx.emit(Opcode.BRANCH, label=mm_end)
    ctx.emit(Opcode.LABEL, label=mm_label)
    _emit_method_params(ctx, [constants.PARAM_SELF, "name"])
    mm_self = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=mm_self, operands=[constants.PARAM_SELF])
    mm_inner = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_FIELD, result_reg=mm_inner, operands=[mm_self, "__boxed__"])
    mm_name = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=mm_name, operands=["name"])
    mm_result = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD_INDIRECT,
        result_reg=mm_result,
        operands=[mm_inner, mm_name],
    )
    ctx.emit(Opcode.RETURN, operands=[mm_result])
    ctx.emit(Opcode.LABEL, label=mm_end)

    # Register methods — CONST func_ref INSIDE class body
    _emit_prelude_func_ref(ctx, "__init__", init_label)
    _emit_prelude_func_ref(ctx, "__method_missing__", mm_label)

    ctx.emit(Opcode.LABEL, label=end_label)

    # Store class ref (OUTSIDE class body, after end_label)
    cls_reg = ctx.fresh_reg()
    ctx.emit_class_ref(class_name, class_label, [], result_reg=cls_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[class_name, cls_reg])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_rust_prelude.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
poetry run python -m black interpreter/frontends/rust/declarations.py tests/unit/test_rust_prelude.py
git add interpreter/frontends/rust/declarations.py tests/unit/test_rust_prelude.py
git commit -m "feat: add __method_missing__ to Box prelude class for auto-deref delegation"
```

---

## Task 5: Revert Box::new Pass-Through + Split String::from

**Files:**
- Modify: `interpreter/frontends/rust/expressions.py:16-52`
- Modify: `tests/unit/test_rust_box_option_lowering.py`

**Context:** `_lower_box_new` currently returns the argument directly (pass-through). Change it to emit `CALL_FUNCTION Box arg`. `String::from` shares the same code path via `lower_call_with_box_option` — it must be split out and remain pass-through.

- [ ] **Step 1: Update existing test expectations**

In `tests/unit/test_rust_box_option_lowering.py`, update `TestBoxNewLowering`:

```python
class TestBoxNewLowering:
    def test_box_new_emits_call_function(self):
        """Box::new(expr) should emit CALL_FUNCTION 'Box' with the argument."""
        ir = _lower("let b = Box::new(42);")
        calls = [i for i in ir if i.opcode == Opcode.CALL_FUNCTION]
        box_calls = [c for c in calls if c.operands and c.operands[0] == "Box"]
        assert len(box_calls) == 1, f"Expected 1 CALL_FUNCTION Box, got {len(box_calls)}: {calls}"
```

Replace the existing `test_box_new_is_pass_through` and `test_box_new_operand_is_not_call_unknown` tests with the above.

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_rust_box_option_lowering.py::TestBoxNewLowering -v`
Expected: FAIL (still pass-through)

- [ ] **Step 3: Split `Box::new` and `String::from`, make Box::new real**

In `interpreter/frontends/rust/expressions.py`, modify `lower_call_with_box_option` and `_lower_box_new`:

Keep the original 2-param signature `(ctx, node)` — it extracts `func_node` and `args_node` internally from the tree-sitter node. Only change the internal dispatch logic:

```python
def lower_call_with_box_option(ctx: TreeSitterEmitContext, node) -> str:
    """Rust-specific call lowering that intercepts Box::new, String::from, and Some."""
    func_node = node.child_by_field_name(ctx.constants.call_function_field)
    args_node = node.child_by_field_name(ctx.constants.call_arguments_field)

    if func_node and func_node.type == RustNodeType.SCOPED_IDENTIFIER:
        name = ctx.node_text(func_node)
        if name == "Box::new":
            return _lower_box_new(ctx, args_node, node)
        if name == "String::from":
            return _lower_string_from(ctx, args_node)
    plain = ctx.node_text(func_node) if func_node else ""
    if plain == "Some":
        return _lower_some(ctx, args_node, node)
    # Fall through to generic call lowering
    return common_expr.lower_call(ctx, node)


def _lower_box_new(ctx: TreeSitterEmitContext, args_node, call_node) -> str:
    """Lower Box::new(expr) → CALL_FUNCTION 'Box' with the argument."""
    arg_regs = extract_call_args(ctx, args_node)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=reg,
        operands=["Box"] + arg_regs,
        node=call_node,
    )
    return reg


def _lower_string_from(ctx: TreeSitterEmitContext, args_node) -> str:
    """Lower String::from(expr) as pass-through — return the argument directly."""
    arg_regs = extract_call_args(ctx, args_node)
    return arg_regs[0] if arg_regs else ctx.fresh_reg()
```

**Important:** The function signature stays `(ctx, node)` — it is registered as a handler in `RustNodeType.CALL_EXPRESSION`'s dispatch table in `frontend.py` and called with exactly 2 args. Do NOT change callers.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_rust_box_option_lowering.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: Some existing integration tests may fail (e.g., `test_box_new_is_pass_through` in `test_rust_frontend_execution.py`). Fix those in the next step.

- [ ] **Step 6: Update integration tests for real Box instantiation**

In `tests/integration/test_rust_frontend_execution.py`, update `TestRustBoxExecution`:

```python
class TestRustBoxExecution:
    def test_box_new_creates_real_object(self):
        """Box::new(x) creates a Box object with __boxed__ field pointing to x."""
        vm, local_vars = _run_rust(
            """\
struct Node { value: i32 }
let n = Node { value: 42 };
let b = Box::new(n);
""",
            max_steps=300,
        )
        # Box::new now creates a real Box — b is a Box object, not n itself
        b_addr = local_vars.get("b")
        assert b_addr is not None
        assert b_addr in vm.heap
        assert "__boxed__" in vm.heap[b_addr].fields
        # The Box's "__boxed__" field should point to the Node
        assert vm.heap[b_addr].type_hint == "Box"
```

Also update `TestRustOptionExecution.test_nested_box_in_option`:

```python
    def test_nested_box_in_option(self):
        """Some(Box::new(42)) — unwrap returns the Box object."""
        vm, local_vars = _run_rust(
            """\
let opt = Some(Box::new(42));
let inner = opt.unwrap();
""",
            max_steps=400,
        )
        # inner is now a Box object, not 42 directly
        inner_addr = local_vars.get("inner")
        assert inner_addr is not None
        assert inner_addr in vm.heap
        assert vm.heap[inner_addr].type_hint == "Box"
```

- [ ] **Step 7: Run full test suite again**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
poetry run python -m black interpreter/frontends/rust/expressions.py tests/unit/test_rust_box_option_lowering.py tests/integration/test_rust_frontend_execution.py
git add interpreter/frontends/rust/expressions.py tests/unit/test_rust_box_option_lowering.py tests/integration/test_rust_frontend_execution.py
git commit -m "feat: revert Box::new pass-through to real CALL_FUNCTION Box, split String::from"
```

---

## Task 6: Change `*expr` to `LOAD_FIELD "__boxed__"` in Rust Frontend

**Files:**
- Modify: `interpreter/frontends/rust/expressions.py:125-137` (`lower_deref_expr`)
- Modify: `tests/unit/test_rust_box_option_lowering.py`

**Context:** Currently `*expr` emits `LOAD_INDIRECT`. Change to `LOAD_FIELD "__boxed__"` for all Rust `*expr`. Per spec, Rust doesn't have raw C pointers in our system, so this is safe. The field name `__boxed__` matches Box's internal storage field (renamed from `value` to avoid collision with user-defined `value` fields).

- [ ] **Step 1: Verify existing test expects LOAD_FIELD**

The existing test `TestDerefLowering.test_deref_emits_load_field_value` in `tests/unit/test_rust_box_option_lowering.py` needs to be updated to expect `LOAD_FIELD` with `"__boxed__"`. Check that it currently fails (it does, because the implementation emits `LOAD_INDIRECT`).

Run: `poetry run python -m pytest tests/unit/test_rust_box_option_lowering.py::TestDerefLowering -v`
Expected: FAIL

- [ ] **Step 2: Change `lower_deref_expr` to emit LOAD_FIELD**

In `interpreter/frontends/rust/expressions.py`, replace `lower_deref_expr`:

```python
def lower_deref_expr(ctx: TreeSitterEmitContext, node) -> str:
    """Lower *expr → LOAD_FIELD '__boxed__' (Box unwrap / deref)."""
    children = [c for c in node.children if c.type != RustNodeType.ASTERISK]
    inner = children[0] if children else node
    inner_reg = ctx.lower_expr(inner)
    reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.LOAD_FIELD,
        result_reg=reg,
        operands=[inner_reg, "__boxed__"],
        node=node,
    )
    return reg
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_rust_box_option_lowering.py::TestDerefLowering -v`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
poetry run python -m black interpreter/frontends/rust/expressions.py
git add interpreter/frontends/rust/expressions.py
git commit -m "feat: change Rust *expr to LOAD_FIELD '__boxed__' for Box deref"
```

---

## Task 7: Integration Tests — Box Auto-Deref End-to-End

**Files:**
- Create: `tests/integration/test_rust_box_deref.py`
- Modify: Rosetta linked list test if needed

**Context:** Verify the full pipeline: Box::new creates a real Box, field access delegates via `__method_missing__`, method calls delegate, multi-level chaining works, and the Rosetta linked list still passes.

- [ ] **Step 1: Write integration tests**

Create `tests/integration/test_rust_box_deref.py`:

```python
"""Integration tests for Rust Box auto-deref via __method_missing__."""

from tests.integration.test_rust_frontend_execution import _run_rust


class TestBoxFieldDelegation:
    def test_box_field_access_delegates_to_inner(self):
        """box_val.field delegates to inner object's field via __method_missing__."""
        _, local_vars = _run_rust(
            """\
struct Point { x: i32, y: i32 }
let p = Point { x: 10, y: 20 };
let b = Box::new(p);
let answer = b.x;
""",
            max_steps=500,
        )
        assert local_vars["answer"] == 10

    def test_box_explicit_deref(self):
        """*box_val returns the inner value via LOAD_FIELD '__boxed__'."""
        _, local_vars = _run_rust(
            """\
struct Point { x: i32, y: i32 }
let p = Point { x: 10, y: 20 };
let b = Box::new(p);
let inner = *b;
let answer = inner.x;
""",
            max_steps=500,
        )
        assert local_vars["answer"] == 10


class TestBoxMultiLevel:
    def test_double_box_field_access(self):
        """Box<Box<T>> chains __method_missing__ through two levels."""
        _, local_vars = _run_rust(
            """\
struct Point { x: i32 }
let p = Point { x: 42 };
let b1 = Box::new(p);
let b2 = Box::new(b1);
let answer = b2.x;
""",
            max_steps=600,
        )
        assert local_vars["answer"] == 42


class TestBoxOptionInteraction:
    def test_some_box_unwrap_field_access(self):
        """Some(Box::new(node)).unwrap().field works via __method_missing__."""
        _, local_vars = _run_rust(
            """\
struct Node { value: i32 }
let n = Node { value: 99 };
let opt = Some(Box::new(n));
let inner = opt.unwrap();
let answer = inner.value;
""",
            max_steps=600,
        )
        assert local_vars["answer"] == 99

    def test_as_ref_unwrap_box_field_access(self):
        """opt.as_ref().unwrap().field — the Rosetta pattern."""
        _, local_vars = _run_rust(
            """\
struct Node { value: i32 }
let n = Node { value: 77 };
let opt = Some(Box::new(n));
let inner = opt.as_ref().unwrap();
let answer = inner.value;
""",
            max_steps=700,
        )
        assert local_vars["answer"] == 77
```

- [ ] **Step 2: Run integration tests**

Run: `poetry run python -m pytest tests/integration/test_rust_box_deref.py -v`
Expected: All PASS

- [ ] **Step 3: Verify Rosetta linked list still passes**

Run: `poetry run python -m pytest tests/unit/rosetta/test_rosetta_linked_list.py -v -k rust`
Expected: PASS

- [ ] **Step 4: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
poetry run python -m black tests/integration/test_rust_box_deref.py
git add tests/integration/test_rust_box_deref.py
git commit -m "test: add integration tests for Rust Box auto-deref via __method_missing__"
```

---

## Task 8: Update CALL_METHOD __method_missing__ for Method Delegation

**Files:**
- Modify: `interpreter/executor.py` (Task 3's `__method_missing__` CALL_METHOD path)
- Modify: `tests/integration/test_rust_box_deref.py`

**Context:** Task 3's CALL_METHOD `__method_missing__` path passes ALL args (including the method name and original args) to `__method_missing__`. But Box's `__method_missing__` only does `LOAD_FIELD_INDIRECT` — it returns the field value, not a method call result. For method calls on Box-wrapped objects, the VM needs to: (1) call `__method_missing__(self, name)` to get the method ref, (2) then invoke it with the original args.

Revisit this task ONLY if the integration tests from Task 7 show method call delegation failing. If they pass (because the test programs only use field access), defer this to a follow-up.

- [ ] **Step 1: Write integration test for method call delegation**

Add to `tests/integration/test_rust_box_deref.py`:

```python
class TestBoxMethodDelegation:
    def test_box_method_call_delegates_to_inner(self):
        """box_val.method() delegates to inner object's method via __method_missing__."""
        _, local_vars = _run_rust(
            """\
struct Counter { count: i32 }

impl Counter {
    fn get_count(&self) -> i32 {
        return self.count;
    }
}

let c = Counter { count: 42 };
let b = Box::new(c);
let answer = b.get_count();
""",
            max_steps=600,
        )
        assert local_vars["answer"] == 42
```

- [ ] **Step 2: Run test and diagnose**

Run: `poetry run python -m pytest tests/integration/test_rust_box_deref.py::TestBoxMethodDelegation -v`

If PASS: method delegation works via field access + CALL_UNKNOWN. Done.
If FAIL: the CALL_METHOD path needs adjustment — `__method_missing__` returns the method ref but doesn't call it. Update the CALL_METHOD `__method_missing__` path to invoke the returned value with original args.

- [ ] **Step 3: Fix if needed (conditional)**

If the test fails, update the CALL_METHOD `__method_missing__` path in `executor.py` to:
1. Call `__method_missing__(self, name)` — gets method ref
2. If result is a BoundFuncRef, dispatch to it with original args
3. Otherwise, return the result as-is

- [ ] **Step 4: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
poetry run python -m black interpreter/executor.py tests/integration/test_rust_box_deref.py
git add interpreter/executor.py tests/integration/test_rust_box_deref.py
git commit -m "feat: handle Box method call delegation via __method_missing__"
```

---

## Task 9: Close Issue + Final Verification

**Files:**
- No code changes

- [ ] **Step 1: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass, no regressions

- [ ] **Step 2: Close beads issue**

```bash
bd update red-dragon-riy --status closed
```

- [ ] **Step 3: Push**

```bash
git push origin main
```
