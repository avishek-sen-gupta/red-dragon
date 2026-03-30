# ContinuationName Domain Type Design

**Date:** 2026-03-30
**Issues:** red-dragon-ti2e, red-dragon-dy92
**Status:** Approved

## Problem

`SetContinuation.name` and `ResumeContinuation.name` are raw `str` fields representing COBOL PERFORM continuation point names (e.g., `"section_FOO_end"`, `"para_BAR_end"`). These flow through `VMState.continuations` (dict key), `StateUpdate.continuation_writes` (dict key), and `StateUpdate.continuation_clear` — all using `str`. A continuation name is conceptually distinct from a branch target label (`CodeLabel`), a variable name (`VarName`), or any other string identifier, but the type system does not enforce this.

## Decision

Introduce `ContinuationName` as a frozen dataclass wrapping `str`, following the established Address/VarName/FieldName pattern. No `__eq__(str)` bridge — strict from day one.

## New File: `interpreter/continuation_name.py`

```python
@dataclass(frozen=True)
class ContinuationName:
    value: str

    def __post_init__(self):
        if not isinstance(self.value, str):
            raise TypeError(...)

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

class NoContinuationName(ContinuationName):
    value: str = ""
    def is_present(self) -> bool:
        return False

NO_CONTINUATION_NAME = NoContinuationName()
```

No domain methods needed — continuation names are opaque lookup keys.

## Migration Surface

### Type annotations (5 changes)

| Location | Current | Target |
|---|---|---|
| `SetContinuation.name` | `str` | `ContinuationName` |
| `ResumeContinuation.name` | `str` | `ContinuationName` |
| `VMState.continuations` key | `dict[str, CodeLabel]` | `dict[ContinuationName, CodeLabel]` |
| `StateUpdate.continuation_writes` key | `dict[str, CodeLabel]` | `dict[ContinuationName, CodeLabel]` |
| `StateUpdate.continuation_clear` | `str` | `ContinuationName` |

### Default values

- `SetContinuation.name`: `""` → `NO_CONTINUATION_NAME`
- `ResumeContinuation.name`: `""` → `NO_CONTINUATION_NAME`
- `StateUpdate.continuation_clear`: `""` → `NO_CONTINUATION_NAME`

### Construction sites — COBOL frontend (3 sites)

- `lower_perform.py:90` — `name=str(continuation_key)` → `name=ContinuationName(str(continuation_key))`
- `lower_procedure.py:48` — `name=f"section_{name}_end"` → `name=ContinuationName(f"section_{name}_end")`
- `lower_procedure.py:60` — `name=f"para_{name}_end"` → `name=ContinuationName(f"para_{name}_end")`

### Handler sites (2 — pass-through, no logic change)

- `_handle_set_continuation` — reads `t.name` (now `ContinuationName`), passes as `continuation_writes` key
- `_handle_resume_continuation` — reads `t.name`, does `vm.continuations.get(name)` — works unchanged

### apply_update (vm.py — 2 sites)

- `continuation_writes` loop: keys become `ContinuationName`, assignment unchanged
- `continuation_clear`: `vm.continuations.pop(update.continuation_clear, None)` — works unchanged since `ContinuationName` is hashable; falsy check on `NO_CONTINUATION_NAME` returns `False` via `__bool__`

### Serialization (1 site)

- `VMState.to_dict()`: `{k: str(v) for k, v in self.continuations.items()}` → `{str(k): str(v) for k, v in self.continuations.items()}` — wrap key in `str()`

### Factory `_to_typed` (2 converters)

- `_set_continuation`: wrap `str(ops[0])` in `ContinuationName(...)`
- `_resume_continuation`: wrap `str(inst.operands[0])` in `ContinuationName(...)`

### Tests (~17 references across 4 files)

- `test_continuations.py` — update `name=` args and assertions
- `test_typed_instructions.py` — update construction
- `test_typed_instruction_compat.py` — update construction
- `test_map_registers_labels.py` — update construction

## Total Scope

~20 change sites across ~10 files. COBOL-only feature, self-contained migration. Closes both ti2e and dy92.
