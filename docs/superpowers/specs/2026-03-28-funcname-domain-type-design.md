# FuncName Domain Type — Design Spec

**Date:** 2026-03-28
**Issue:** red-dragon-cnz9
**Status:** Approved

## Goal

Replace `str` function/method name fields on IR instructions with a `FuncName` domain type. Introduce accessor methods on registries and builtin tables as the permanent API — callers never access the underlying dicts directly. Enables incremental, per-dict migration with every commit green.

## Architecture

Simple wrapper `FuncName(value: str)` following the VarName precedent. Single type for both function names and method names. No str bridge — strict from day one. Accessor methods on each registry/table encapsulate dict access; during migration they unwrap with `str()`, after migration they pass FuncName as-is. Dicts become private, accessors stay forever.

## Type Definition

File: `interpreter/func_name.py`

```python
@dataclass(frozen=True)
class FuncName:
    """A function or method name."""
    value: str

    def __post_init__(self):
        if not isinstance(self.value, str):
            raise TypeError(...)

    def is_present(self) -> bool: return True
    def __str__(self) -> str: return self.value
    def __hash__(self) -> int: return hash(self.value)
    def __eq__(self, other):  # FuncName-only, NO str bridge
    def __lt__(self, other):  # for sorting
    def startswith(self, prefix: str): ...  # for __cobol_ check
    def __contains__(self, item: str): ...  # for "[" in name check

@dataclass(frozen=True, eq=False)
class NoFuncName(FuncName):
    value: str = ""
    def is_present(self) -> bool: return False

NO_FUNC_NAME = NoFuncName()
```

### Design decisions

- **Single type for func_name and method_name.** Both are callable names. The accessor method on the registry distinguishes the lookup context, not the type.
- **Clean names only.** No embedded type parameters (`"Box[Node]"` is banned — tracked as n9tr). FuncName stores `"Box"`, not `"Box[Node]"`.
- **No str bridge.** Accessor pattern enables incremental migration without a bridge.
- **`__post_init__` guard.** Rejects double-wrapping.

## Instruction Field Changes

| Class | Field | Before | After |
|-------|-------|--------|-------|
| `CallFunction` | `func_name` | `str = ""` | `FuncName = NO_FUNC_NAME` |
| `CallMethod` | `method_name` | `str = ""` | `FuncName = NO_FUNC_NAME` |
| `CallCtorFunction` | `func_name` | `str = ""` | `FuncName = NO_FUNC_NAME` |

`CallUnknown` has no name field — unchanged.

`operands` properties return `str(self.func_name)` / `str(self.method_name)` for display.

`_to_typed` converters wrap with `FuncName(str(ops[...]))`.

## Accessor Pattern

Each str-keyed dict gets an accessor method. The accessor is the **permanent API** — callers never access the dict directly. During migration, the accessor unwraps with `str()`. After migration, the accessor passes FuncName as-is and the dict is FuncName-keyed.

### FunctionRegistry (`interpreter/registry.py`)

```python
class FunctionRegistry:
    # Phase 1: str-keyed (existing)
    # Phase final: FuncName-keyed, private
    _func_refs: dict[FuncName, FuncRef]
    _class_methods: dict[str, dict[FuncName, list[CodeLabel]]]

    def lookup_func(self, name: FuncName) -> FuncRef | None:
        return self._func_refs.get(name)

    def lookup_methods(self, class_name: str, name: FuncName) -> list[CodeLabel]:
        return self._class_methods.get(class_name, {}).get(name, [])

    def register_func(self, name: FuncName, ref: FuncRef) -> None:
        self._func_refs[name] = ref

    def register_method(self, class_name: str, name: FuncName, label: CodeLabel) -> None:
        self._class_methods.setdefault(class_name, {}).setdefault(name, []).append(label)
```

### Builtins (`interpreter/vm/builtins.py`)

```python
class Builtins:
    # Phase final: FuncName-keyed, private
    _TABLE: dict[FuncName, Callable]
    _METHOD_TABLE: dict[FuncName, Callable]

    @classmethod
    def lookup_builtin(cls, name: FuncName) -> Callable | None:
        return cls._TABLE.get(name)

    @classmethod
    def lookup_method_builtin(cls, name: FuncName) -> Callable | None:
        return cls._METHOD_TABLE.get(name)
```

### Type Inference (`interpreter/types/type_inference.py`)

```python
# func_return_types, class_method_types inner key
# Accessor methods on _InferenceContext
def lookup_func_return_type(self, name: FuncName) -> TypeExpr:
    return self._func_return_types.get(name, UNKNOWN)

def lookup_method_type(self, class_name: TypeExpr, name: FuncName) -> TypeExpr:
    return self._class_method_types.get(class_name, {}).get(name, UNKNOWN)
```

### Call Graph (`interpreter/interprocedural/call_graph.py`)

```python
# call_target_map accessor
def lookup_call_target(self, name: FuncName) -> CodeLabel | None: ...
```

### COBOL IO Dispatch (`interpreter/cobol/io_provider.py`)

```python
# _COBOL_IO_DISPATCH accessor
def dispatch(self, name: FuncName) -> str | None:
    return self._dispatch.get(name)
```

## Migration Sequence

Every commit is independently green. Each phase migrates one dict.

| Commit | What |
|--------|------|
| 1 | Define FuncName type + tests |
| 2 | Add accessor methods to all registries/tables (unwrap with `str()` internally). Dicts stay str-keyed. |
| 3 | Migrate all callers to use accessors instead of direct dict access |
| 4 | Wrap ~307 frontend/COBOL construction sites + change instruction field types |
| 5 | Migrate `Builtins.TABLE` → `dict[FuncName, ...]`, remove `str()` in accessor |
| 6 | Migrate `Builtins.METHOD_TABLE` → same |
| 7 | Migrate `FunctionRegistry.func_refs` → same |
| 8 | Migrate `FunctionRegistry.class_methods` inner key → same |
| 9 | Migrate type_inference + call_graph + COBOL dispatch dicts → same |
| 10 | Fix test assertions, close issue |

## Boundary Rules

| Site | Action |
|------|--------|
| Frontend `node_text()` → CallFunction/CallMethod/CallCtorFunction | Wrap `FuncName(text)` at origin |
| COBOL `__cobol_*` calls | Wrap `FuncName(name)` at origin |
| `_to_typed` converters | Wrap `FuncName(str(ops[...]))` |
| `reasoning=f"..."` strings | No change — f-string calls `__str__` |
| JSON/MCP serialization | Unwrap `str(name)` at boundary |
| Symbol table lookups (`class_info.methods`, `class_info.constants`) | Unwrap `str(name)` — symbol table not migrated (9adr) |
| `calls.py` split("[") hack | Remains until n9tr (Rust Box/Option CallCtor migration) |

## Testing Strategy

- **Unit tests** for FuncName type: equality, hash, is_present, `__post_init__`, `__lt__`, startswith, `__contains__`.
- **Unit tests** for each accessor method: lookup_func, lookup_methods, lookup_builtin, lookup_method_builtin.
- Existing 13,039 tests exercise all call paths.

## What This Does NOT Cover

- **Rust `Box[Node]` encoding (n9tr):** Separate issue to migrate to CallCtorFunction. Until then, `calls.py` split("[") hack remains.
- **SymbolTable/FunctionRegistry full migration (9adr):** ClassInfo.methods, SymbolTable.functions still use str keys.
- **CallUnknown:** No name field — not in scope.
