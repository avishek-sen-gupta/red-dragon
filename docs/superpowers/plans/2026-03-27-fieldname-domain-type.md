# FieldName Domain Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `str` field name fields on IR instructions and `dict[str, ...]` heap object keys with a tagged `FieldName(value, kind)` domain type, with no str bridge.

**Architecture:** Define FieldName with FieldKind enum (PROPERTY/INDEX/SPECIAL). Kind is part of identity. No bridge — fix all construction AND consumption sites in one pass. Default kind is PROPERTY. Wrap at origin, unwrap at serialization/symbol-table boundaries only.

**Tech Stack:** Python 3.13+, pytest, Poetry

**Spec:** `docs/superpowers/specs/2026-03-27-fieldname-domain-type-design.md`
**Issue:** red-dragon-j0h1

---

## Task 1: Define FieldName type and tests

**Files:**
- Create: `interpreter/field_name.py`
- Create: `tests/unit/test_field_name.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for FieldName domain type."""
import pytest
from interpreter.field_name import FieldName, FieldKind, NoFieldName, NO_FIELD_NAME


class TestFieldName:
    def test_str(self):
        assert str(FieldName("x")) == "x"

    def test_value_and_kind(self):
        f = FieldName("x")
        assert f.value == "x"
        assert f.kind == FieldKind.PROPERTY

    def test_explicit_kind(self):
        f = FieldName("0", FieldKind.INDEX)
        assert f.kind == FieldKind.INDEX
        assert str(f) == "0"

    def test_is_present(self):
        assert FieldName("x").is_present()

    def test_equality_same_kind(self):
        assert FieldName("x") == FieldName("x")
        assert FieldName("x") != FieldName("y")

    def test_equality_different_kind(self):
        assert FieldName("0", FieldKind.INDEX) != FieldName("0", FieldKind.PROPERTY)

    def test_not_equal_to_string(self):
        assert FieldName("x") != "x"

    def test_hash_includes_kind(self):
        assert hash(FieldName("0", FieldKind.INDEX)) != hash(FieldName("0", FieldKind.PROPERTY))

    def test_hash_consistent(self):
        assert hash(FieldName("x")) == hash(FieldName("x"))

    def test_dict_lookup(self):
        d = {FieldName("x"): 42, FieldName("0", FieldKind.INDEX): 99}
        assert d[FieldName("x")] == 42
        assert d[FieldName("0", FieldKind.INDEX)] == 99

    def test_lt(self):
        assert FieldName("a") < FieldName("b")

    def test_contains(self):
        assert "__" in FieldName("__method_missing__")

    def test_startswith(self):
        assert FieldName("__x").startswith("__")

    def test_post_init_rejects_double_wrap(self):
        with pytest.raises(TypeError, match="must be str"):
            FieldName(FieldName("x"))


class TestNoFieldName:
    def test_str(self):
        assert str(NO_FIELD_NAME) == ""

    def test_not_present(self):
        assert not NO_FIELD_NAME.is_present()

    def test_is_instance(self):
        assert isinstance(NO_FIELD_NAME, FieldName)
```

- [ ] **Step 2: Implement FieldName**

```python
"""FieldName — typed field/property name with access-pattern tag."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class FieldKind(Enum):
    PROPERTY = "property"
    INDEX = "index"
    SPECIAL = "special"


@dataclass(frozen=True)
class FieldName:
    value: str
    kind: FieldKind = FieldKind.PROPERTY

    def __post_init__(self):
        if not isinstance(self.value, str):
            raise TypeError(
                f"FieldName.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def is_present(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash((self.value, self.kind))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FieldName):
            return self.value == other.value and self.kind == other.kind
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, FieldName):
            return (self.value, self.kind.value) < (other.value, other.kind.value)
        return NotImplemented

    def __contains__(self, item: str) -> bool:
        return item in self.value

    def startswith(self, prefix: str) -> bool:
        return self.value.startswith(prefix)


@dataclass(frozen=True, eq=False)
class NoFieldName(FieldName):
    value: str = ""
    kind: FieldKind = FieldKind.PROPERTY

    def is_present(self) -> bool:
        return False


NO_FIELD_NAME = NoFieldName()
```

- [ ] **Step 3: Run tests, format, lint, commit**

```bash
poetry run python -m pytest tests/unit/test_field_name.py -v
poetry run python -m black .
poetry run lint-imports
bd backup
git add interpreter/field_name.py tests/unit/test_field_name.py
git commit -m "Add FieldName domain type with FieldKind tag

FieldName(value, kind) with kind as part of identity. FieldKind enum:
PROPERTY, INDEX, SPECIAL. No str bridge. __post_init__ double-wrap guard.

Issue: red-dragon-j0h1

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Change instruction fields, HeapObject, HeapWrite, and converters

**Files:**
- Modify: `interpreter/instructions.py` — LoadField (line 447), StoreField (line 467), operands, converters (lines 1094-1111)
- Modify: `interpreter/vm/vm_types.py` — HeapObject.fields (line 51), HeapWrite.field (line 175), HeapObject.to_dict serialization

- [ ] **Step 1: Add imports and change instruction field types**

In `interpreter/instructions.py`:
```python
from interpreter.field_name import FieldName, FieldKind, NO_FIELD_NAME
```

Change:
```python
# LoadField (line 447)
field_name: FieldName = NO_FIELD_NAME   # was str = ""

