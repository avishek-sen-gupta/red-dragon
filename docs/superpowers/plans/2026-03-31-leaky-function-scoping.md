# Leaky Function Scoping Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix VM scoping so that inner functions defined inside outer functions in Ruby, PHP, and Lua are accessible from global scope after the outer function returns.

**Architecture:** Add an injectable `FunctionScopingStrategy` to `ExecutionStrategies` and `HandlerContext`. The default (`LocalFunctionScopingStrategy`) preserves existing behaviour. `GlobalLeakFunctionScopingStrategy` (used for Ruby/PHP/Lua) additionally writes `FuncRef`/`BoundFuncRef` values to the global frame when stored inside a nested frame. `_write_var_to_frame` delegates to the strategy for function-ref values.

**Process: Test-Driven Development (TDD).** Every task follows red → green → commit. Write the failing test first. Run it to confirm it fails for the right reason. Write only enough implementation to make it pass. Never write implementation code before a failing test exists. Tasks 2–4 are wiring steps with no new behaviour — the regression gate (full test suite) serves as the red check for those.

**Tech Stack:** Python 3.13+, pytest, poetry

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `interpreter/vm/function_scoping.py` | ABC + two concrete strategies |
| Modify | `interpreter/vm/executor.py` | Add `function_scoping` to `HandlerContext` |
| Modify | `interpreter/handlers/_common.py` | Delegate FuncRef writes to strategy |
| Modify | `interpreter/run.py` | Add field to `ExecutionStrategies`, add helper, thread into `base_ctx` and both strategy builders |
| Create | `tests/unit/test_function_scoping_strategy.py` | Unit tests for strategy objects |
| Modify | `tests/unit/rosetta/test_rosetta_nested_functions.py` | Remove `xfail` from `test_inner_leaks_outside_outer` |

---

## Task 1: Create `FunctionScopingStrategy` with two implementations

**Files:**
- Create: `interpreter/vm/function_scoping.py`
- Create: `tests/unit/test_function_scoping_strategy.py`

- [ ] **Step 1: Write failing unit tests**

```python
# tests/unit/test_function_scoping_strategy.py
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from interpreter.types.typed_value import TypedValue, typed
from interpreter.types.type_expr import scalar
from interpreter.var_name import VarName
from interpreter.vm.function_scoping import (
    GlobalLeakFunctionScopingStrategy,
    LocalFunctionScopingStrategy,
)
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import StackFrame
from interpreter.func_name import FuncName
from interpreter.refs.func_ref import FuncRef
from interpreter.ir import CodeLabel


def _make_func_ref_value() -> TypedValue:
    ref = FuncRef(name=FuncName("inner"), label=CodeLabel("func_inner"))
    return typed(ref, scalar("function"))


def _make_vm_with_depth(depth: int) -> tuple[VMState, StackFrame]:
    """Create a VMState with `depth` frames. Returns (vm, top_frame)."""
    vm = VMState()
    for i in range(depth):
        vm.call_stack.append(StackFrame(function_name=FuncName(f"frame_{i}")))
    return vm, vm.call_stack[-1]


NAME = VarName("inner")


class TestLocalFunctionScopingStrategy:
    def test_writes_to_current_frame_at_depth_1(self):
        vm, frame = _make_vm_with_depth(1)
        value = _make_func_ref_value()
        LocalFunctionScopingStrategy().register_func(NAME, value, vm, frame)
        assert frame.local_vars[NAME] == value

    def test_does_not_write_to_global_frame_at_depth_2(self):
        vm, frame = _make_vm_with_depth(2)
        value = _make_func_ref_value()
        LocalFunctionScopingStrategy().register_func(NAME, value, vm, frame)
        assert frame.local_vars[NAME] == value
        assert NAME not in vm.call_stack[0].local_vars


class TestGlobalLeakFunctionScopingStrategy:
    def test_writes_to_current_frame_at_depth_1(self):
        vm, frame = _make_vm_with_depth(1)
        value = _make_func_ref_value()
        GlobalLeakFunctionScopingStrategy().register_func(NAME, value, vm, frame)
        assert frame.local_vars[NAME] == value

    def test_no_double_write_at_depth_1(self):
        """current_frame IS global frame at depth 1 — only one write."""
        vm, frame = _make_vm_with_depth(1)
        value = _make_func_ref_value()
        GlobalLeakFunctionScopingStrategy().register_func(NAME, value, vm, frame)
        assert vm.call_stack[0].local_vars[NAME] == value
        # value written exactly once (same object)
        assert frame is vm.call_stack[0]

    def test_writes_to_both_frames_at_depth_2(self):
        vm, frame = _make_vm_with_depth(2)
        value = _make_func_ref_value()
        GlobalLeakFunctionScopingStrategy().register_func(NAME, value, vm, frame)
        assert frame.local_vars[NAME] == value
        assert vm.call_stack[0].local_vars[NAME] == value

    def test_writes_to_both_frames_at_depth_3(self):
        vm, frame = _make_vm_with_depth(3)
        value = _make_func_ref_value()
        GlobalLeakFunctionScopingStrategy().register_func(NAME, value, vm, frame)
        assert frame.local_vars[NAME] == value
        assert vm.call_stack[0].local_vars[NAME] == value
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/test_function_scoping_strategy.py -v
```

