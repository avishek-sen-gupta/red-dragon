# FuncName Domain Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `str` function/method name fields on IR instructions with `FuncName`, introducing accessor methods on all registries and builtin tables as the permanent API. Every commit is independently green.

**Architecture:** Accessor-based incremental migration. Add accessors that unwrap `str()` first, migrate callers to accessors, wrap construction sites, then per-dict change key types and remove `str()` from accessors. No str bridge on FuncName.

**Tech Stack:** Python 3.13+, pytest, Poetry

**Spec:** `docs/superpowers/specs/2026-03-28-funcname-domain-type-design.md`
**Issue:** red-dragon-cnz9

---

## Task 1: Define FuncName type and tests

**Files:**
- Create: `interpreter/func_name.py`
- Create: `tests/unit/test_func_name.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for FuncName domain type."""
import pytest
from interpreter.func_name import FuncName, NoFuncName, NO_FUNC_NAME


class TestFuncName:
    def test_str(self):
        assert str(FuncName("add")) == "add"

    def test_value(self):
        assert FuncName("add").value == "add"

    def test_is_present(self):
        assert FuncName("add").is_present()

    def test_equality(self):
        assert FuncName("add") == FuncName("add")
        assert FuncName("add") != FuncName("sub")

    def test_not_equal_to_string(self):
        assert FuncName("add") != "add"

    def test_hash(self):
        assert hash(FuncName("add")) == hash(FuncName("add"))

    def test_dict_lookup(self):
        d = {FuncName("add"): 42}
        assert d[FuncName("add")] == 42

    def test_lt(self):
        assert FuncName("a") < FuncName("b")

    def test_startswith(self):
        assert FuncName("__cobol_accept").startswith("__cobol_")
        assert not FuncName("add").startswith("__cobol_")

    def test_contains(self):
        assert "[" in FuncName("Box[Node]")
        assert "[" not in FuncName("add")

    def test_post_init_rejects_double_wrap(self):
        with pytest.raises(TypeError, match="must be str"):
            FuncName(FuncName("add"))


class TestNoFuncName:
    def test_str(self):
        assert str(NO_FUNC_NAME) == ""

    def test_not_present(self):
        assert not NO_FUNC_NAME.is_present()

    def test_is_instance(self):
        assert isinstance(NO_FUNC_NAME, FuncName)
```

- [ ] **Step 2: Implement FuncName**

```python
"""FuncName — typed function/method name."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class FuncName:
    """A function or method name."""
    value: str

    def __post_init__(self):
        if not isinstance(self.value, str):
            raise TypeError(
                f"FuncName.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def is_present(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FuncName):
            return self.value == other.value
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, FuncName):
            return self.value < other.value
        return NotImplemented

    def startswith(self, prefix: str) -> bool:
        return self.value.startswith(prefix)

    def __contains__(self, item: str) -> bool:
        return item in self.value


@dataclass(frozen=True, eq=False)
class NoFuncName(FuncName):
    """Null object: no function name."""
    value: str = ""

    def is_present(self) -> bool:
        return False


NO_FUNC_NAME = NoFuncName()
```

- [ ] **Step 3: Run tests, format, lint, commit**

```bash
poetry run python -m pytest tests/unit/test_func_name.py -v
poetry run python -m black .
poetry run lint-imports
bd backup
git add interpreter/func_name.py tests/unit/test_func_name.py
git commit -m "Add FuncName domain type — no str bridge"
```

---

## Task 2: Add accessor methods to all registries/tables (unwrapping with str())

**Files:**
- Modify: `interpreter/registry.py` (lines 18-28, 178)
- Modify: `interpreter/vm/builtins.py` (lines 339, 366)
- Modify: `interpreter/types/type_inference.py` (lines 181, 187-189)
- Modify: `interpreter/cobol/io_provider.py` (line 53)
- Modify: `interpreter/cfg.py` (line 331)
- Create: `tests/unit/test_func_name_accessors.py`

Each accessor takes `FuncName`, unwraps with `str()`, and looks up the existing str-keyed dict. Dicts stay str-keyed. This is the transitional state.

- [ ] **Step 1: Add accessors to FunctionRegistry**

```python
# interpreter/registry.py
from interpreter.func_name import FuncName

class FunctionRegistry:
    # existing fields unchanged (still str-keyed)

    def lookup_func(self, name: FuncName) -> FuncRef | None:
        return self.func_refs.get(str(name))

    def lookup_methods(self, class_name: str, name: FuncName) -> list[CodeLabel]:
        return self.class_methods.get(class_name, {}).get(str(name), [])

    def register_func(self, name: FuncName, ref: FuncRef) -> None:
        self.func_refs[str(name)] = ref

    def register_method(self, class_name: str, name: FuncName, label: CodeLabel) -> None:
        self.class_methods.setdefault(class_name, {}).setdefault(str(name), []).append(label)
```

