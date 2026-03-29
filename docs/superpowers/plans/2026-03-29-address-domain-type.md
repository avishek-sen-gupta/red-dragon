# Address Domain Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `str` heap address fields on Pointer, HeapWrite, NewObject, RegionWrite, and VMState dict keys with an `Address` domain type. Introduce VMState accessor methods as the permanent API.

**Architecture:** Accessor-based incremental migration. Add VMState accessors that unwrap `str()` first, migrate all `vm.heap[addr]` callers to accessors, change field types, then per-dict migrate keys and remove `str()` from accessors. Every commit independently green. No str bridge.

**Tech Stack:** Python 3.13+, pytest, Poetry

**Spec:** `docs/superpowers/specs/2026-03-29-address-domain-type-design.md`
**Issue:** red-dragon-v217

---

## Task 1: Define Address type + tests

**Files:**
- Create: `interpreter/address.py`
- Create: `tests/unit/test_address.py`

- [ ] **Step 1: Write tests**

```python
"""Tests for Address domain type."""
import pytest
from interpreter.address import Address, NoAddress, NO_ADDRESS


class TestAddress:
    def test_str(self):
        assert str(Address("obj_0")) == "obj_0"

    def test_value(self):
        assert Address("obj_0").value == "obj_0"

    def test_is_present(self):
        assert Address("obj_0").is_present()

    def test_equality(self):
        assert Address("obj_0") == Address("obj_0")
        assert Address("obj_0") != Address("arr_1")

    def test_not_equal_to_string(self):
        assert Address("obj_0") != "obj_0"

    def test_hash(self):
        assert hash(Address("obj_0")) == hash(Address("obj_0"))

    def test_dict_lookup(self):
        d = {Address("obj_0"): 42}
        assert d[Address("obj_0")] == 42

    def test_lt(self):
        assert Address("arr_0") < Address("obj_0")

    def test_startswith(self):
        assert Address("obj_0").startswith("obj_")
        assert not Address("arr_0").startswith("obj_")

    def test_post_init_rejects_double_wrap(self):
        with pytest.raises(TypeError, match="must be str"):
            Address(Address("obj_0"))


class TestNoAddress:
    def test_str(self):
        assert str(NO_ADDRESS) == ""

    def test_not_present(self):
        assert not NO_ADDRESS.is_present()

    def test_is_instance(self):
        assert isinstance(NO_ADDRESS, Address)
```

- [ ] **Step 2: Implement Address**

```python
"""Address — typed heap/region address."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Address:
    """A heap object or region address (e.g., 'obj_0', 'arr_3', 'mem_0')."""
    value: str

    def __post_init__(self):
        if not isinstance(self.value, str):
            raise TypeError(
                f"Address.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def is_present(self) -> bool:
        return True

    def __str__(self) -> str:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Address):
            return self.value == other.value
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Address):
            return self.value < other.value
        return NotImplemented

    def startswith(self, prefix: str) -> bool:
        return self.value.startswith(prefix)


@dataclass(frozen=True, eq=False)
class NoAddress(Address):
    """Null object: no address."""
    value: str = ""

    def is_present(self) -> bool:
        return False


NO_ADDRESS = NoAddress()
```

- [ ] **Step 3: Run tests, format, lint, commit**

```bash
poetry run python -m pytest tests/unit/test_address.py -v
poetry run python -m black .
poetry run lint-imports
bd backup
git add interpreter/address.py tests/unit/test_address.py
git commit -m "Add Address domain type — no str bridge

Issue: red-dragon-v217

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Add VMState accessor methods (str() unwrap)

**Files:**
- Modify: `interpreter/vm/vm_types.py` (VMState class, ~line 127)
- Create: `tests/unit/test_address_accessors.py`

- [ ] **Step 1: Add accessors to VMState**

```python
from interpreter.address import Address

class VMState:
    # existing fields unchanged

    def heap_get(self, addr: Address) -> HeapObject:
        return self.heap.get(str(addr), NO_HEAP_OBJECT)

    def heap_set(self, addr: Address, obj: HeapObject) -> None:
        self.heap[str(addr)] = obj

    def heap_contains(self, addr: Address) -> bool:
        return str(addr) in self.heap

    def heap_ensure(self, addr: Address) -> HeapObject:
        """Get or create a HeapObject at addr."""
        if str(addr) not in self.heap:
            self.heap[str(addr)] = HeapObject()
        return self.heap[str(addr)]

    def region_get(self, addr: Address) -> bytearray | None:
        return self.regions.get(str(addr))

    def region_set(self, addr: Address, data: bytearray) -> None:
        self.regions[str(addr)] = data
