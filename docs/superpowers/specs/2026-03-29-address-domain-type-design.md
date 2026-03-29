# Address Domain Type — Design Spec

**Date:** 2026-03-29
**Issue:** red-dragon-v217
**Status:** Approved

## Goal

Replace `str` heap address fields on Pointer, HeapWrite, NewObject, RegionWrite, and VMState dict keys with an `Address` domain type. Introduce accessor methods on VMState as the permanent API for heap/region access.

## Architecture

Simple wrapper `Address(value: str)` following the VarName/FuncName precedent. Accessor pattern for incremental per-dict migration — every commit independently green. No str bridge. Closures excluded (separate ClosureId type, tracked as tjv4).

## Type Definition

File: `interpreter/address.py`

```python
@dataclass(frozen=True)
class Address:
    """A heap object or region address (e.g., 'obj_0', 'arr_3', 'mem_0')."""
    value: str

    def __post_init__(self):
        if not isinstance(self.value, str):
            raise TypeError(...)

    def is_present(self) -> bool: return True
    def __str__(self) -> str: return self.value
    def __hash__(self) -> int: return hash(self.value)
    def __eq__(self, other):  # Address-only, NO str bridge
    def __lt__(self, other):  # for sorting
    def startswith(self, prefix: str): ...  # for obj_/arr_/mem_ prefix checks

@dataclass(frozen=True, eq=False)
class NoAddress(Address):
    value: str = ""
    def is_present(self) -> bool: return False

NO_ADDRESS = NoAddress()
```

### Design decisions

- **No tag.** Unlike FieldName, all addresses are the same kind. Prefixes (obj_, arr_, mem_, sym_) are naming conventions, not identity discriminators.
- **No str bridge.** Accessor pattern enables incremental migration.
- **Closures excluded.** Closure IDs are semantically distinct from heap addresses. Tracked as tjv4.

## Field Changes

| Class | Field | Before | After |
|-------|-------|--------|-------|
| `Pointer` | `base` | `str` | `Address` |
| `HeapWrite` (Pydantic) | `obj_addr` | `str` | `Address` |
| `NewObject` (Pydantic) | `addr` | `str` | `Address` |
| `RegionWrite` (Pydantic) | `region_addr` | `str` | `Address` |
| `VMState` | `heap` keys | `dict[str, HeapObject]` | `dict[Address, HeapObject]` |
| `VMState` | `regions` keys | `dict[str, ...]` | `dict[Address, ...]` |

## VMState Accessors (permanent API)

```python
class VMState:
    # heap and regions become private after migration

    def heap_get(self, addr: Address) -> HeapObject | None:
        return self.heap.get(addr)

    def heap_set(self, addr: Address, obj: HeapObject) -> None:
        self.heap[addr] = obj

    def heap_contains(self, addr: Address) -> bool:
        return addr in self.heap

    def region_get(self, addr: Address) -> list[int] | None:
        return self.regions.get(addr)

    def region_set(self, addr: Address, data: list[int]) -> None:
        self.regions[addr] = data
```

## Migration Sequence

Every commit independently green.

| Commit | What |
|--------|------|
| 1 | Define Address type + tests |
| 2 | Add VMState accessors (unwrap with `str()` internally) |
| 3 | Migrate all `vm.heap[addr]` callers → VMState accessors |
| 4 | Change Pointer.base, HeapWrite.obj_addr, NewObject.addr, RegionWrite.region_addr to Address |
| 5 | Migrate `vm.heap` → `dict[Address, HeapObject]`, remove `str()` from heap accessors |
| 6 | Migrate `vm.regions` → `dict[Address, ...]`, remove `str()` from region accessors |
| 7 | Fix test assertions (~169 sites) |

## Boundary Rules

| Site | Action |
|------|--------|
| Address generation (`f"obj_{counter}"`) | Wrap `Address(f"obj_{counter}")` at origin |
| `_heap_addr()` helper in handlers | Returns `Address | None` (wraps at extraction point) |
| `shared_heap_addr()` in vm.py | Returns `Address | None` |
| `Pointer(base=addr)` construction | `addr` is Address after field change |
| Serialization (to_dict, JSON) | `str(addr)` at boundary |
| `reasoning=f"..."` strings | No change — `__str__` handles it |
| Closure IDs (`closure_42`, `env_3`) | Stay `str` — excluded from this migration (tjv4) |

## Testing Strategy

- Unit tests for Address type: equality, hash, is_present, `__post_init__`, `__lt__`, startswith.
- Unit tests for VMState accessors: heap_get, heap_set, heap_contains, region_get, region_set.
- Existing 13,080 tests cover all heap access paths.

## What This Does NOT Cover

- **ClosureId (tjv4):** Closure environment identifiers (`closure_42`, `env_3`). Separate domain type.
- **SymbolTable/FunctionRegistry (9adr):** Symbol table keys stay str.
- **Pointer.offset:** Stays `int`. Not an address.