# StoreField (line 467)
field_name: FieldName = NO_FIELD_NAME   # was str = ""
```

Update operands: `return [str(self.obj_reg), str(self.field_name)]`

Update converters:
```python
# _load_field (line 1099)
field_name=FieldName(str(ops[1])) if len(ops) >= 2 else NO_FIELD_NAME,

# _store_field (line 1108)
field_name=FieldName(str(ops[1])) if len(ops) >= 2 else NO_FIELD_NAME,
```

- [ ] **Step 2: Change HeapObject.fields and HeapWrite.field**

In `interpreter/vm/vm_types.py`:
```python
from interpreter.field_name import FieldName, FieldKind

# HeapObject (line 51)
fields: dict[FieldName, TypedValue] = field(default_factory=dict)

# HeapWrite (line 175)
field: FieldName    # was str
```

Update `HeapObject.to_dict` serialization to use `str(k)`:
```python
"fields": {str(k): _serialize_value(v) for k, v in self.fields.items()},
```

- [ ] **Step 3: Run tests (expect many failures — no bridge), commit type changes**

```bash
poetry run python -m pytest tests/ -q --tb=no 2>&1 | tail -3
# Note failure count for tracking
bd backup && git add -A
git commit -m "Change FieldName/HeapObject/HeapWrite types (failures expected until consumption sites fixed)"
```

---

## Task 3: Fix all handler and VM consumption sites

**Files:**
- Modify: `interpreter/handlers/memory.py` — lines 50-51, 89-91, 248-249, 334-340, 392-393, 416, 451
- Modify: `interpreter/handlers/_common.py` — line 27
- Modify: `interpreter/handlers/variables.py` — line 165
- Modify: `interpreter/vm/vm.py` — lines 249-252, 283
- Modify: `interpreter/vm/builtins.py` — lines 129, 137-141, 146, 198, 203, 224-226
- Modify: `interpreter/vm/field_fallback.py` — lines 69, 75
- Modify: `interpreter/vm/unresolved_call.py` — line 187
- Modify: `mcp_server/formatting.py` — line 62

- [ ] **Step 1: Fix memory.py handler sites**

```python
# _find_method_missing (line 50): constants as SPECIAL
FieldName(constants.METHOD_MISSING, FieldKind.SPECIAL) in heap_obj.fields
heap_obj.fields[FieldName(constants.METHOD_MISSING, FieldKind.SPECIAL)]

# Boxed field (line 89, 91):
FieldName(constants.BOXED_FIELD, FieldKind.SPECIAL) not in heap_obj.fields
heap_obj.fields[FieldName(constants.BOXED_FIELD, FieldKind.SPECIAL)]

# _handle_load_field (line 392-393): field_name is already FieldName from inst
# No change needed — field_name comes from inst.field_name

# _handle_load_field cached symbolic (line 416):
heap_obj.fields[field_name] = typed(sym, UNKNOWN)  # field_name already FieldName

# _handle_load_field_indirect (line 248-249): wrap runtime str value
field_key = FieldName(str(field_name))
if field_key in heap_obj.fields:
    tv = heap_obj.fields[field_key]

# _handle_store_field (line 337): field_name already FieldName from inst

# _handle_store_index (line 451): wrap index as INDEX
field=FieldName(str(idx_val), FieldKind.INDEX)

# _handle_load_index: wrap index as INDEX for lookup
```

- [ ] **Step 2: Fix _common.py spread arguments (line 27)**

```python
args.extend(
    fields[FieldName(str(i), FieldKind.INDEX)]
    for i in range(len(fields))
    if FieldName(str(i), FieldKind.INDEX) in fields
)
```

- [ ] **Step 3: Fix variables.py field fallback HeapWrite (line 165)**

```python
heap_writes=[HeapWrite(obj_addr=this_addr, field=FieldName(str(name)), value=tv)],
```

- [ ] **Step 4: Fix vm.py heap writes and alias write**

```python
# line 252: hw.field is already FieldName after HeapWrite type change
vm.heap[hw.obj_addr].fields[hw.field] = hw.value  # no change

# line 283: pointer offset alias write
vm.heap[alias_ptr.base].fields[FieldName(str(alias_ptr.offset), FieldKind.INDEX)] = tv
```

- [ ] **Step 5: Fix builtins.py**

```python
# _builtin_keys (line 129): unwrap for return values
field_names = [str(k) for k in vm.heap[addr].fields if k != FieldName("length", FieldKind.SPECIAL)]