- [ ] **Step 2: Add accessors to Builtins**

```python
# interpreter/vm/builtins.py
from interpreter.func_name import FuncName

class Builtins:
    # TABLE and METHOD_TABLE unchanged

    @classmethod
    def lookup_builtin(cls, name: FuncName) -> Any | None:
        return cls.TABLE.get(str(name))

    @classmethod
    def lookup_method_builtin(cls, name: FuncName) -> Any | None:
        return cls.METHOD_TABLE.get(str(name))
```

- [ ] **Step 3: Add accessors to _InferenceContext**

```python
# interpreter/types/type_inference.py
from interpreter.func_name import FuncName

class _InferenceContext:
    # existing fields unchanged

    def lookup_func_return_type(self, name: FuncName) -> TypeExpr:
        return self.func_return_types.get(str(name), UNKNOWN)

    def lookup_method_type(self, class_name: TypeExpr, name: FuncName) -> TypeExpr:
        return self.class_method_types.get(class_name, {}).get(str(name), UNKNOWN)

    def store_func_return_type(self, name: FuncName, type_expr: TypeExpr) -> None:
        self.func_return_types[str(name)] = type_expr
```

- [ ] **Step 4: Add accessor to COBOL io_provider**

```python
# interpreter/cobol/io_provider.py
from interpreter.func_name import FuncName

class CobolIOProvider:
    def dispatch(self, name: FuncName) -> str | None:
        return _COBOL_IO_DISPATCH.get(str(name))
```

- [ ] **Step 5: Add accessor to cfg.py call_target_map**

```python
# interpreter/cfg.py — add function or use inline
# call_target_map.get(str(func_name)) at line 331
```

- [ ] **Step 6: Write tests for accessors**

```python
# tests/unit/test_func_name_accessors.py
from interpreter.func_name import FuncName
from interpreter.registry import FunctionRegistry
from interpreter.refs.func_ref import FuncRef
from interpreter.ir import CodeLabel

class TestRegistryAccessors:
    def test_lookup_func_found(self):
        reg = FunctionRegistry()
        ref = FuncRef(name="add", label=CodeLabel("func_add_0"))
        reg.register_func(FuncName("add"), ref)
        assert reg.lookup_func(FuncName("add")) == ref

    def test_lookup_func_not_found(self):
        reg = FunctionRegistry()
        assert reg.lookup_func(FuncName("missing")) is None

    def test_lookup_methods(self):
        reg = FunctionRegistry()
        label = CodeLabel("func_get_0")
        reg.register_method("MyClass", FuncName("get"), label)
        assert reg.lookup_methods("MyClass", FuncName("get")) == [label]

    def test_lookup_methods_not_found(self):
        reg = FunctionRegistry()
        assert reg.lookup_methods("MyClass", FuncName("missing")) == []
```

- [ ] **Step 7: Run full test suite, format, lint, commit**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Add FuncName accessor methods to all registries/tables (str() unwrap)"
```

---

## Task 3: Migrate all callers to use accessors

**Files:**
- Modify: `interpreter/handlers/calls.py` (lines 76-78, 464-465, 477, 519-520, 536-537, 563)
- Modify: `interpreter/handlers/memory.py` (lines 74, 114)
- Modify: `interpreter/interprocedural/call_graph.py` (lines 73, 88-89)
- Modify: `interpreter/types/type_inference.py` (lines 540-541, 545, 703-704, 782, 806-807)
- Modify: `interpreter/cfg.py` (line 331)
- Modify: `interpreter/cobol/io_provider.py` (line 53)

Replace all direct dict access with accessor calls. Callers pass `FuncName(str_value)` to the accessor. The accessor unwraps — so this is a no-op functionally.

- [ ] **Step 1: Migrate calls.py builtin lookups**

```python
# Line 76-78: _try_builtin_call
# Before: if func_name not in Builtins.TABLE:
# After:
builtin_fn = Builtins.lookup_builtin(FuncName(func_name) if isinstance(func_name, str) else func_name)
if builtin_fn is None:
    return ExecutionResult.not_handled()
result = builtin_fn(args, vm)
```

- [ ] **Step 2: Migrate calls.py class_methods lookups**

```python
# Lines 464-465, 519-520, 536-537, 563: methods.get(method_name, [])
# Before: methods = ctx.registry.class_methods.get(class_name, {})
#          func_labels = methods.get(method_name, [])
# After:
func_labels = ctx.registry.lookup_methods(class_name, FuncName(method_name) if isinstance(method_name, str) else method_name)

