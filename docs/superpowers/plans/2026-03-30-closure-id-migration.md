# ClosureId Domain Type Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace stringly-typed closure identifiers with a `ClosureId` frozen dataclass across the VM, following the established ContinuationName pattern.

**Architecture:** New `interpreter/closure_id.py` with `ClosureId`, `NoClosureId`, and `NO_CLOSURE_ID` sentinel. Migrate 3 field annotations, 1 dict key type, ~8 construction sites, ~8 consumer sites, and ~12 test references across ~10 files. No `__eq__(str)` bridge — clean break.

**Tech Stack:** Python 3.13+, dataclasses, pytest

**Spec:** `docs/superpowers/specs/2026-03-30-closure-id-design.md`

---

### Task 1: Create `ClosureId` Domain Type with Tests

**Files:**
- Create: `interpreter/closure_id.py`
- Create: `tests/unit/test_closure_id.py`

- [ ] **Step 1: Write failing tests for ClosureId**

Create `tests/unit/test_closure_id.py`:

```python
"""Unit tests for ClosureId domain type."""

from __future__ import annotations

import pytest

from interpreter.closure_id import ClosureId, NoClosureId, NO_CLOSURE_ID


class TestClosureId:
    def test_construction(self):
        cid = ClosureId("closure_42")
        assert cid.value == "closure_42"

    def test_str(self):
        cid = ClosureId("closure_42")
        assert str(cid) == "closure_42"

    def test_is_present(self):
        cid = ClosureId("closure_42")
        assert cid.is_present() is True

    def test_hash_and_dict_key(self):
        cid = ClosureId("closure_42")
        d = {cid: "env"}
        assert d[ClosureId("closure_42")] == "env"

    def test_equality(self):
        assert ClosureId("closure_42") == ClosureId("closure_42")
        assert ClosureId("closure_42") != ClosureId("closure_99")

    def test_no_str_equality(self):
        """ClosureId does not compare equal to bare strings."""
        assert ClosureId("closure_42") != "closure_42"
        assert ClosureId("closure_42").__eq__("closure_42") is NotImplemented

    def test_frozen(self):
        cid = ClosureId("closure_42")
        with pytest.raises(AttributeError):
            cid.value = "other"

    def test_bool_truthy(self):
        assert bool(ClosureId("closure_42")) is True

    def test_rejects_non_str(self):
        with pytest.raises(TypeError):
            ClosureId(42)

    def test_contains(self):
        cid = ClosureId("closure_42")
        assert "42" in cid


class TestNoClosureId:
    def test_is_present_false(self):
        assert NO_CLOSURE_ID.is_present() is False

    def test_value_is_empty(self):
        assert NO_CLOSURE_ID.value == ""

    def test_bool_falsy(self):
        assert bool(NO_CLOSURE_ID) is False

    def test_str_is_empty(self):
        assert str(NO_CLOSURE_ID) == ""

    def test_is_instance(self):
        assert isinstance(NO_CLOSURE_ID, ClosureId)
        assert isinstance(NO_CLOSURE_ID, NoClosureId)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_closure_id.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.closure_id'`

- [ ] **Step 3: Implement ClosureId**

Create `interpreter/closure_id.py`:

```python
"""ClosureId — typed closure environment identifier."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ClosureId:
    """A closure environment identifier (e.g., 'closure_42')."""

    value: str

    def __post_init__(self):
        if not isinstance(self.value, str):
            raise TypeError(
                f"ClosureId.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def is_present(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ClosureId):
            return self.value == other.value
        return NotImplemented

    def __bool__(self) -> bool:
        return bool(self.value)

    def __contains__(self, item: str) -> bool:
        return item in self.value


@dataclass(frozen=True, eq=False)
class NoClosureId(ClosureId):
    """Null object: no closure binding."""

    value: str = ""

    def is_present(self) -> bool:
        return False


NO_CLOSURE_ID = NoClosureId()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_closure_id.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
bd backup
git add interpreter/closure_id.py tests/unit/test_closure_id.py
git commit -m "Add ClosureId domain type with tests

Frozen dataclass following the ContinuationName pattern: ClosureId,
NoClosureId null object, NO_CLOSURE_ID sentinel. No __eq__(str) bridge."
```

