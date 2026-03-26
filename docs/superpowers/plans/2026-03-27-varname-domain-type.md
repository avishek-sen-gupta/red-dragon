# VarName Domain Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `str` variable name fields on IR instructions and `dict[str, ...]` VM scope chain keys with a `VarName` domain type, preventing accidental interchange of variable names with field names, function names, or arbitrary strings.

**Architecture:** Simple wrapper `VarName(value: str)` following the CodeLabel precedent. Bridge-first: `__eq__(str)` and hash compat keep existing lookups working during migration. Frontend wrapping first (jdx0), then field types + VM cascade + bridge removal (90z9).

**Tech Stack:** Python 3.13+, pytest, Poetry

**Spec:** `docs/superpowers/specs/2026-03-27-varname-domain-type-design.md`
**Issues:** red-dragon-b9cd (type), jdx0 (frontends), 90z9 (VM cascade)

---

## Task 1: Define VarName type and tests (b9cd)

**Files:**
- Create: `interpreter/var_name.py`
- Create: `tests/unit/test_var_name.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for VarName domain type."""

import pytest

from interpreter.var_name import VarName, NoVarName, NO_VAR_NAME


class TestVarName:
    def test_str(self):
        assert str(VarName("x")) == "x"

    def test_value(self):
        assert VarName("x").value == "x"

    def test_is_present(self):
        assert VarName("x").is_present()

    def test_is_self_python(self):
        assert VarName("self").is_self

    def test_is_self_java(self):
        assert VarName("this").is_self

    def test_is_self_php(self):
        assert VarName("$this").is_self

    def test_is_self_false(self):
        assert not VarName("x").is_self

    def test_equality(self):
        assert VarName("x") == VarName("x")
        assert VarName("x") != VarName("y")

    def test_equality_with_string_bridge(self):
        assert VarName("x") == "x"
        assert VarName("x") != "y"

    def test_hash_consistent_with_str(self):
        assert hash(VarName("x")) == hash("x")

    def test_dict_lookup_with_str_key(self):
        d = {VarName("x"): 42}
        assert d["x"] == 42

    def test_contains(self):
        assert "__" in VarName("__cobol_x")
        assert "z" not in VarName("abc")

    def test_startswith(self):
        assert VarName("__cobol_x").startswith("__cobol_")
        assert not VarName("x").startswith("__cobol_")

    def test_post_init_rejects_double_wrap(self):
        with pytest.raises(TypeError, match="must be str"):
            VarName(VarName("x"))


class TestNoVarName:
    def test_str(self):
        assert str(NO_VAR_NAME) == ""

    def test_not_present(self):
        assert not NO_VAR_NAME.is_present()

    def test_is_instance(self):
        assert isinstance(NO_VAR_NAME, VarName)
```

- [ ] **Step 2: Implement VarName**

Create `interpreter/var_name.py`:

```python
"""VarName — typed variable name with domain semantics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VarName:
    """A variable name, wrapping a string with domain semantics."""

    value: str

    def __post_init__(self):
        if not isinstance(self.value, str):
            raise TypeError(
                f"VarName.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def is_present(self) -> bool:
        return True

    @property
    def is_self(self) -> bool:
        # "self" — Python, Ruby, Lua, Scala
        # "this" — Java, C#, C++, Kotlin, JS/TS
        # "$this" — PHP
        return self.value in ("self", "this", "$this")

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, VarName):
            return self.value == other.value
        if isinstance(other, str):  # bridge — removed in 90z9
            return self.value == other
        return NotImplemented

    def __contains__(self, item: str) -> bool:
        return item in self.value

    def startswith(self, prefix: str) -> bool:
        return self.value.startswith(prefix)


@dataclass(frozen=True, eq=False)
class NoVarName(VarName):
    """Null object: no variable name."""

    value: str = ""

    def is_present(self) -> bool:
        return False


NO_VAR_NAME = NoVarName()
```