```

- [ ] **Step 2: Write accessor tests**

```python
from interpreter.address import Address
from interpreter.vm.vm_types import VMState, HeapObject, NO_HEAP_OBJECT

class TestVMStateHeapAccessors:
    def test_heap_get_found(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject()
        assert vm.heap_get(Address("obj_0")) is not None

    def test_heap_get_not_found(self):
        vm = VMState()
        assert not vm.heap_get(Address("missing")).is_present()

    def test_heap_get_found_is_present(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject()
        assert vm.heap_get(Address("obj_0")).is_present()

    def test_heap_set_and_get(self):
        vm = VMState()
        obj = HeapObject()
        vm.heap_set(Address("obj_0"), obj)
        assert vm.heap_get(Address("obj_0")) is obj

    def test_heap_contains(self):
        vm = VMState()
        vm.heap["obj_0"] = HeapObject()
        assert vm.heap_contains(Address("obj_0"))
        assert not vm.heap_contains(Address("missing"))

    def test_heap_ensure_creates(self):
        vm = VMState()
        obj = vm.heap_ensure(Address("obj_0"))
        assert isinstance(obj, HeapObject)
        assert vm.heap_contains(Address("obj_0"))

    def test_heap_ensure_returns_existing(self):
        vm = VMState()
        vm.heap_set(Address("obj_0"), HeapObject())
        obj = vm.heap_ensure(Address("obj_0"))
        assert obj is vm.heap_get(Address("obj_0"))
```

- [ ] **Step 3: Run full test suite, format, lint, commit**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Add VMState heap/region accessor methods (str() unwrap)

Issue: red-dragon-v217 (Task 2)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Migrate all vm.heap[] callers to VMState accessors

**Files:**
- Modify: `interpreter/vm/vm.py` (~lines 237, 251-253, 284)
- Modify: `interpreter/handlers/memory.py` (~13 vm.heap accesses)
- Modify: `interpreter/handlers/calls.py` (~6 vm.heap accesses)
- Modify: `interpreter/vm/builtins.py` (~6 vm.heap accesses)
- Modify: `interpreter/handlers/_common.py` (~2 vm.heap accesses)
- Modify: `interpreter/handlers/variables.py` (~1 vm.heap access)
- Modify: `interpreter/vm/field_fallback.py` (~2 vm.heap accesses)
- Modify: `interpreter/handlers/regions.py` (~1 vm.regions access)

Replace all `vm.heap[addr]` with `vm.heap_get(Address(addr))` / `vm.heap_set(Address(addr), obj)` / `vm.heap_ensure(Address(addr))` / `vm.heap_contains(Address(addr))`. Similarly for `vm.regions[addr]`.

- [ ] **Step 1: Migrate vm.py apply_update**

Replace direct heap/region dict access with accessor calls. The `addr` values are still strings — wrap with `Address()`.

- [ ] **Step 2: Migrate memory.py handlers**

Replace all 13 `vm.heap[addr]` sites with accessor calls.

- [ ] **Step 3: Migrate calls.py**

Replace all 6 `vm.heap[addr]` sites with accessor calls. Address generation at line 149: `addr = Address(f"{constants.OBJ_ADDR_PREFIX}{vm.symbolic_counter}")`.

- [ ] **Step 4: Migrate builtins.py**

Replace all 6 `vm.heap[addr]` sites with accessor calls. Address generation at lines 143, 231, 262: wrap with `Address()`.

- [ ] **Step 5: Migrate _common.py, variables.py, field_fallback.py, regions.py**

Replace remaining `vm.heap[addr]` and `vm.regions[addr]` sites with accessor calls.

- [ ] **Step 6: Update _heap_addr helper**

Change `_heap_addr()` in vm.py (~line 319) to return `Address | None` instead of `str`. This is the natural wrapping point — all downstream consumers get Address.

- [ ] **Step 7: Update objects.py address generation**

Wrap address generation at lines 40, 61 with `Address()`.

- [ ] **Step 8: Run full test suite, format, lint, commit**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Migrate all vm.heap/vm.regions callers to VMState accessors

Issue: red-dragon-v217 (Task 3)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Change Pointer.base, HeapWrite, NewObject, RegionWrite to Address

**Files:**
- Modify: `interpreter/vm/vm_types.py` — Pointer.base (~line 45), HeapWrite.obj_addr (~line 176), NewObject.addr (~line 183), RegionWrite.region_addr (~line 188)
- Modify: `interpreter/vm/vm.py` — apply_update reads these fields
- Modify: Test files that construct Pointer/HeapWrite/NewObject/RegionWrite with str

- [ ] **Step 1: Change field types**

```python
# Pointer (line 45)
base: Address    # was: str

# HeapWrite (line 176) — Pydantic BaseModel
obj_addr: Address    # was: str

# NewObject (line 183) — Pydantic BaseModel
addr: Address    # was: str

# RegionWrite (line 188) — Pydantic BaseModel
region_addr: Address    # was: str
```

- [ ] **Step 2: Update apply_update to use Address fields directly**

In vm.py, `hw.obj_addr` and `rw.region_addr` are now Address — pass directly to accessors instead of wrapping.

- [ ] **Step 3: Update all Pointer(base=...) construction sites**

Wrap with `Address()` at each construction site across handlers and builtins.

- [ ] **Step 4: Update test constructions**

Tests constructing Pointer/HeapWrite/NewObject/RegionWrite with str need `Address()` wrapping.

- [ ] **Step 5: Run full test suite, format, lint, commit**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Change Pointer.base, HeapWrite, NewObject, RegionWrite to Address

Issue: red-dragon-v217 (Task 4)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Migrate vm.heap → dict[Address, HeapObject]

**Files:**
- Modify: `interpreter/vm/vm_types.py` — VMState.heap field type (~line 127)
- Modify: `interpreter/vm/vm_types.py` — to_dict serialization (~line 151)

- [ ] **Step 1: Change heap field type**

```python
heap: dict[Address, HeapObject] = field(default_factory=dict)
```

- [ ] **Step 2: Remove str() from heap accessors**

```python
def heap_get(self, addr: Address) -> HeapObject | None:
    return self.heap.get(addr)  # was: str(addr)

def heap_set(self, addr: Address, obj: HeapObject) -> None:
    self.heap[addr] = obj  # was: str(addr)

def heap_contains(self, addr: Address) -> bool:
    return addr in self.heap  # was: str(addr)

def heap_ensure(self, addr: Address) -> HeapObject:
    if addr not in self.heap:
        self.heap[addr] = HeapObject()
    return self.heap[addr]
```

- [ ] **Step 3: Update to_dict serialization**

```python
"heap": {str(k): v.to_dict() for k, v in self.heap.items()},
```

- [ ] **Step 4: Run full test suite, format, lint, commit**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Migrate vm.heap to dict[Address, HeapObject], remove str() from accessors

Issue: red-dragon-v217 (Task 5)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Migrate vm.regions → dict[Address, bytearray]

**Files:**
- Modify: `interpreter/vm/vm_types.py` — VMState.regions field type (~line 132)
- Modify: `interpreter/vm/vm_types.py` — to_dict serialization (~line 161)

- [ ] **Step 1: Change regions field type**

```python
regions: dict[Address, bytearray] = field(default_factory=dict)
```

- [ ] **Step 2: Remove str() from region accessors**

```python
def region_get(self, addr: Address) -> bytearray | None:
    return self.regions.get(addr)  # was: str(addr)

def region_set(self, addr: Address, data: bytearray) -> None:
    self.regions[addr] = data  # was: str(addr)
```

- [ ] **Step 3: Update to_dict serialization**

```python
"regions": {str(addr): list(data) for addr, data in self.regions.items()},
```

- [ ] **Step 4: Run full test suite, format, lint, commit**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Migrate vm.regions to dict[Address, bytearray]

Issue: red-dragon-v217 (Task 6)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Fix test assertions (~133 sites) + close issue

**Files:**
- Modify: ~29 test files with `vm.heap[str_addr]` patterns

- [ ] **Step 1: Write script to fix vm.heap[] test accesses**

Replace `vm.heap["addr"]` with `vm.heap_get(Address("addr"))` or `vm.heap[Address("addr")]` across all test files. Also fix `Pointer(base="addr")` → `Pointer(base=Address("addr"))` and similar.

- [ ] **Step 2: Fix test HeapObject construction helpers**

Search for `vm.heap["..."] = HeapObject(...)` in tests — replace with `vm.heap_set(Address("..."), HeapObject(...))`.

- [ ] **Step 3: Fix Pointer construction in tests**

Search for `Pointer(base="..."` in tests — wrap with `Address()`.

- [ ] **Step 4: Run full test suite**

```bash
poetry run python -m pytest tests/ -x -q --tb=short
```

Expected: 13,080+ passed.

- [ ] **Step 5: Format, lint, commit, close issue**

```bash
poetry run python -m black .
poetry run lint-imports
bd backup && git add -A
git commit -m "Fix test assertions for Address domain type

~133 vm.heap[] accesses and Pointer/HeapWrite constructions updated.

Issue: red-dragon-v217

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push
bd close v217 --reason "Address domain type complete: VMState accessors as permanent API, heap/regions Address-keyed, Pointer.base/HeapWrite/NewObject/RegionWrite use Address. 13,080+ tests passing."
```
