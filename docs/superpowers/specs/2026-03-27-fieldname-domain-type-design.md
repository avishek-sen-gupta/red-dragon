# FieldName Domain Type — Design Spec

**Date:** 2026-03-27
**Issue:** red-dragon-j0h1
**Status:** Approved

## Goal

Replace `str` field name fields on IR instructions and `dict[str, ...]` heap object keys with a tagged `FieldName` domain type. Prevents accidental interchange of field names with variable names, function names, or arbitrary strings. The tag distinguishes property access, array indexing, and special keys.

## Architecture

Tagged frozen dataclass `FieldName(value: str, kind: FieldKind)` with `FieldKind` enum (`PROPERTY`, `INDEX`, `SPECIAL`). Default kind is `PROPERTY` — most construction sites need no explicit tag. **No str bridge** — strict from day one. All construction AND consumption sites fixed in one pass.

## Type Definition

File: `interpreter/field_name.py`

```python
class FieldKind(Enum):
    PROPERTY = "property"   # obj.name, obj.age
    INDEX = "index"         # arr[0], arr[1]
    SPECIAL = "special"     # __method_missing__, length

@dataclass(frozen=True)
class FieldName:
    value: str
    kind: FieldKind = FieldKind.PROPERTY

    def __post_init__(self):
        if not isinstance(self.value, str):
            raise TypeError(
                f"FieldName.value must be str, got {type(self.value).__name__}: {self.value!r}"
            )

    def is_present(self) -> bool: return True
    def __str__(self) -> str: return self.value

    def __hash__(self) -> int:
        return hash((self.value, self.kind))

    def __eq__(self, other):
        if isinstance(other, FieldName):
            return self.value == other.value and self.kind == other.kind
        return NotImplemented

    def __lt__(self, other):
        if isinstance(other, FieldName):
            return (self.value, self.kind.value) < (other.value, other.kind.value)
        return NotImplemented

    def __contains__(self, item: str): return item in self.value
    def startswith(self, prefix: str): return self.value.startswith(prefix)

@dataclass(frozen=True, eq=False)
class NoFieldName(FieldName):
    """Null object. eq=False preserves parent __eq__. Use .is_present() for null checks."""
    value: str = ""
    kind: FieldKind = FieldKind.PROPERTY
    def is_present(self) -> bool: return False

NO_FIELD_NAME = NoFieldName()
```

### Design decisions

- **Tagged, not hierarchical.** `FieldKind` enum on a single class rather than `PropertyName`/`IndexKey`/`SpecialKey` subclasses. Simpler, same expressiveness.
- **Default PROPERTY.** ~130 frontend sites construct properties — no explicit tag needed. Only array/special sites (~20 in builtins/handlers) pass the tag.
- **No str bridge.** Lesson from VarName: bridge-then-remove costs more than going strict from day one.
- **`__post_init__` guard.** Rejects `FieldName(FieldName(...))` double-wrapping and non-str values.
- **Kind is part of identity.** `__eq__` and `__hash__` include both `value` and `kind`. `FieldName("0", INDEX) != FieldName("0", PROPERTY)`. This means writers and readers must agree on the kind — a field stored as INDEX must be looked up as INDEX. In practice this is naturally consistent: StoreField always uses PROPERTY, array builtins always use INDEX, and special keys always use SPECIAL. The indirect handler boundary (LoadFieldIndirect, StoreIndirect) must use the correct kind when wrapping runtime strings — see mmdt for analysis.
- **`NoFieldName(eq=False)` preserves parent `__eq__`.** Use `x.is_present()` for null checks, not `x == NO_FIELD_NAME`.

## Instruction Field Changes

| Class | Field | Before | After |
|-------|-------|--------|-------|
| `LoadField` | `field_name` | `str = ""` | `FieldName = NO_FIELD_NAME` |
| `StoreField` | `field_name` | `str = ""` | `FieldName = NO_FIELD_NAME` |

`operands` properties return `str(self.field_name)` for display.

`_to_typed` converters wrap with `FieldName(str(ops[...]))`.

## HeapObject.fields Key Type

```python
class HeapObject:
    fields: dict[FieldName, TypedValue]   # was dict[str, TypedValue]
```

All heap field reads/writes use FieldName keys.

## HeapWrite Pydantic Model

```python
class HeapWrite(BaseModel):
    obj_addr: str
    field: FieldName    # was str
    value: Any
```

## Construction Sites (~160)

**Frontend (~130 sites, 29 files):** `field_name=FieldName(name)` — all default PROPERTY.