- [ ] **Step 3: Run tests, verify**

```bash
poetry run python -m pytest tests/unit/test_var_name.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Format, lint, commit**

```bash
poetry run python -m black .
poetry run lint-imports
bd backup
git add interpreter/var_name.py tests/unit/test_var_name.py
git commit -m "Add VarName domain type with bridge equality"
```

---

## Task 2: Wrap frontend construction sites (jdx0)

**Files:**
- Modify: ~50 frontend files + `interpreter/frontends/_base.py` + `interpreter/frontends/common/` (6 files) + `interpreter/cobol/` (3 files)

~430 DeclVar/StoreVar/LoadVar/AddressOf construction sites. Dispatch 8-10 parallel subagents by language group. Each subagent:

1. Reads each file
2. Adds `from interpreter.var_name import VarName` before `from interpreter.instructions import`
3. Wraps every `name=X` argument inside DeclVar/StoreVar/LoadVar/AddressOf constructors with `VarName(X)`
4. Wraps every `var_name=X` argument inside AddressOf constructors with `VarName(X)`
5. Does NOT wrap `name=` arguments on these OTHER instruction types: `CallFunction`, `CallMethod`, `CallCtorFunction`, `CallUnknown`, `LoadField`, `StoreField`, `StoreFieldIndirect`, `NewObject`, `NewArray`, `SetContinuation`, `ResumeContinuation`
6. Uses the Edit tool, not bulk scripts

**Subagent groups:**

| Agent | Files | Est. sites |
|-------|-------|------------|
| 1 | `_base.py`, `common/` (6 files) | 40 |
| 2 | `python/`, `ruby/` | 42 |
| 3 | `javascript/`, `typescript/` | 31+ |
| 4 | `java/`, `kotlin/` | 74 |
| 5 | `c/`, `cpp/`, `csharp/` | 61 |
| 6 | `go/`, `rust/` | 66 |
| 7 | `lua/`, `php/`, `scala/`, `pascal/` | 107 |
| 8 | COBOL (`lower_search.py`, `lower_perform.py`, `lower_call.py`) | 9 |

- [ ] **Step 1: Dispatch 8 parallel subagents**

Each subagent wraps all `name=` / `var_name=` arguments on DeclVar/StoreVar/LoadVar/AddressOf with `VarName()`.

- [ ] **Step 2: Verify zero unwrapped sites remain**

```bash
# Check for unwrapped name= on DeclVar/StoreVar/LoadVar (multi-line aware)
poetry run python -c "
import pathlib
missed = []
for p in pathlib.Path('interpreter').rglob('*.py'):
    if '__pycache__' in str(p): continue
    text = p.read_text()
    if 'DeclVar(' not in text and 'StoreVar(' not in text and 'LoadVar(' not in text and 'AddressOf(' not in text: continue
    lines = text.splitlines()
    in_target = False
    for i, line in enumerate(lines):
        s = line.strip()
        if any(t in s for t in ['DeclVar(', 'StoreVar(', 'LoadVar(', 'AddressOf(']):
            in_target = True
        if in_target and ('name=' in s or 'var_name=' in s):
            if 'VarName' not in s and 'NO_VAR_NAME' not in s:
                missed.append(f'{p}:{i+1}: {s}')
            in_target = False
        if s.startswith(')'):
            in_target = False
for m in missed: print(m)
if not missed: print('All sites wrapped!')
"
```

- [ ] **Step 3: Run full test suite**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
```

Expected: 13,000+ passed (bridge makes wrapping a no-op).

- [ ] **Step 4: Format, lint, commit**

```bash
poetry run python -m black .
poetry run lint-imports
bd backup
git add -A
git commit -m "Wrap all frontend/COBOL variable name sites with VarName"
```

---

## Task 3: Change instruction field types (90z9 part 1)