---

### Task 2: Migrate `BoundFuncRef.closure_id` Field

**Files:**
- Modify: `interpreter/refs/func_ref.py`
- Modify: `tests/unit/test_func_ref.py`

- [ ] **Step 1: Update test_func_ref.py to use ClosureId**

In `tests/unit/test_func_ref.py`, add import and update all `closure_id=` references:

```python
# Add to imports:
from interpreter.closure_id import ClosureId, NO_CLOSURE_ID

# TestBoundFuncRef.test_construction_with_closure (line 41-45):
    def test_construction_with_closure(self):
        fr = FuncRef(name=FuncName("inner"), label=CodeLabel("func_inner_0"))
        bound = BoundFuncRef(func_ref=fr, closure_id=ClosureId("closure_42"))
        assert bound.func_ref.name == FuncName("inner")
        assert bound.func_ref.label == "func_inner_0"
        assert bound.closure_id == ClosureId("closure_42")

# TestBoundFuncRef.test_construction_without_closure (line 47-50):
    def test_construction_without_closure(self):
        fr = FuncRef(name=FuncName("add"), label=CodeLabel("func_add_0"))
        bound = BoundFuncRef(func_ref=fr)
        assert bound.closure_id == NO_CLOSURE_ID

# TestBoundFuncRef.test_frozen (line 52-58):
    def test_frozen(self):
        fr = FuncRef(name=FuncName("add"), label=CodeLabel("func_add_0"))
        bound = BoundFuncRef(func_ref=fr)
        import pytest
        with pytest.raises(AttributeError):
            bound.closure_id = "other"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_func_ref.py -v`
Expected: FAIL — `ClosureId("closure_42") != "closure_42"` (type mismatch since `BoundFuncRef.closure_id` is still `str`)

- [ ] **Step 3: Update BoundFuncRef**

In `interpreter/refs/func_ref.py`, change:

```python
# Add import:
from interpreter.closure_id import ClosureId, NO_CLOSURE_ID

# BoundFuncRef (line 19-24):
@dataclass(frozen=True)
class BoundFuncRef:
    """Runtime function reference with closure binding. Stored in registers."""

    func_ref: FuncRef
    closure_id: ClosureId = NO_CLOSURE_ID
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_func_ref.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
bd backup
git add interpreter/refs/func_ref.py tests/unit/test_func_ref.py
git commit -m "Migrate BoundFuncRef.closure_id from str to ClosureId"
```

---

### Task 3: Migrate VM Types (`StackFrame`, `StackFramePush`, `VMState.closures`)

**Files:**
- Modify: `interpreter/vm/vm_types.py`
- Modify: `tests/unit/test_materialize_raw_update.py`

- [ ] **Step 1: Update test_materialize_raw_update.py**

Change the `closure_env_id` reference at line 197:

```python
# Add import:
from interpreter.closure_id import ClosureId

# Line 197: closure_env_id="env_0" becomes:
                closure_env_id=ClosureId("env_0"),
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_materialize_raw_update.py -v`
Expected: FAIL — type mismatch (field is still `str`)

- [ ] **Step 3: Update vm_types.py**

In `interpreter/vm/vm_types.py`:

```python
# Add to imports (line 18, after continuation_name import):
from interpreter.closure_id import ClosureId, NO_CLOSURE_ID

# StackFrame.closure_env_id (line 107):
    closure_env_id: ClosureId = NO_CLOSURE_ID

# StackFrame.to_dict() (lines 123-124):
        if self.closure_env_id:
            d["closure_env_id"] = str(self.closure_env_id)

# VMState.closures (line 148):
    closures: dict[ClosureId, ClosureEnvironment] = field(default_factory=dict)

# StackFramePush.closure_env_id (line 282):
    closure_env_id: ClosureId = NO_CLOSURE_ID
```