# _builtin_array_of (lines 137-141): use INDEX for array elements, SPECIAL for length
fields = {FieldName(str(i), FieldKind.INDEX): typed_from_runtime(v) for i, v in enumerate(elements)}
fields[FieldName("length", FieldKind.SPECIAL)] = typed_from_runtime(len(elements))

# HeapWrite construction (line 146):
heap_writes=[HeapWrite(obj_addr=addr, field=k, value=v) for k, v in fields.items()]

# _slice_heap_array (line 198):
heap_obj.fields.get(FieldName("length", FieldKind.SPECIAL), ...)

# _slice_heap_array (line 203):
[heap_obj.fields.get(FieldName(str(i), FieldKind.INDEX)) for i in indices]

# _builtin_clone (lines 224-226):
HeapWrite(obj_addr=new_addr, field=k, value=v) for k, v in source.fields.items()
```

- [ ] **Step 6: Fix field_fallback.py (lines 69, 75)**

```python
# resolve_load (line 69)
return vm.heap[addr].fields.get(FieldName(str(name)))

# resolve_store (line 75)
if FieldName(str(name)) in vm.heap[addr].fields:
```

- [ ] **Step 7: Fix unresolved_call.py LLM parse (line 187)**

```python
HeapWrite(obj_addr=hw["obj_addr"], field=FieldName(hw["field"]), value=...)
```

- [ ] **Step 8: Fix mcp_server/formatting.py (line 62)**

```python
"field": str(hw.field),   # was "field": hw.field
```

- [ ] **Step 9: Run full test suite, note remaining failures**

```bash
poetry run python -m pytest tests/ -q --tb=no 2>&1 | tail -5
```

- [ ] **Step 10: Format, lint, commit**

```bash
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Fix all handler/VM/MCP consumption sites for FieldName"
```

---

## Task 4: Wrap frontend construction sites (~130 sites)

**Files:**
- Modify: ~29 frontend files + `interpreter/frontends/common/` + `interpreter/frontends/_base.py`

Dispatch 6-8 parallel subagents by language group. Each:
1. Reads file
2. Adds `from interpreter.field_name import FieldName` before `from interpreter.instructions import`
3. Wraps every `field_name=X` in LoadField/StoreField constructors with `FieldName(X)`
4. Does NOT wrap `field_name=` on other types or `field=` on HeapWrite (already handled in Task 3)

**Subagent groups:**

| Agent | Files | Est. sites |
|-------|-------|------------|
| 1 | `_base.py`, `common/` | ~15 |
| 2 | `python/`, `ruby/`, `lua/` | ~15 |
| 3 | `javascript/`, `typescript/` | ~15 |
| 4 | `java/`, `kotlin/`, `scala/` | ~25 |
| 5 | `c/`, `cpp/`, `csharp/` | ~25 |
| 6 | `go/`, `rust/`, `php/`, `pascal/` | ~35 |

- [ ] **Step 1: Dispatch 6 parallel subagents**
- [ ] **Step 2: Verify zero unwrapped sites remain (use ast-grep or comprehensive grep)**
- [ ] **Step 3: Run full test suite**

```bash
poetry run python -m pytest tests/ -q --tb=no 2>&1 | tail -5
```

- [ ] **Step 4: Format, lint, commit**

```bash
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Wrap all frontend field_name= sites with FieldName"
```

---

## Task 5: Fix test assertions (~126 sites) and add integration test

**Files:**
- Modify: ~20 test files with `.fields["X"]` accesses
- Modify: Test files with `HeapObject(fields={"X": ...})` construction
- Create integration test for INDEX/SPECIAL round-trip

- [ ] **Step 1: Write script to fix all .fields["X"] test accesses**

Similar to VarName fix script — replace `.fields["X"]` with `.fields[FieldName("X")]` and `HeapObject(fields={"X": ...})` with `FieldName("X")` keys. Run and verify.

- [ ] **Step 2: Fix test HeapObject constructions with str keys**

Search for `HeapObject(fields={` and `HeapObject(type_hint=..., fields={` in tests — wrap all str keys with `FieldName()`.

- [ ] **Step 3: Write integration test for INDEX and SPECIAL round-trip**

```python
def test_array_index_and_special_keys_round_trip(self):
    """Store and load array elements (INDEX) and length (SPECIAL) through VM."""
    vm = run("x = [10, 20, 30]", language="python")
    # Verify array is on heap with correct FieldKind tags
    # ... (assert concrete values, not symbolic)
```

- [ ] **Step 4: Run full test suite**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
```

Expected: 13,017+ passed.

- [ ] **Step 5: Format, lint, commit, close issue**

```bash
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Fix ~126 test assertions for FieldName, add integration test

All .fields[] accesses and HeapObject constructions use FieldName keys.
Integration test verifies INDEX and SPECIAL round-trip through VM.

Issue: red-dragon-j0h1

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push
bd close j0h1 --reason "FieldName domain type complete: tagged type, all instruction/heap/handler/test sites migrated, no str bridge. 13,017+ tests passing."
```