**Files:**
- Modify: `interpreter/instructions.py` — field types (lines 208, 227, 248, 604), operands properties (lines 218-220, 239-241, 260-262, 614-616), converters (lines 977-982, 985-991, 994-1000, 1165-1170)
- Modify: `tests/unit/test_typed_instruction_compat.py` — update test constructions to use VarName

- [ ] **Step 1: Add VarName import to instructions.py**

```python
from interpreter.var_name import VarName, NO_VAR_NAME
```

- [ ] **Step 2: Change 4 field type annotations**

```python
# LoadVar (line 208)
name: VarName = NO_VAR_NAME    # was: name: str = ""

# DeclVar (line 227)
name: VarName = NO_VAR_NAME    # was: name: str = ""

# StoreVar (line 248)
name: VarName = NO_VAR_NAME    # was: name: str = ""

# AddressOf (line 604)
var_name: VarName = NO_VAR_NAME  # was: var_name: str = ""
```

- [ ] **Step 3: Update operands properties to str()**

```python
# LoadVar.operands
return [str(self.name)]

# DeclVar.operands
return [str(self.name), str(self.value_reg)]

# StoreVar.operands
return [str(self.name), str(self.value_reg)]

# AddressOf.operands
return [str(self.var_name)]
```

- [ ] **Step 4: Update _to_typed converters**

```python
# _load_var (line 977-982)
name=VarName(str(inst.operands[0])) if inst.operands else NO_VAR_NAME,

# _decl_var (line 985-991)
name=VarName(str(inst.operands[0])) if len(ops) >= 1 else NO_VAR_NAME,

# _store_var (line 994-1000)
name=VarName(str(inst.operands[0])) if len(ops) >= 1 else NO_VAR_NAME,

# _address_of (line 1165-1170)
var_name=VarName(str(inst.operands[0])) if inst.operands else NO_VAR_NAME,
```

- [ ] **Step 5: Update tests that construct these instructions with raw strings**

Known files that construct LoadVar/DeclVar/StoreVar/AddressOf with raw string names:
- `tests/unit/test_typed_instruction_compat.py`
- `tests/unit/test_emit_inst.py`
- `tests/unit/test_map_registers_labels.py`

Also grep `tests/` for any others: `LoadVar(name=`, `DeclVar(name=`, `StoreVar(name=`, `AddressOf(var_name=` with string arguments, and wrap with `VarName()`.

- [ ] **Step 6: Run full test suite, format, commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/ -x -q --tb=short
bd backup
git add -A
git commit -m "Change LoadVar/DeclVar/StoreVar/AddressOf field types to VarName"
```

---

## Task 4: Cascade VarName through VM scope chain (90z9 part 2)

**Files:**
- Modify: `interpreter/vm/vm_types.py` — StackFrame fields (lines 82, 89, 90), StateUpdate.var_writes (~line 214), StackFramePush.captured_var_names (~line 205)
- Modify: `interpreter/handlers/variables.py` (lines 56, 62, 65, 95, 104-105, 153)
- Modify: `interpreter/handlers/_common.py` — `_write_var_to_frame` (lines 54, 58, 62, 63). Note: line 66 writes to `ClosureEnvironment.bindings: dict[str, TypedValue]` which remains str-keyed until ss6g — bridge keeps this working.
- Modify: `interpreter/handlers/calls.py` (lines 165, 168, 171, 174, 303-304, 399-400, 582, 585, 588)
- Modify: `interpreter/handlers/memory.py` (lines 112, 126-127, 171)
- Modify: `interpreter/handlers/objects.py` — wrap `hint_name` in `VarName()` for `local_vars` lookup (~lines 34-35)
- Modify: `interpreter/vm/vm.py` (lines 265, 276, 278, 280-284)
- Modify: `interpreter/vm/field_fallback.py` (line 50) — wrap `constants.PARAM_THIS` in `VarName()`
- Modify: `interpreter/llm/backend.py` (line 102) — serialization boundary: use `str(k)` for JSON keys

The bridge `__eq__(str)` + hash compat means existing code still works during migration. But all write sites must be updated to construct VarName keys so that bridge removal (Task 5) succeeds cleanly.

- [ ] **Step 1: Change vm_types.py field types**

```python
# StackFrame fields
local_vars: dict[VarName, TypedValue] = field(default_factory=dict)
captured_var_names: frozenset[VarName] = field(default_factory=frozenset)
var_heap_aliases: dict[VarName, Pointer] = field(default_factory=dict)