Expected: `ImportError` — `function_scoping` module does not exist yet.

- [ ] **Step 3: Create `interpreter/vm/function_scoping.py`**

```python
"""Function scoping strategies — controls where FuncRef/BoundFuncRef values are registered.

LocalFunctionScopingStrategy (default):
    Writes only to the current frame. Correct for all lexically-scoped languages.

GlobalLeakFunctionScopingStrategy:
    Writes to the current frame AND the global frame (call_stack[0]) when nested.
    Used for Ruby, PHP, and Lua where inner function definitions leak to global scope.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from interpreter.types.typed_value import TypedValue
from interpreter.var_name import VarName
from interpreter.vm.vm import VMState
from interpreter.vm.vm_types import StackFrame


class FunctionScopingStrategy(ABC):
    """Strategy for registering function-ref values when executing STORE_VAR/DECL_VAR."""

    @abstractmethod
    def register_func(
        self,
        name: VarName,
        value: TypedValue,
        vm: VMState,
        current_frame: StackFrame,
    ) -> None:
        """Write *value* to the appropriate frame(s) in *vm*."""


class LocalFunctionScopingStrategy(FunctionScopingStrategy):
    """Default: write to the current frame only."""

    def register_func(
        self,
        name: VarName,
        value: TypedValue,
        vm: VMState,
        current_frame: StackFrame,
    ) -> None:
        current_frame.local_vars[name] = value


class GlobalLeakFunctionScopingStrategy(FunctionScopingStrategy):
    """Ruby/PHP/Lua: write to current frame and global frame when nested."""

    def register_func(
        self,
        name: VarName,
        value: TypedValue,
        vm: VMState,
        current_frame: StackFrame,
    ) -> None:
        current_frame.local_vars[name] = value
        if len(vm.call_stack) > 1:
            vm.call_stack[0].local_vars[name] = value
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/test_function_scoping_strategy.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
bd backup
git add interpreter/vm/function_scoping.py tests/unit/test_function_scoping_strategy.py
git commit -m "feat: add FunctionScopingStrategy with local and global-leak implementations"
```

---

## Task 2: Thread `FunctionScopingStrategy` into `HandlerContext`

**Files:**
- Modify: `interpreter/vm/executor.py:59-115`

- [ ] **Step 1: Add import and field to `HandlerContext`**

In `interpreter/vm/executor.py`, add the import after the existing `field_fallback` import:

```python
from interpreter.vm.function_scoping import (
    FunctionScopingStrategy,
    LocalFunctionScopingStrategy,
)
```

Add field to `HandlerContext` after `field_fallback`:

```python
field_fallback: FieldFallbackStrategy
symbol_table: SymbolTable
function_scoping: FunctionScopingStrategy
```

Add default in `_default_handler_context()` after `field_fallback=_NO_FIELD_FALLBACK`:

```python
field_fallback=_NO_FIELD_FALLBACK,
symbol_table=SymbolTable.empty(),
function_scoping=LocalFunctionScopingStrategy(),
```

- [ ] **Step 2: Run full test suite to verify no regressions**

```bash
poetry run python -m pytest tests/ -x -q
```

Expected: all existing tests pass (new field has a default so no callers break).

- [ ] **Step 3: Commit**

```bash
bd backup
git add interpreter/vm/executor.py
git commit -m "feat: add function_scoping field to HandlerContext"
```

---

## Task 3: Delegate FuncRef writes to strategy in `_write_var_to_frame`

**Files:**
- Modify: `interpreter/handlers/_common.py:59-75`
- Modify: `tests/unit/test_function_scoping_strategy.py`

- [ ] **Step 1: Write a failing test that proves the strategy is not yet called**

Add to `tests/unit/test_function_scoping_strategy.py`:

