# ClosureId Domain Type — Design Spec

**Date:** 2026-03-30
**Status:** Approved
**Pattern:** ContinuationName (frozen dataclass + null object)
**Scope:** ~25 change sites across ~10 files

## Problem

Closure identifiers are stringly-typed throughout the VM. The `closure_id` and `closure_env_id` fields use bare `str`, making it impossible to distinguish closure IDs from arbitrary strings at the type level. The empty string `""` serves as a sentinel for "no closure" with no type-level enforcement.

## Design

### New File: `interpreter/closure_id.py`

Frozen dataclass following the established domain type pattern (ContinuationName, Address, VarName, etc.):

- `ClosureId(value: str)` — frozen, hashable, `__str__` returns `value`
- `NoClosureId(ClosureId)` — null object subclass, `value=""`, `is_present() → False`
- `NO_CLOSURE_ID` — module-level sentinel instance
- `__post_init__` validates `value` is `str`
- `__hash__`, `__eq__` for dict key usage
- No `__eq__(str)` compatibility bridge — clean break

### Type Annotation Changes

| Location | File | Before | After |
|---|---|---|---|
| `BoundFuncRef.closure_id` | `interpreter/refs/func_ref.py:24` | `str` | `ClosureId`, default `NO_CLOSURE_ID` |
| `StackFrame.closure_env_id` | `interpreter/vm/vm_types.py:107` | `str = ""` | `ClosureId`, default `NO_CLOSURE_ID` |
| `StackFramePush.closure_env_id` | `interpreter/vm/vm_types.py:282` | `str = ""` | `ClosureId`, default `NO_CLOSURE_ID` |
| `VMState.closures` | `interpreter/vm/vm_types.py:148` | `dict[str, ClosureEnvironment]` | `dict[ClosureId, ClosureEnvironment]` |

### Construction Sites (~8)

| File | Change |
|---|---|
| `interpreter/handlers/variables.py:52,69,71,74,79` | `f"closure_{counter}"` → `ClosureId(f"closure_{counter}")` |
| `interpreter/handlers/calls.py:230-252,472` | Closure lookup/passing — wrap string in `ClosureId()` |
| `interpreter/handlers/memory.py:85` | `BoundFuncRef(closure_id="")` → `BoundFuncRef()` (uses default `NO_CLOSURE_ID`) |

### Consumer Sites (~8)

| File | Change |
|---|---|
| `interpreter/handlers/_common.py:70-71` | Closure env lookup via `frame.closure_env_id` — unchanged semantics, just typed |
| `interpreter/vm/vm.py:266,289-290` | `apply_update` closure_env_id handling — unchanged semantics |
| `interpreter/run.py:765-766` | Serialization: `str(bound_ref.closure_id)` for function ref string |
| `interpreter/vm/vm_types.py:123-124` | `StackFrame.to_dict()`: `str(self.closure_env_id)` in conditional |

### Test Changes (~12 references across 5 files)

| File | Refs | Change |
|---|---|---|
| `tests/unit/test_func_ref.py` | 6 | `closure_id="x"` → `closure_id=ClosureId("x")` |
| `tests/unit/test_materialize_raw_update.py` | 2 | Same pattern |
| `tests/unit/test_method_missing.py` | 2 | Same pattern |
| `tests/unit/test_load_field_indirect.py` | 1 | Same pattern |
| `tests/unit/test_heap_field_method_call.py` | 1 | Same pattern |

## Decisions

- **No `__eq__(str)` bridge:** All sites updated atomically. Clean break, consistent with ContinuationName.
- **Default sentinel in dataclass fields:** `BoundFuncRef`, `StackFrame`, and `StackFramePush` all default to `NO_CLOSURE_ID`, matching the current `""` default behavior.
- **Dict key migration:** `VMState.closures` key type changes from `str` to `ClosureId`. Works because `ClosureId` is frozen and implements `__hash__`/`__eq__`.

## Non-Goals

- Changing the closure ID naming scheme (`closure_{counter}`).
- Refactoring closure creation or lookup logic.
- Adding validation beyond type checking (e.g., format validation of the counter suffix).