Note: The `to_dict()` conditional `if self.closure_env_id:` works because `NO_CLOSURE_ID.__bool__()` returns `False`. The serialized value uses `str()` at the boundary.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_materialize_raw_update.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
bd backup
git add interpreter/vm/vm_types.py tests/unit/test_materialize_raw_update.py
git commit -m "Migrate StackFrame/StackFramePush/VMState.closures to ClosureId"
```

---

### Task 4: Migrate Construction Sites (handlers)

**Files:**
- Modify: `interpreter/handlers/variables.py`
- Modify: `interpreter/handlers/calls.py`
- Modify: `interpreter/handlers/memory.py`

- [ ] **Step 1: Update `interpreter/handlers/variables.py`**

```python
# Add import:
from interpreter.closure_id import ClosureId, NO_CLOSURE_ID

# Line 52: closure_id = "" becomes:
        closure_id = NO_CLOSURE_ID

# Line 69: closure_id = f"closure_{vm.symbolic_counter}" becomes:
            closure_id = ClosureId(f"closure_{vm.symbolic_counter}")

# Line 71: vm.closures[closure_id] = env — no change needed (ClosureId is hashable)

# Line 79: BoundFuncRef(func_ref=func_ref_entry, closure_id=closure_id) — no change needed (already ClosureId)
```

Also update the `env_id` variable (lines 55-67). `env_id` is `enclosing.closure_env_id` (already `ClosureId` after Task 3) or constructed from a string:

```python
# Line 63: env_id = f"{constants.ENV_ID_PREFIX}{vm.symbolic_counter}" becomes:
                env_id = ClosureId(f"{constants.ENV_ID_PREFIX}{vm.symbolic_counter}")

# Line 66: vm.closures[env_id] = env — no change needed
# Line 67: enclosing.closure_env_id = env_id — no change needed (both ClosureId now)
```

- [ ] **Step 2: Update `interpreter/handlers/calls.py`**

```python
# Add import:
from interpreter.closure_id import NO_CLOSURE_ID

# Line 240: closure_env_id = func_val.closure_id if closure_env else "" becomes:
    closure_env_id = func_val.closure_id if closure_env else NO_CLOSURE_ID

# Line 472: closure_id="" becomes (in the static method dispatch BoundFuncRef):
                closure_id=NO_CLOSURE_ID,
```

- [ ] **Step 3: Update `interpreter/handlers/memory.py`**

```python
# Line 85: BoundFuncRef(closure_id="") — remove the explicit kwarg, rely on default:
        return BoundFuncRef(
            func_ref=FuncRef(
                name=FuncName(constants.METHOD_MISSING), label=mm_labels[0]
            ),
        )
```

No import needed here — `BoundFuncRef` default is already `NO_CLOSURE_ID` from Task 2.

- [ ] **Step 4: Run full test suite**

Run: `poetry run python -m pytest tests/ -x -q`
Expected: All 13,126+ tests PASS

- [ ] **Step 5: Commit**

```bash
bd backup
git add interpreter/handlers/variables.py interpreter/handlers/calls.py interpreter/handlers/memory.py
git commit -m "Migrate closure construction sites to ClosureId

Update _handle_const, call dispatch, and _find_method_missing to use
ClosureId() and NO_CLOSURE_ID instead of bare strings."
```

---

### Task 5: Migrate Consumer Sites and Remaining Tests

**Files:**
- Modify: `interpreter/handlers/_common.py` (no change needed — reads `frame.closure_env_id` truthiness, works with ClosureId)
- Modify: `interpreter/vm/vm.py` (no change needed — reads `closure_env_id` from already-typed `StackFrame`)
- Modify: `interpreter/run.py:764-766`
- Modify: `tests/unit/test_method_missing.py`
- Modify: `tests/unit/test_load_field_indirect.py`
- Modify: `tests/unit/test_heap_field_method_call.py`

- [ ] **Step 1: Update `interpreter/run.py`**

Line 765 uses `v.closure_id` in a truthiness check followed by f-string formatting. Since `ClosureId.__bool__` and `ClosureId.__str__` are implemented, this works without change. Verify by reading the code:

```python
    if isinstance(v, BoundFuncRef):
        if v.closure_id:  # NO_CLOSURE_ID is falsy ✓
            return f"<function:{v.func_ref.name}@{v.func_ref.label}#{v.closure_id}>"  # __str__ ✓
        return f"<function:{v.func_ref.name}@{v.func_ref.label}>"