**Builtins/handlers (~30 sites):**
- Array index: `FieldName(str(i), FieldKind.INDEX)`
- Length: `FieldName("length", FieldKind.SPECIAL)`
- Method missing: `FieldName(constants.METHOD_MISSING, FieldKind.SPECIAL)`
- Boxed field: `FieldName(constants.BOXED_FIELD, FieldKind.SPECIAL)`
- Pointer offset in vm.py: `FieldName(str(alias_ptr.offset), FieldKind.INDEX)`
- Implicit this field write in `variables.py:165`: `HeapWrite(field=FieldName(str(name)))` — crosses VarName→FieldName boundary
- Address-of promotion in `memory.py:168`: `HeapObject(fields={FieldName("0", FieldKind.INDEX): ...})`
- Spread-argument expansion in `_common.py`: `FieldName(str(i), FieldKind.INDEX)` for indexed access
- LLM JSON deserialization in `unresolved_call.py:188`: `HeapWrite(field=FieldName(hw["field"]))` — wraps at parse boundary, assumes PROPERTY

**Indirect field access handlers (`LoadFieldIndirect`, `StoreFieldIndirect`, `StoreIndirect`):**
These have no `field_name` field (they use `name_reg: Register` for dynamic names). However, at runtime they look up `heap_obj.fields` with a string value from a register. After migration, they must wrap at the handler boundary:
```python
# _handle_load_field_indirect (memory.py ~line 248)
field_key = FieldName(str(field_name))   # wrap runtime str value
if field_key in heap_obj.fields: ...

# _handle_store_indirect (memory.py ~line 289)
HeapWrite(field=FieldName(str(target_field), FieldKind.INDEX), ...)
```

## Boundary Rules

| Site | Action | Rationale |
|------|--------|-----------|
| Frontend `node_text()` → LoadField/StoreField | Wrap `FieldName(text)` | Origin — wrap early |
| Builtins array access `str(i)` | Wrap `FieldName(str(i), INDEX)` | Origin |
| Constants `"length"`, `"__method_missing__"` | Wrap `FieldName(X, SPECIAL)` | Origin |
| Pointer offset `str(alias_ptr.offset)` | Wrap `FieldName(str(offset), INDEX)` | Origin |
| Indirect handler runtime values | Wrap `FieldName(str(value))` | Origin — runtime str → FieldName at handler boundary |
| Address-of promotion `{"0": ...}` | Wrap `FieldName("0", INDEX)` | Origin |
| Implicit this HeapWrite `str(name)` | Wrap `FieldName(str(name))` | VarName→FieldName boundary |
| LLM JSON parse `hw["field"]` | Wrap `FieldName(hw["field"])` | Deserialization boundary |
| `class_info.constants[field_name]` | Unwrap `str(field_name)` | Symbol table boundary (not migrated, see 9adr) |
| `typed(field_name, scalar("String"))` | Unwrap `str(field_name)` | Runtime value, not a key |
| `HeapObject.to_dict()` | Unwrap `str(k)` in fields dict comprehension | Serialization boundary |
| JSON/MCP serialization | Unwrap `str(k)` | Serialization boundary — unwrap late |
| `_builtin_keys` return values | Unwrap `str(k)` | Returns string values to user code, not keys |
| `reasoning=f"..."` strings | No change | f-string calls `__str__` automatically |

**Principle:** FieldName stays as FieldName through the entire instruction → handler → heap path. Wrap at origin (frontends, builtins, runtime handlers, deserialization). Unwrap to str only at serialization boundaries, the symbol table boundary (tracked as follow-up 9adr), and when producing runtime string values.

## Test Changes (~126 sites, 20 files)

`.fields["X"]` → `.fields[FieldName("X")]` across test assertions.

Also fix test setup sites that construct `HeapObject(fields={"X": ...})` with str keys.

## Testing Strategy

- **Unit tests** for FieldName type: equality (value-only, kind-ignored), hash, kind tag, is_present, `__post_init__`, `__lt__` (kind-ignored), `__contains__`, startswith.
- **One integration test** that round-trips through heap store → heap load with `FieldKind.INDEX` and `FieldKind.SPECIAL` to prove tagged path works end-to-end.

## What This Does NOT Cover

- **SymbolTable/FunctionRegistry migration (9adr):** `ClassInfo.fields`, `resolve_field()`, etc. still use str keys. Follow-up P4 issue.
- **LoadFieldIndirect/StoreFieldIndirect instruction fields:** Use `name_reg: Register` for dynamic names — no `field_name` field to migrate. But their handlers DO wrap runtime values at the boundary (see Construction Sites above).
- **FuncName (cnz9):** Separate domain type for CallFunction.func_name, CallMethod.method_name.
- **Address domain type (v217):** HeapWrite.obj_addr, Pointer.base, NewObject.addr, vm.heap keys.
- **Indirect handler impedance mismatch (mmdt):** Runtime string → FieldName wrapping at LoadFieldIndirect/StoreIndirect boundaries. Analysis filed; may not need fixing.