```python
from interpreter.handlers._common import _write_var_to_frame
from interpreter.vm.function_scoping import GlobalLeakFunctionScopingStrategy
from interpreter.vm.executor import HandlerContext, _default_handler_context


class TestWriteVarToFrameDelegation:
    def test_funcref_written_to_global_frame_via_strategy(self):
        """_write_var_to_frame must call the strategy for FuncRef values."""
        vm, frame = _make_vm_with_depth(2)
        value = _make_func_ref_value()
        ctx = _default_handler_context()
        ctx = HandlerContext(
            **{**ctx.__dict__, "function_scoping": GlobalLeakFunctionScopingStrategy()}
        )
        _write_var_to_frame(vm, frame, NAME, value, ctx)
        # Strategy must have written to global frame
        assert vm.call_stack[0].local_vars[NAME] == value

    def test_non_funcref_not_delegated_to_strategy(self):
        """Plain values bypass the strategy entirely."""
        vm, frame = _make_vm_with_depth(2)
        plain = typed(42, scalar("int"))
        ctx = _default_handler_context()
        _write_var_to_frame(vm, frame, NAME, plain, ctx)
        assert frame.local_vars[NAME] == plain
        assert NAME not in vm.call_stack[0].local_vars
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
poetry run python -m pytest tests/unit/test_function_scoping_strategy.py::TestWriteVarToFrameDelegation -v
```

Expected: FAIL — `_write_var_to_frame` does not accept a `ctx` argument yet.

- [ ] **Step 3: Implement — update `_write_var_to_frame` signature and body**

The current signature:
```python
def _write_var_to_frame(
    vm: VMState, frame: StackFrame, name: VarName, tv: TypedValue
) -> None:
```

New signature and body (add `ctx` parameter, delegate FuncRef writes):

```python
def _write_var_to_frame(
    vm: VMState, frame: StackFrame, name: VarName, tv: TypedValue, ctx: Any = None
) -> None:
    """Write a variable to a specific frame, handling aliases and closure envs."""
    from interpreter.refs.func_ref import FuncRef, BoundFuncRef

    alias_ptr = frame.var_heap_aliases.get(name)
    if alias_ptr and vm.heap_contains(alias_ptr.base):
        vm.heap_get(alias_ptr.base).fields[
            FieldName(str(alias_ptr.offset), FieldKind.INDEX)
        ] = tv
    elif ctx is not None and isinstance(tv.value, (FuncRef, BoundFuncRef)):
        ctx.function_scoping.register_func(name, tv, vm, frame)
    else:
        frame.local_vars[name] = tv
    if frame.closure_env_id and name in frame.captured_var_names:
        env = vm.closures.get(frame.closure_env_id)
        if env:
            env.bindings[name] = tv
```

Note: `ctx` defaults to `None` so all existing call sites without `ctx` continue to work unchanged (local-only write). Only callers that pass `ctx` get the strategy dispatch.

- [ ] **Step 2: Update callers in `interpreter/handlers/variables.py` to pass `ctx`**

Find all calls to `_write_var_to_frame` in `variables.py`:

```bash
grep -n "_write_var_to_frame" interpreter/handlers/variables.py
```

For each call site that handles `DECL_VAR` and `STORE_VAR`, add `ctx` as the last argument. Example — if the call looks like:

```python
_write_var_to_frame(vm, frame, name, tv)
```

Change to:

```python
_write_var_to_frame(vm, frame, name, tv, ctx)
```

Only update call sites in `_handle_decl_var` and `_handle_store_var`. Leave any other callers as-is.

- [ ] **Step 3: Run full test suite to verify no regressions**

```bash
poetry run python -m pytest tests/ -x -q
```

Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
bd backup
git add interpreter/handlers/_common.py interpreter/handlers/variables.py
git commit -m "feat: delegate FuncRef writes in _write_var_to_frame to FunctionScopingStrategy"
```

---

## Task 4: Add `function_scoping` to `ExecutionStrategies` and thread into `base_ctx`

**Files:**
- Modify: `interpreter/run.py`

- [ ] **Step 1: Add import**

In `interpreter/run.py`, add after the `field_fallback` import:

```python
from interpreter.vm.function_scoping import (
    FunctionScopingStrategy,
    LocalFunctionScopingStrategy,
    GlobalLeakFunctionScopingStrategy,
)
```

- [ ] **Step 2: Add field to `ExecutionStrategies`**

After the `field_fallback` field:

```python
field_fallback: FieldFallbackStrategy = dataclass_field(
    default_factory=NoFieldFallback
)
function_scoping: FunctionScopingStrategy = dataclass_field(
    default_factory=LocalFunctionScopingStrategy
)
symbol_table: SymbolTable = dataclass_field(default_factory=SymbolTable.empty)
```

- [ ] **Step 3: Add per-language helper**

After `_field_fallback_for_language`:

```python
_LEAKY_SCOPING_LANGS: frozenset[Language] = frozenset(
    {Language.RUBY, Language.PHP, Language.LUA}
)


