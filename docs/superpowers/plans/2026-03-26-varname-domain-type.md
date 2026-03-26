# VarName Domain Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `str` variable name fields on IR instructions and `dict[str, ...]` scope chain keys with a `VarName` domain type that carries structured name + optional scope ID for mangled block-scoped variables.

**Architecture:** Bridge-first, same pattern as Register migration. Define `VarName(base: str, scope_id: int | None)` with `__eq__(str)` bridge. Wrap all frontend and VM sites. Change field types. Cascade through scope chain (`local_vars: dict[VarName, TypedValue]`). Remove bridge.

**Tech Stack:** Python 3.13+, pytest, Poetry

**Issue:** red-dragon-w667

---

## Task 1: Define VarName and NoVarName types

**Files:**
- Create: `interpreter/var_name.py`
- Test: `tests/unit/test_var_name.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for VarName domain type."""
from interpreter.var_name import VarName, NO_VAR_NAME


class TestVarName:
    def test_simple_name(self):
        v = VarName(base="x")
        assert str(v) == "x"
        assert v.base == "x"
        assert v.scope_id is None

    def test_mangled_name(self):
        v = VarName(base="x", scope_id=1)
        assert str(v) == "x$1"
        assert v.base == "x"
        assert v.scope_id == 1

    def test_is_mangled(self):
        assert not VarName(base="x").is_mangled
        assert VarName(base="x", scope_id=1).is_mangled

    def test_is_self(self):
        assert VarName(base="self").is_self
        assert VarName(base="this").is_self
        assert VarName(base="$this").is_self  # PHP
        assert not VarName(base="x").is_self

    def test_equality_between_varnames(self):
        assert VarName(base="x") == VarName(base="x")
        assert VarName(base="x", scope_id=1) == VarName(base="x", scope_id=1)
        assert VarName(base="x") != VarName(base="y")
        assert VarName(base="x") != VarName(base="x", scope_id=1)

    def test_equality_with_string_bridge(self):
        """Bridge period: VarName compares equal to its str representation."""
        assert VarName(base="x") == "x"
        assert VarName(base="x", scope_id=1) == "x$1"

    def test_hash_consistent_with_str(self):
        """Bridge period: hash matches str hash for dict key compat."""
        assert hash(VarName(base="x")) == hash("x")
        assert hash(VarName(base="x", scope_id=1)) == hash("x$1")

    def test_no_var_name(self):
        assert str(NO_VAR_NAME) == ""
        assert not NO_VAR_NAME.is_present()
        assert VarName(base="x").is_present()

    def test_from_str_simple(self):
        v = VarName.from_str("x")
        assert v.base == "x"
        assert v.scope_id is None

    def test_from_str_mangled(self):
        v = VarName.from_str("x$1")
        assert v.base == "x"
        assert v.scope_id == 1

    def test_from_str_no_mangle_if_no_dollar(self):
        v = VarName.from_str("self")
        assert v.base == "self"
        assert v.scope_id is None
```

- [ ] **Step 2: Implement VarName**

Create `interpreter/var_name.py`:

```python
"""VarName — typed variable name with optional block-scope mangling."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class VarName:
    """A variable name, optionally mangled with a block-scope ID."""

    base: str
    scope_id: int | None = None

    def is_present(self) -> bool:
        return True

    @property
    def is_mangled(self) -> bool:
        return self.scope_id is not None

    @property
    def is_self(self) -> bool:
        return self.base in ("self", "this", "$this")

    def __str__(self) -> str:
        if self.scope_id is not None:
            return f"{self.base}${self.scope_id}"
        return self.base

    def __hash__(self) -> int:
        return hash(str(self))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, VarName):
            return self.base == other.base and self.scope_id == other.scope_id
        if isinstance(other, str):
            return str(self) == other
        return NotImplemented

    @classmethod
    def from_str(cls, s: str) -> VarName:
        """Parse 'x$1' into VarName(base='x', scope_id=1)."""
        match = re.match(r"^(.+)\$(\d+)$", s)
        if match:
            return cls(base=match.group(1), scope_id=int(match.group(2)))
        return cls(base=s)


@dataclass(frozen=True, eq=False)
class NoVarName(VarName):
    """Null object: no variable name."""
    base: str = ""

    def is_present(self) -> bool:
        return False


NO_VAR_NAME = NoVarName()
```

