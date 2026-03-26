# VarName Domain Type — Design Spec

**Date:** 2026-03-27
**Issue:** red-dragon-w667 (epic), b9cd (type definition), jdx0 (frontend wrapping), 90z9 (VM cascade + strict)
**Status:** Approved

## Goal

Replace `str` variable name fields on IR instructions and `dict[str, ...]` VM scope chain keys with a `VarName` domain type. Prevents accidental interchange of variable names with field names, function names, or arbitrary strings.

## Architecture

Simple wrapper type following the CodeLabel precedent. Bridge-first migration: `VarName.__eq__(str)` ensures backward compatibility during the transition. No structured decomposition (base/scope_id) — that's Phase 2 (red-dragon-kozu) when block-scope mangling is needed.

## Issue Breakdown

```
w667 [epic] Introduce VarName domain type
├── b9cd [P2] Define VarName simple wrapper type + tests
│   ├── jdx0 [P2] Phase 1a: wrap ~450 frontend/COBOL construction sites
│   └── 90z9 [P2] Phase 1b: change field types, cascade VM/handlers/tests, remove bridge
├── ss6g [P3] Migrate ClosureEnvironment.bindings keys from str to VarName
└── kozu [P3] Phase 2: add base/scope_id structured decomposition (future)
```

## Type Definition

File: `interpreter/var_name.py`

```python
@dataclass(frozen=True)
class VarName:
    """Typed variable name — wraps a string with domain semantics."""
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
        if isinstance(other, str):       # bridge — removed in 90z9
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

### Design decisions

- **Simple wrapper, not structured.** `value: str` only — no `base`/`scope_id` decomposition. The `$` mangling convention doesn't exist in the codebase today. YAGNI. Phase 2 (kozu) adds it when needed.
- **`__post_init__` guard.** Rejects `VarName(VarName(...))` double-wrapping at construction time, matching the CodeLabel/Register precedent. Bugs surface immediately at the wrapping site, not downstream.
- **`__eq__(str)` bridge.** During migration, `VarName("x") == "x"` is True and `hash(VarName("x")) == hash("x")`. This keeps `dict[str, ...]` lookups working while field types are being changed. Removed last.
- **`NoVarName` uses `@dataclass(frozen=True, eq=False)`.** Prevents auto-generated `__eq__` from shadowing the parent's bridge equality. Matches the `NoRegister`/`NoCodeLabel` pattern.
- **Domain methods.** `__contains__` and `startswith` cover the two call sites that do string operations on variable names (`__cobol_*` prefix check, `PARAM_PREFIX` check). No `endswith`, `split`, or regex needed today.
- **`is_self` property.** Covers Python/Ruby/Lua/Scala (`self`), Java/C#/C++/Kotlin/JS/TS (`this`), and PHP (`$this`).
- **Null object pattern.** `NO_VAR_NAME` with `is_present() → False`, matching CodeLabel/Register conventions. `str(NO_VAR_NAME) == ""`, so `operands` output is unchanged from the current `str = ""` default.

## Instruction Field Changes

4 fields across 4 instruction classes in `interpreter/instructions.py`:

| Class | Field | Before | After |
|-------|-------|--------|-------|
| `LoadVar` | `name` | `str = ""` | `VarName = NO_VAR_NAME` |
| `DeclVar` | `name` | `str = ""` | `VarName = NO_VAR_NAME` |
| `StoreVar` | `name` | `str = ""` | `VarName = NO_VAR_NAME` |
| `AddressOf` | `var_name` | `str = ""` | `VarName = NO_VAR_NAME` |

`operands` properties return `str(self.name)` / `str(self.var_name)` for display and serialization. When `name` is `NO_VAR_NAME`, `str(NO_VAR_NAME) == ""`, so serialized output is unchanged.

4 `_to_typed` legacy converters (`_load_var`, `_decl_var`, `_store_var`, `_address_of`) updated to wrap with `VarName(str(ops[0]))` as part of 90z9.

## Frontend Wrapping (~450 sites)

All DeclVar/StoreVar/LoadVar/AddressOf construction sites across 50 frontend and 3 COBOL files wrapped with `VarName()`:

```python
# Before
DeclVar(name=var_name, value_reg=reg)
# After
DeclVar(name=VarName(var_name), value_reg=reg)
```

Executed via 8-10 parallel subagents grouped by language, same pattern as BinopKind Task 2. Import `from interpreter.var_name import VarName` added before `from interpreter.instructions import` block.

## VM Scope Chain Cascade

Three dict/frozenset types in `interpreter/vm/vm_types.py` change key type:

| Field | Before | After |
|-------|--------|-------|
| `StackFrame.local_vars` | `dict[str, TypedValue]` | `dict[VarName, TypedValue]` |
| `StackFrame.captured_var_names` | `frozenset[str]` | `frozenset[VarName]` |
| `StackFrame.var_heap_aliases` | `dict[str, Pointer]` | `dict[VarName, Pointer]` |

~26 usages across handlers (`variables.py`, `_common.py`, `calls.py`, `objects.py`, `memory.py`), `vm.py`, `field_fallback.py`, and `llm/backend.py`. Handler writes updated to construct `VarName(name)` for dict keys.

Bridge `__eq__(str)` + hash compat means existing `local_vars[name]` lookups (where `name` is str) work during migration. Bridge removed last after all sites use VarName.

## Test Changes (~400 assertions)

```python
# Before
assert unwrap(vm.current_frame.local_vars["x"]) == 42
# After bridge removal
assert unwrap(vm.current_frame.local_vars[VarName("x")]) == 42
```

## Testing Strategy

- **Unit tests** for VarName type: equality, hash, is_self, is_present, bridge compat, `__contains__`, `startswith`, `__post_init__` double-wrap rejection.
- **No new integration tests** — existing 13,000 tests exercise all variable paths. Zero regressions = success.

## What This Does NOT Cover

- **Phase 2 (kozu):** `base`/`scope_id` decomposition, `from_str()` parsing, `is_mangled` property. Deferred until block-scope mangling is implemented.
- **ClosureEnvironment.bindings (ss6g):** Uses `dict[str, TypedValue]` keys for closure bindings. Tracked as a separate P3 follow-up.
- **FieldName (j0h1):** Separate domain type for LoadField/StoreField field names. Independent migration.
- **FuncName (cnz9):** Separate domain type for CallFunction/CallMethod function/method names.