# Line 477: Builtins.METHOD_TABLE.get(method_name)
# After:
method_fn = Builtins.lookup_method_builtin(FuncName(method_name) if isinstance(method_name, str) else method_name)
```

- [ ] **Step 3: Migrate memory.py class_methods lookups**

```python
# Lines 74, 114: registry.class_methods.get(type_name, {}).get(...)
# After: registry.lookup_methods(type_name, FuncName(constants.METHOD_MISSING))
```

- [ ] **Step 4: Migrate call_graph.py lookups**

```python
# Line 73: registry.func_refs.get(target)
# After: registry.lookup_func(FuncName(target))

# Line 89: methods.get(method_name, [])
# After: registry.lookup_methods(_class_name, FuncName(method_name))
```

- [ ] **Step 5: Migrate type_inference.py lookups**

```python
# Lines 703-704: ctx.func_return_types[func_name]
# After: ctx.lookup_func_return_type(FuncName(func_name))

# Line 782: ctx.class_method_types[class_name].get(method_name, UNKNOWN)
# After: ctx.lookup_method_type(class_name, FuncName(method_name))

# Lines 806-807: ctx.func_return_types[method_name]
# After: ctx.lookup_func_return_type(FuncName(method_name))
```

- [ ] **Step 6: Migrate cfg.py lookup**

```python
# Line 331: call_target_map.get(func_name)
# After: call_target_map.get(str(func_name))  # cfg visualization, str boundary
```

- [ ] **Step 7: Migrate COBOL io_provider**

```python
# Line 53: method_name = _COBOL_IO_DISPATCH.get(func_name)
# After: method_name = self.dispatch(FuncName(func_name) if isinstance(func_name, str) else func_name)
```

- [ ] **Step 8: Run full test suite, format, lint, commit**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Migrate all callers to FuncName accessor methods"
```

---

## Task 4: Wrap frontend/COBOL construction sites + change instruction fields

**Files:**
- Modify: `interpreter/instructions.py` (lines 345, 370, 419, converters 1036-1092)
- Modify: ~40 frontend files + COBOL files
- Modify: ~14 test files constructing CallFunction/CallMethod/CallCtorFunction

Dispatch 6-8 parallel subagents for frontend wrapping. Change instruction fields to `FuncName`.

- [ ] **Step 1: Change instruction field types and converters**

```python
# interpreter/instructions.py
from interpreter.func_name import FuncName, NO_FUNC_NAME

# CallFunction (line 345)
func_name: FuncName = NO_FUNC_NAME

# CallMethod (line 370)
method_name: FuncName = NO_FUNC_NAME

# CallCtorFunction (line 419)
func_name: FuncName = NO_FUNC_NAME

# operands: str(self.func_name) / str(self.method_name)
# converters: FuncName(str(ops[...])) or NO_FUNC_NAME
```

- [ ] **Step 2: Dispatch 6-8 parallel subagents to wrap ~307 frontend/COBOL sites**

Each wraps `func_name=X` → `func_name=FuncName(X)` and `method_name=X` → `method_name=FuncName(X)` on CallFunction/CallMethod/CallCtorFunction only.

- [ ] **Step 3: Update test files constructing these instructions with raw strings**

- [ ] **Step 4: Remove isinstance checks in callers**