# StateUpdate.var_writes
var_writes: dict[VarName, Any]  # was dict[str, Any]

# StackFramePush.captured_var_names
captured_var_names: list[VarName]  # was list[str]
```

- [ ] **Step 2: Update handler writes to use VarName keys**

For each handler that writes to `local_vars`, `var_heap_aliases`, or constructs `new_vars` dicts:

- `inst.name` is already `VarName` after Task 3 — these are no-ops
- **Bare string literals** need wrapping: grep for `new_vars["` and `new_vars[constants.` in handler files. Key sites:
  - `calls.py` line 588: `new_vars["arguments"]` → `new_vars[VarName("arguments")]`
  - Any other constant string keys in `new_vars` dicts
- `_write_var_to_frame` signature: change `name: str` → `name: VarName`
- `objects.py` lines 34-35: `hint_name in frame.local_vars` → `VarName(hint_name) in frame.local_vars`
- `field_fallback.py` line 50: `f.local_vars.get(constants.PARAM_THIS)` → `f.local_vars.get(VarName(constants.PARAM_THIS))`
- `calls.py` lines 303-304, 399-400: these look up `base_name`/`func_name` (function names, not variable names) in `local_vars` — wrap with `VarName()` since function aliases are stored as variable entries

- [ ] **Step 3: Update backend.py serialization boundary**

```python
# backend.py line 102: serialization boundary — keys must be str for JSON
{str(k): _serialize_value(v) for k, v in frame.local_vars.items()}
```

- [ ] **Step 4: Run full test suite (bridge handles compat)**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
```

Expected: all pass — bridge keeps str lookups working.

- [ ] **Step 5: Format, lint, commit**

```bash
poetry run python -m black .
poetry run lint-imports
bd backup
git add -A
git commit -m "Cascade VarName through VM scope chain (local_vars, captured_var_names, var_heap_aliases)"
```

---

## Task 5: Remove bridge and update test assertions (90z9 part 3)

**Files:**
- Modify: `interpreter/var_name.py` — remove `__eq__(str)` branch
- Modify: ~many test files — update `local_vars["x"]` to `local_vars[VarName("x")]`

- [ ] **Step 1: Remove the str bridge from VarName.__eq__**

```python
def __eq__(self, other: object) -> bool:
    if isinstance(other, VarName):
        return self.value == other.value
    return NotImplemented
```

- [ ] **Step 2: Run tests to find all breakages**

```bash
poetry run python -m pytest tests/ -x -q --tb=line 2>&1 | head -30
```

This will show all sites that compare VarName to str or use str as dict key.

- [ ] **Step 3: Fix test assertions**

Pattern: replace `local_vars["x"]` with `local_vars[VarName("x")]` across ~400 test assertions. Use parallel subagents grouped by test directory.

- [ ] **Step 4: Fix any remaining handler/VM string comparisons**

Grep for `== "` or `!= "` or `.get("` patterns in handler and VM files that now need VarName.

- [ ] **Step 5: Run full test suite, format, lint, commit**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/ -x -q --tb=short
bd backup
git add -A
git commit -m "Remove VarName.__eq__(str) bridge, update all test assertions"
```

- [ ] **Step 6: Close issues**

```bash
bd close b9cd --reason "VarName type defined and tested"
bd close jdx0 --reason "All frontend/COBOL construction sites wrapped"
bd close 90z9 --reason "Field types changed, VM cascaded, bridge removed, tests updated"
```