```

No change needed in `run.py`.

- [ ] **Step 2: Verify `_common.py` and `vm.py` need no changes**

`_common.py:70`: `if frame.closure_env_id` — works (ClosureId is truthy, NO_CLOSURE_ID is falsy).
`_common.py:71`: `vm.closures.get(frame.closure_env_id)` — works (ClosureId is hashable dict key).
`vm.py:266,289-290`: Same pattern — truthiness check + dict lookup. No changes needed.

- [ ] **Step 3: Update test files**

In `tests/unit/test_method_missing.py`:

```python
# Add import:
from interpreter.closure_id import NO_CLOSURE_ID

# Line 79: closure_id="" becomes:
        func_ref=FuncRef(name=FuncName(METHOD_MISSING), label=mm_label),
    )  # relies on default NO_CLOSURE_ID

# Line 251: closure_id="" becomes:
            closure_id=NO_CLOSURE_ID,
```

In `tests/unit/test_load_field_indirect.py`:

```python
# Add import:
from interpreter.closure_id import NO_CLOSURE_ID

# Line 140: mm_bound = BoundFuncRef(func_ref=mm_func_ref, closure_id="") becomes:
        mm_bound = BoundFuncRef(func_ref=mm_func_ref)
```

In `tests/unit/test_heap_field_method_call.py`:

```python
# Add import:
from interpreter.closure_id import NO_CLOSURE_ID

# Line 57: bound = BoundFuncRef(func_ref=func_ref, closure_id="") becomes:
    bound = BoundFuncRef(func_ref=func_ref)
```

- [ ] **Step 4: Run full test suite**

Run: `poetry run python -m pytest tests/ -x -q`
Expected: All 13,126+ tests PASS

- [ ] **Step 5: Grep for remaining bare-string closure comparisons**

```bash
# Check no bare string comparisons remain against closure_id fields:
poetry run python -m pytest tests/ -x -q  # already done above
rg 'closure_id\s*=\s*"' interpreter/ tests/
rg 'closure_env_id\s*=\s*"' interpreter/ tests/
```

Expected: Zero matches.

- [ ] **Step 6: Commit**

```bash
bd backup
git add interpreter/run.py tests/unit/test_method_missing.py tests/unit/test_load_field_indirect.py tests/unit/test_heap_field_method_call.py
git commit -m "Migrate remaining consumer sites and tests to ClosureId

All closure identifier references now use ClosureId/NO_CLOSURE_ID.
No bare-string closure comparisons remain."
```

---

### Task 6: Final Verification and Cleanup

- [ ] **Step 1: Run formatting**

```bash
poetry run python -m black .
```

- [ ] **Step 2: Run import linter**

```bash
poetry run lint-imports
```

- [ ] **Step 3: Run full test suite**

```bash
poetry run python -m pytest tests/ -q
```

Expected: All 13,126+ tests PASS, 0 failures.

- [ ] **Step 4: Grep for any remaining bare-string closure patterns**

```bash
rg 'closure_id\s*=\s*"' interpreter/ tests/
rg 'closure_env_id\s*=\s*"' interpreter/ tests/
rg "closures\[\"" interpreter/
rg "closures\.get\(\"" interpreter/
```

Expected: Zero matches for all four patterns.

- [ ] **Step 5: Close Beads issues**

```bash
bd close red-dragon-ynpw --reason "ClosureId domain type migration complete — frozen dataclass with NO_CLOSURE_ID sentinel, all 25 change sites migrated"
bd close red-dragon-tjv4 --reason "Duplicate of red-dragon-ynpw, closed together"
```

- [ ] **Step 6: Commit any formatting changes**

```bash
bd backup
git add -A
git commit -m "Format and verify ClosureId migration complete"
git push
```
