# ContinuationName Domain Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw `str` with `ContinuationName` domain type for COBOL continuation point names across instructions, VM state, handlers, and tests.

**Architecture:** New frozen dataclass `ContinuationName` in `interpreter/continuation_name.py` following the Address pattern. No `__eq__(str)` bridge. Migrate 5 type annotations, 3 COBOL emit sites, 2 handler sites, 2 factory converters, and ~17 test references.

**Tech Stack:** Python 3.13+ frozen dataclasses, Pydantic BaseModel (StateUpdate), pytest

**Spec:** `docs/superpowers/specs/2026-03-30-continuationname-domain-type-design.md`
**Issues:** red-dragon-ti2e, red-dragon-dy92

---

### Task 1: Create ContinuationName domain type

**Files:**
- Create: `interpreter/continuation_name.py`
- Test: `tests/unit/test_continuation_name.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for ContinuationName domain type."""

import pytest
from interpreter.continuation_name import (
    ContinuationName,
    NoContinuationName,
    NO_CONTINUATION_NAME,
)


class TestContinuationName:
    def test_str(self):
        assert str(ContinuationName("para_X_end")) == "para_X_end"

    def test_hash(self):
        a = ContinuationName("para_X_end")
        b = ContinuationName("para_X_end")
        assert hash(a) == hash(b)
        assert a == b

    def test_eq_different_values(self):
        assert ContinuationName("a") != ContinuationName("b")

    def test_eq_rejects_str(self):
        assert ContinuationName("x").__eq__("x") is NotImplemented

    def test_bool_truthy(self):
        assert bool(ContinuationName("para_X_end")) is True

    def test_bool_falsy_empty(self):
        assert bool(ContinuationName("")) is False

    def test_post_init_rejects_non_str(self):
        with pytest.raises(TypeError):
            ContinuationName(42)  # type: ignore[arg-type]

    def test_post_init_rejects_double_wrap(self):
        with pytest.raises(TypeError):
            ContinuationName(ContinuationName("x"))  # type: ignore[arg-type]

    def test_is_present(self):
        assert ContinuationName("x").is_present() is True

    def test_dict_key(self):
        d = {ContinuationName("a"): 1, ContinuationName("b"): 2}
        assert d[ContinuationName("a")] == 1


class TestNoContinuationName:
    def test_is_present_false(self):
        assert NO_CONTINUATION_NAME.is_present() is False

    def test_bool_false(self):
        assert bool(NO_CONTINUATION_NAME) is False

    def test_str_empty(self):
        assert str(NO_CONTINUATION_NAME) == ""

    def test_singleton_value(self):
        assert isinstance(NO_CONTINUATION_NAME, NoContinuationName)
        assert isinstance(NO_CONTINUATION_NAME, ContinuationName)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_continuation_name.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write implementation**

```python
"""ContinuationName — typed COBOL continuation point name."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ContinuationName:
    """A COBOL continuation point name (e.g., 'para_WORK_end', 'section_MAIN_end')."""

    value: str

    def __post_init__(self):
        if not isinstance(self.value, str):
            raise TypeError(
                f"ContinuationName.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def is_present(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ContinuationName):
            return self.value == other.value
        return NotImplemented

    def __bool__(self) -> bool:
        return bool(self.value)


@dataclass(frozen=True, eq=False)
class NoContinuationName(ContinuationName):
    """Null object: no continuation name."""

    value: str = ""

    def is_present(self) -> bool:
        return False


NO_CONTINUATION_NAME = NoContinuationName()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_continuation_name.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/continuation_name.py tests/unit/test_continuation_name.py
git commit -m "Add ContinuationName domain type (ti2e)"
```

---

### Task 2: Migrate instruction fields and factory converters

**Files:**
- Modify: `interpreter/instructions.py:1027-1071` (SetContinuation, ResumeContinuation classes)
- Modify: `interpreter/instructions.py:1419-1432` (_set_continuation, _resume_continuation converters)
- Test: `tests/unit/test_typed_instructions.py:475-492`
- Test: `tests/unit/test_typed_instruction_compat.py:57-60,84-85`
- Test: `tests/unit/test_map_registers_labels.py:149-152`

- [ ] **Step 1: Update instruction classes**

In `interpreter/instructions.py`, add import at top:

```python
from interpreter.continuation_name import ContinuationName, NO_CONTINUATION_NAME
```

Change `SetContinuation.name` (line 1030):

```python
# Before:
    name: str = ""
# After:
    name: ContinuationName = NO_CONTINUATION_NAME
```

Change `ResumeContinuation.name` (line 1054):

```python
# Before:
    name: str = ""
# After:
    name: ContinuationName = NO_CONTINUATION_NAME
```

- [ ] **Step 2: Update factory converters**

In `_set_continuation` (line 1419-1425):

```python
def _set_continuation(inst: IRInstruction) -> SetContinuation:
    ops = inst.operands
    return SetContinuation(
        name=ContinuationName(str(ops[0])) if len(ops) >= 1 else NO_CONTINUATION_NAME,
        target_label=ops[1] if len(ops) >= 2 else NO_LABEL,
        source_location=inst.source_location,
    )
```

In `_resume_continuation` (line 1428-1432):

```python
def _resume_continuation(inst: IRInstruction) -> ResumeContinuation:
    return ResumeContinuation(
        name=ContinuationName(str(inst.operands[0])) if inst.operands else NO_CONTINUATION_NAME,
        source_location=inst.source_location,
    )
```

- [ ] **Step 3: Update test_typed_instructions.py**

The `_assert_to_typed` helper round-trips through `IRInstruction` → typed → operands comparison. The `IRInstruction` factory calls `_to_typed` internally, which now wraps names in `ContinuationName`. The tests construct via `IRInstruction(opcode=..., operands=[...])` — the factory handles wrapping. These tests should pass without changes since `_assert_to_typed` checks structural round-trip, not string identity.

Run: `poetry run python -m pytest tests/unit/test_typed_instructions.py::TestSetContinuationToTyped tests/unit/test_typed_instructions.py::TestResumeContinuationToTyped -v`

If they fail, the issue is the operands comparison. Fix by verifying the typed fields directly rather than operand lists.

- [ ] **Step 4: Update test_typed_instruction_compat.py**

Change lines 57, 60, 84, 85 — add `ContinuationName` import and wrap `name=` values:

```python
from interpreter.continuation_name import ContinuationName

# Line 57:
SetContinuation(name=ContinuationName("c"), target_label=CodeLabel("L")),

# Line 60:
ResumeContinuation(name=ContinuationName("c")),

# Line 84:
SetContinuation(name=ContinuationName("c"), target_label=CodeLabel("L")),

# Line 85:
ResumeContinuation(name=ContinuationName("c")),
```

- [ ] **Step 5: Update test_map_registers_labels.py**

Change line 149 and update assertion on line 152:

```python
from interpreter.continuation_name import ContinuationName

# Line 149:
inst = SetContinuation(name=ContinuationName("__cont"), target_label=CodeLabel("L_resume"))

# Line 152 — name is ContinuationName, not str; map_labels doesn't touch it:
assert mapped.name == ContinuationName("__cont")
```

- [ ] **Step 6: Run affected tests**

Run: `poetry run python -m pytest tests/unit/test_typed_instructions.py tests/unit/test_typed_instruction_compat.py tests/unit/test_map_registers_labels.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add interpreter/instructions.py tests/unit/test_typed_instructions.py tests/unit/test_typed_instruction_compat.py tests/unit/test_map_registers_labels.py
git commit -m "Migrate SetContinuation/ResumeContinuation.name to ContinuationName"
```

---

### Task 3: Migrate VM state and handlers

**Files:**
- Modify: `interpreter/vm/vm_types.py:149,294-295` (VMState.continuations, StateUpdate fields)
- Modify: `interpreter/vm/vm.py:229-234` (apply_update)
- Modify: `interpreter/handlers/control_flow.py:136-173` (handlers)
- Test: `tests/unit/test_continuations.py`

- [ ] **Step 1: Update VMState.continuations**

In `interpreter/vm/vm_types.py`, add import:

```python
from interpreter.continuation_name import ContinuationName, NO_CONTINUATION_NAME
```

Change line 149:

```python
# Before:
    continuations: dict[str, CodeLabel] = field(default_factory=dict)
# After:
    continuations: dict[ContinuationName, CodeLabel] = field(default_factory=dict)
```

- [ ] **Step 2: Update StateUpdate fields**

Change line 294-295:

```python
# Before:
    continuation_writes: dict[str, CodeLabel] = {}
    continuation_clear: str = ""
# After:
    continuation_writes: dict[ContinuationName, CodeLabel] = {}
    continuation_clear: ContinuationName = NO_CONTINUATION_NAME
```

- [ ] **Step 3: Update VMState.to_dict() serialization**

Change line 235:

```python
# Before:
    if self.continuations:
        result["continuations"] = {k: str(v) for k, v in self.continuations.items()}
# After:
    if self.continuations:
        result["continuations"] = {str(k): str(v) for k, v in self.continuations.items()}
```

- [ ] **Step 4: Verify apply_update needs no changes**

In `interpreter/vm/vm.py` lines 228-234, the code is:

```python
for name, label in update.continuation_writes.items():
    vm.continuations[name] = label

if update.continuation_clear:
    vm.continuations.pop(update.continuation_clear, None)
```

`name` is now `ContinuationName` — hashable, so dict assignment works. `update.continuation_clear` is `ContinuationName` — `__bool__` returns `False` for `NO_CONTINUATION_NAME`, so the guard works. `pop` uses `__hash__`/`__eq__`. No code changes needed.

- [ ] **Step 5: Verify handlers need no code changes**

In `interpreter/handlers/control_flow.py`, `_handle_set_continuation` reads `t.name` (now `ContinuationName`) and passes it as `continuation_writes` key. `_handle_resume_continuation` reads `t.name` and does `vm.continuations.get(name)` and passes it as `continuation_clear`. Types flow through — no code changes needed, just verify the imports aren't broken.

- [ ] **Step 6: Update test_continuations.py**

Add import:

```python
from interpreter.continuation_name import ContinuationName
```

Update all `IRInstruction` construction sites to use `ContinuationName` in operands, and update all assertions that compare against bare strings.

**TestHandleSetContinuation.test_produces_correct_state_update** (line 26-36):

```python
def test_produces_correct_state_update(self):
    inst = IRInstruction(
        opcode=Opcode.SET_CONTINUATION,
        operands=["para_WORK_end", CodeLabel("perform_return_0")],
    )
    vm = _make_vm()
    result = _handle_set_continuation(inst, vm, _CTX)

    assert result.handled
    assert result.update.continuation_writes == {
        ContinuationName("para_WORK_end"): CodeLabel("perform_return_0")
    }
```

**TestHandleSetContinuation.test_last_writer_wins** (line 38-56):

```python
def test_last_writer_wins(self):
    vm = _make_vm()

    inst1 = IRInstruction(
        opcode=Opcode.SET_CONTINUATION,
        operands=["para_X_end", CodeLabel("return_A")],
    )
    result1 = _handle_set_continuation(inst1, vm, _CTX)
    apply_update(vm, result1.update)
    assert vm.continuations[ContinuationName("para_X_end")] == CodeLabel("return_A")

    inst2 = IRInstruction(
        opcode=Opcode.SET_CONTINUATION,
        operands=["para_X_end", CodeLabel("return_B")],
    )
    result2 = _handle_set_continuation(inst2, vm, _CTX)
    apply_update(vm, result2.update)
    assert vm.continuations[ContinuationName("para_X_end")] == CodeLabel("return_B")
```

**TestHandleResumeContinuation.test_branches_when_set** (line 60-72):

```python
def test_branches_when_set(self):
    vm = _make_vm()
    vm.continuations[ContinuationName("para_WORK_end")] = CodeLabel("perform_return_0")

    inst = IRInstruction(
        opcode=Opcode.RESUME_CONTINUATION,
        operands=["para_WORK_end"],
    )
    result = _handle_resume_continuation(inst, vm, _CTX)

    assert result.handled
    assert result.update.next_label == CodeLabel("perform_return_0")
    assert result.update.continuation_clear == ContinuationName("para_WORK_end")
```

**TestHandleResumeContinuation.test_falls_through_when_not_set** (line 74-85):

```python
def test_falls_through_when_not_set(self):
    vm = _make_vm()

    inst = IRInstruction(
        opcode=Opcode.RESUME_CONTINUATION,
        operands=["para_WORK_end"],
    )
    result = _handle_resume_continuation(inst, vm, _CTX)

    assert result.handled
    assert result.update.next_label is None
    assert result.update.continuation_clear == ContinuationName("para_WORK_end")
```

**TestApplyUpdateContinuations.test_writes_continuation** (line 88-96):

```python
def test_writes_continuation(self):
    vm = _make_vm()
    update = StateUpdate(
        continuation_writes={ContinuationName("para_X_end"): CodeLabel("return_label")},
        reasoning="test",
    )
    apply_update(vm, update)
    assert vm.continuations[ContinuationName("para_X_end")] == CodeLabel("return_label")
```

**TestApplyUpdateContinuations.test_clears_continuation** (line 98-104):

```python
def test_clears_continuation(self):
    vm = _make_vm()
    vm.continuations[ContinuationName("para_X_end")] = CodeLabel("return_label")

    update = StateUpdate(continuation_clear=ContinuationName("para_X_end"), reasoning="test")
    apply_update(vm, update)
    assert ContinuationName("para_X_end") not in vm.continuations
```

**TestApplyUpdateContinuations.test_clear_nonexistent_is_noop** (line 106-110):

```python
def test_clear_nonexistent_is_noop(self):
    vm = _make_vm()
    update = StateUpdate(continuation_clear=ContinuationName("para_NONEXIST_end"), reasoning="test")
    apply_update(vm, update)
    assert ContinuationName("para_NONEXIST_end") not in vm.continuations
```

**TestCFGBuilderResumeContinuation** tests (line 113-157): these construct `IRInstruction` with `operands=["para_A_end"]` — the factory wraps it in `ContinuationName`. These tests don't assert on the name value, only on CFG structure. No changes needed.

- [ ] **Step 7: Run all continuation tests**

Run: `poetry run python -m pytest tests/unit/test_continuations.py -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add interpreter/vm/vm_types.py interpreter/vm/vm.py tests/unit/test_continuations.py
git commit -m "Migrate VMState.continuations and StateUpdate to ContinuationName keys"
```

---

### Task 4: Migrate COBOL frontend emit sites

**Files:**
- Modify: `interpreter/cobol/lower_perform.py:90`
- Modify: `interpreter/cobol/lower_procedure.py:48,60`

- [ ] **Step 1: Update lower_perform.py**

Add import:

```python
from interpreter.continuation_name import ContinuationName
```

Change line 90:

```python
# Before:
    ctx.emit_inst(
        SetContinuation(name=str(continuation_key), target_label=return_label)
    )
# After:
    ctx.emit_inst(
        SetContinuation(name=ContinuationName(str(continuation_key)), target_label=return_label)
    )
```

- [ ] **Step 2: Update lower_procedure.py**

Add import:

```python
from interpreter.continuation_name import ContinuationName
```

Change line 48:

```python
# Before:
    ctx.emit_inst(ResumeContinuation(name=f"section_{section.name}_end"))
# After:
    ctx.emit_inst(ResumeContinuation(name=ContinuationName(f"section_{section.name}_end")))
```

Change line 60:

```python
# Before:
    ctx.emit_inst(ResumeContinuation(name=f"para_{para.name}_end"))
# After:
    ctx.emit_inst(ResumeContinuation(name=ContinuationName(f"para_{para.name}_end")))
```

- [ ] **Step 3: Run COBOL tests**

Run: `poetry run python -m pytest tests/unit/test_cobol*.py tests/integration/test_cobol*.py -v`
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add interpreter/cobol/lower_perform.py interpreter/cobol/lower_procedure.py
git commit -m "Wrap COBOL frontend continuation names in ContinuationName"
```

---

### Task 5: Full verification and cleanup

**Files:**
- None (verification only)

- [ ] **Step 1: Run full verification gate**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/ -x -q
```

Expected: all pass, 13,100+ tests, 0 failures.

- [ ] **Step 2: Grep for any remaining bare string continuation names**

```bash
grep -rn 'continuation_writes.*{.*"' interpreter/ tests/
grep -rn 'continuation_clear.*=.*"' interpreter/ tests/
grep -rn 'vm\.continuations\[.*"' interpreter/ tests/
```

Expected: no matches (all should use `ContinuationName(...)` now).

- [ ] **Step 3: Close issues**

```bash
bd close red-dragon-ti2e --reason "ContinuationName domain type implemented — 5 type annotations, 3 emit sites, 2 factory converters, ~17 test references migrated"
bd close red-dragon-dy92 --reason "Duplicate of ti2e — closed as part of ContinuationName migration"
bd backup
```

- [ ] **Step 4: Final commit**

```bash
git add .beads/
git commit -m "bd: close ti2e + dy92 (ContinuationName migration complete)"
git push
```