def _function_scoping_for_language(lang: Language) -> FunctionScopingStrategy:
    """Select FunctionScopingStrategy based on source language.

    Ruby, PHP, and Lua leak inner function definitions to global scope.
    All other languages use lexical (local) scoping for inner functions.
    """
    if lang in _LEAKY_SCOPING_LANGS:
        return GlobalLeakFunctionScopingStrategy()
    return LocalFunctionScopingStrategy()
```

- [ ] **Step 4: Thread into `base_ctx` in `execute_cfg`**

In the `base_ctx = HandlerContext(...)` construction, add after `field_fallback`:

```python
field_fallback=strategies.field_fallback,
function_scoping=strategies.function_scoping,
symbol_table=strategies.symbol_table,
```

- [ ] **Step 5: Thread into both strategy builder functions**

In `_build_strategies_from_frontend`, add to the `return ExecutionStrategies(...)` call after `field_fallback`:

```python
field_fallback=_field_fallback_for_language(lang),
function_scoping=_function_scoping_for_language(lang),
symbol_table=frontend.symbol_table,
```

In `_build_strategies_from_linked`, add to the `return ExecutionStrategies(...)` call after `field_fallback`:

```python
field_fallback=_field_fallback_for_language(linked.language),
function_scoping=_function_scoping_for_language(linked.language),
symbol_table=linked.symbol_table,
```

- [ ] **Step 6: Run full test suite**

```bash
poetry run python -m pytest tests/ -x -q
```

Expected: all existing tests pass.

- [ ] **Step 7: Commit**

```bash
bd backup
git add interpreter/run.py
git commit -m "feat: thread FunctionScopingStrategy through ExecutionStrategies and HandlerContext"
```

---

## Task 5: Enable the xfail integration tests

**Files:**
- Modify: `tests/unit/rosetta/test_rosetta_nested_functions.py`

- [ ] **Step 1: Run the xfail tests to confirm current failure mode**

```bash
poetry run python -m pytest tests/unit/rosetta/test_rosetta_nested_functions.py::TestNestedFunctionLeakyScoping::test_inner_leaks_outside_outer -v
```

Expected: 3 tests XFAIL (one per language: lua, php, ruby).

- [ ] **Step 2: Remove the `xfail` marker**

Find this block (lines ~588-596):

```python
@pytest.mark.xfail(
    strict=True,
    reason=(
        "VM enforces frame-based scoping; in real Ruby/PHP/Lua, "
        "inner functions leak to enclosing/global scope — red-dragon-crds"
    ),
)
def test_inner_leaks_outside_outer(self, leaky_result):
```

Replace with:

```python
def test_inner_leaks_outside_outer(self, leaky_result):
```

- [ ] **Step 3: Run the formerly-xfail tests to confirm they now pass**

```bash
poetry run python -m pytest tests/unit/rosetta/test_rosetta_nested_functions.py::TestNestedFunctionLeakyScoping -v
```

Expected: all 9 tests PASS (3 languages × 3 test methods: `test_inner_accessible_inside_outer`, `test_inner_leaks_outside_outer`, `test_zero_llm_calls`).

- [ ] **Step 4: Run full test suite**

```bash
poetry run python -m pytest tests/ -x -q
```

Expected: 13,227+ tests pass (3 formerly-xfail now counted as pass), 0 xfailed in `TestNestedFunctionLeakyScoping`.

- [ ] **Step 5: Close the issue and commit**

```bash
bd update red-dragon-crds --close --reason "GlobalLeakFunctionScopingStrategy writes FuncRefs to global frame for Ruby/PHP/Lua; xfail removed from TestNestedFunctionLeakyScoping"
bd backup
git add tests/unit/rosetta/test_rosetta_nested_functions.py
git commit -m "fix: enable leaky scoping for Ruby/PHP/Lua inner functions (red-dragon-crds)"
```

---

## Task 6: Final verification and push

- [ ] **Step 1: Run full verification gate**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/ -x -q
```

Expected: formatting clean, 5/5 contracts kept, all tests pass.

- [ ] **Step 2: Push**

```bash
git push
```