- [ ] **Step 3: Run tests, verify, commit**

---

## Task 2: Wrap frontend emit sites with VarName (bridge)

**Files:**
- Modify: All frontend files that construct `DeclVar`, `StoreVar`, `LoadVar`, `AddressOf` with name arguments
- The field stays `str`. `VarName.__eq__(str)` bridge ensures compatibility.

Find sites: `grep -rn 'DeclVar\|StoreVar\|LoadVar\|AddressOf' interpreter/frontends/ interpreter/cobol/ --include='*.py' | grep 'name='`

Pattern:
```python
# Before
DeclVar(name=var_name, ...)

# After
DeclVar(name=VarName.from_str(var_name), ...)
```

Or for sites where the name is freshly constructed (not from AST text):
```python
DeclVar(name=VarName(base=var_name), ...)
```

- [ ] **Step 1: Survey all DeclVar/StoreVar/LoadVar/AddressOf construction sites**
- [ ] **Step 2: Wrap with VarName.from_str() or VarName(base=...)**
- [ ] **Step 3: Run full test suite, verify, commit**

---

## Task 3: Change field types on instructions

**Files:**
- Modify: `interpreter/instructions.py` — `LoadVar.name: VarName`, `DeclVar.name: VarName`, `StoreVar.name: VarName`, `AddressOf.var_name: VarName`
- Modify: `interpreter/instructions.py` — `operands` properties: `str()` VarName values
- Modify: `interpreter/instructions.py` — `_to_typed` converters: `VarName.from_str()`

- [ ] **Step 1: Change field types, update operands, update converters**
- [ ] **Step 2: Run full test suite, verify, commit**

---

## Task 4: Cascade VarName through VM scope chain

**Files:**
- Modify: `interpreter/vm/vm_types.py` — `StackFrame.local_vars: dict[VarName, TypedValue]`
- Modify: `interpreter/vm/vm_types.py` — `captured_var_names: frozenset[VarName]`
- Modify: `interpreter/vm/vm_types.py` — `var_heap_aliases: dict[VarName, Pointer]`
- Modify: `interpreter/handlers/variables.py` — scope chain lookup uses VarName
- Modify: `interpreter/handlers/calls.py` — constructor var_writes uses VarName
- Modify: `interpreter/handlers/_common.py` — if it touches local_vars
- Modify: `interpreter/handlers/objects.py` — ClassRef dereference uses str(type_hint) for lookup
- Modify: `interpreter/vm/vm.py` — closure capture writes to `local_vars` and `var_heap_aliases`
- Modify: `interpreter/types/typed_value.py` — `unwrap_locals` signature
- Modify: All other files that read/write `frame.local_vars`

Note: `ClosureEnvironment.bindings: dict[str, TypedValue]` in `vm_types.py` also uses variable names as keys. This should be tracked as a follow-up (file issue during execution if not addressed here).

This is the largest task — ~26 usages across 11+ files. Bridge period: `VarName.__eq__(str)` and `hash(VarName) == hash(str)` keep existing `dict[str, ...]` lookups working during migration.

- [ ] **Step 1: Change StackFrame.local_vars key type**
- [ ] **Step 2: Update handler files to construct VarName for dict keys**
- [ ] **Step 3: Run full test suite (bridge handles compat)**
- [ ] **Step 4: Commit**

---

## Task 5: Remove VarName.__eq__(str) bridge

**Files:**
- Modify: `interpreter/var_name.py` — remove str comparison branch
- Modify: All sites that compare VarName to str or use str as dict key

Same pattern as the Register.__eq__(str) removal — expect ~50-100 test assertion fixes.

- [ ] **Step 1: Remove bridge**
- [ ] **Step 2: Fix all broken comparisons and dict lookups**
- [ ] **Step 3: Run full test suite, verify, commit, close issue**