After field types change, callers in calls.py that do `FuncName(func_name) if isinstance(func_name, str) else func_name` can simplify to just `func_name` (it's already FuncName).

- [ ] **Step 5: Run full test suite, format, lint, commit**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Wrap all frontend/COBOL func_name/method_name sites with FuncName"
```

---

## Task 5: Migrate Builtins.TABLE → dict[FuncName, ...]

**Files:**
- Modify: `interpreter/vm/builtins.py` (line 339+)

- [ ] **Step 1: Change TABLE keys from str to FuncName**

```python
TABLE: dict[FuncName, Any] = {
    FuncName("len"): _builtin_len,
    FuncName("strlen"): _builtin_len,
    FuncName("range"): _builtin_range,
    # ... all entries
}
```

- [ ] **Step 2: Remove str() from lookup_builtin accessor**

```python
@classmethod
def lookup_builtin(cls, name: FuncName) -> Any | None:
    return cls.TABLE.get(name)  # was: cls.TABLE.get(str(name))
```

- [ ] **Step 3: Run full test suite, format, lint, commit**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Migrate Builtins.TABLE to FuncName keys"
```

---

## Task 6: Migrate Builtins.METHOD_TABLE → dict[FuncName, ...]

**Files:**
- Modify: `interpreter/vm/builtins.py` (line 366+)

- [ ] **Step 1: Change METHOD_TABLE keys to FuncName**

Same pattern as Task 5.

- [ ] **Step 2: Remove str() from lookup_method_builtin accessor**

- [ ] **Step 3: Run full test suite, format, lint, commit**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Migrate Builtins.METHOD_TABLE to FuncName keys"
```

---

## Task 7: Migrate FunctionRegistry.func_refs → dict[FuncName, FuncRef]

**Files:**
- Modify: `interpreter/registry.py` (line 28, 178)

- [ ] **Step 1: Change func_refs field type and population**

```python
func_refs: dict[FuncName, FuncRef] = field(default_factory=dict)

# Line 178:
reg.func_refs = {FuncName(ref.name): ref for ref in func_symbol_table.values()}
```

- [ ] **Step 2: Remove str() from lookup_func and register_func**

```python
def lookup_func(self, name: FuncName) -> FuncRef | None:
    return self.func_refs.get(name)  # was: str(name)

def register_func(self, name: FuncName, ref: FuncRef) -> None:
    self.func_refs[name] = ref  # was: str(name)
```

- [ ] **Step 3: Run full test suite, format, lint, commit**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Migrate FunctionRegistry.func_refs to FuncName keys"
```

---

## Task 8: Migrate FunctionRegistry.class_methods inner key → FuncName

**Files:**
- Modify: `interpreter/registry.py` (line 22, 136)

- [ ] **Step 1: Change class_methods inner key type and population**

```python
class_methods: dict[str, dict[FuncName, list[CodeLabel]]] = field(default_factory=dict)

# Line 136:
class_methods[in_class].setdefault(FuncName(ref.name), []).append(ref.label)
```

- [ ] **Step 2: Remove str() from lookup_methods and register_method**

```python
def lookup_methods(self, class_name: str, name: FuncName) -> list[CodeLabel]:
    return self.class_methods.get(class_name, {}).get(name, [])  # was: str(name)

def register_method(self, class_name: str, name: FuncName, label: CodeLabel) -> None:
    self.class_methods.setdefault(class_name, {}).setdefault(name, []).append(label)  # was: str(name)
```

- [ ] **Step 3: Fix any other direct class_methods access**

Grep for `class_methods[` and `class_methods.get(` across interpreter/ — any remaining direct access must go through `lookup_methods`.

- [ ] **Step 4: Run full test suite, format, lint, commit**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Migrate FunctionRegistry.class_methods inner key to FuncName"
```

---

## Task 9: Migrate type_inference + call_graph + COBOL dispatch dicts

**Files:**
- Modify: `interpreter/types/type_inference.py` (lines 181, 187-189, and accessor methods)
- Modify: `interpreter/interprocedural/call_graph.py`
- Modify: `interpreter/cobol/io_provider.py` (line 28+)

- [ ] **Step 1: Migrate func_return_types and class_method_types**

```python
# type_inference.py
func_return_types: dict[FuncName, TypeExpr] = field(default_factory=dict)
class_method_types: dict[TypeExpr, dict[FuncName, TypeExpr]] = field(default_factory=dict)
```

Remove `str()` from `lookup_func_return_type`, `lookup_method_type`, `store_func_return_type`.

- [ ] **Step 2: Migrate COBOL io_provider dispatch table**

```python
_COBOL_IO_DISPATCH: dict[FuncName, str] = {
    FuncName("__cobol_accept"): "_accept",
    FuncName("__cobol_open_file"): "_open_file",
    # ... all entries
}
```

Remove `str()` from `dispatch` accessor.

- [ ] **Step 3: Migrate call_graph lookups**

Ensure call_graph uses `FuncName` throughout. `_build_call_target_map` keys become `FuncName`.

- [ ] **Step 4: Run full test suite, format, lint, commit**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Migrate type_inference, call_graph, COBOL dispatch to FuncName keys"
```

---

## Task 10: Fix remaining test assertions + close issue

**Files:**
- Modify: various test files that directly access registry dicts or construct FuncName comparisons

- [ ] **Step 1: Find and fix test files that access dicts directly**

Grep tests/ for `func_refs[`, `class_methods[`, `TABLE[`, `METHOD_TABLE[`, `func_return_types[` — these should use accessors or FuncName keys.

- [ ] **Step 2: Run full test suite**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
```

Expected: 13,039+ passed.

- [ ] **Step 3: Format, lint, commit, close issue**

```bash
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Fix test assertions for FuncName, close cnz9

Issue: red-dragon-cnz9

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push
bd close cnz9 --reason "FuncName domain type complete: accessor pattern, all dicts FuncName-keyed, no str bridge. 13,039+ tests passing."
```
