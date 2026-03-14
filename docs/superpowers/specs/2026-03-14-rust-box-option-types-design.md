# Rust Box<T> and Option<T> Proper Type Representation

## Problem

The Rust frontend's linked list Rosetta test returns `SymbolicValue` instead of a
concrete result because `Box::new(n2)` and `Some(Box::new(n3))` are not properly
modeled. The VM has no class definitions for `Box` or `Option`, so constructor calls
fall through to symbolic resolution.

**Tracked as:** red-dragon-62g

## Design Decisions

### 1. Prelude class definitions

The Rust frontend **always emits** IR class definitions for `Box` and `Option` before
user code. These are emitted at the top of the IR stream, before any user-code
instructions, using the same `LABEL class:X` / `LABEL end_class:X` structure as
regular class definitions.

The prelude classes are equivalent to:

```python
class Box:
    def __init__(self, value):
        self.value = value

class Option:
    def __init__(self, value):
        self.value = value

    def unwrap(self):
        return self.value

    def as_ref(self):
        return self
```

`as_ref()` is included in the class body so that `opt.as_ref().unwrap()` chains
resolve through normal method dispatch (identity in our VM since everything is
reference-based).

### 2. Option is a single class

`Option` is one class, not separate `Some`/`None` classes. `Some(x)` lowers to
`Option(x)`. Rust's `None` literal maps to the existing VM `None` value.

### 3. ParameterizedType in TypeExpr

Both `Box` and `Option` are represented as `ParameterizedType` in the type system:
- `Box::new(n3)` where `n3: Node` produces `ParameterizedType("Box", (ScalarType("Node"),))`
- `Some(Box::new(n3))` produces `ParameterizedType("Option", (ParameterizedType("Box", (ScalarType("Node"),)),))`

### 4. HeapObject.type_hint becomes TypeExpr

`HeapObject.type_hint` changes from `str | None` to `TypeExpr` (default `UNKNOWN`).
This allows runtime objects to carry full parameterized type information.

Backward compatibility:
- `TypeExpr.__eq__` string compatibility means existing `type_hint == "Node"` checks
  continue to work.
- `UnknownType.__bool__` returns `False`, so existing `if type_hint:` guards work
  identically to the old `if type_hint is not None:` pattern.
- `HeapObject.to_dict()` serialization: use `str(type_hint) or None` to preserve
  the existing JSON shape (`null` for untyped objects, string for typed ones).

Downstream changes:
- `_try_class_constructor_call` in executor: receives the original operand string
  (see Decision 5) and uses `parse_type()` to construct the `TypeExpr`.
- `SymbolicValue.type_hint`: stays `str | None` (no change — symbolic values don't
  need parameterized type tracking, and changing them would require Pydantic-free
  migration)
- `NewObject.type_hint`: stays `str | None` (Pydantic `BaseModel` — `TypeExpr` is
  not Pydantic-serializable, and `NewObject` is only used for LLM state updates
  which don't involve parameterized types)

### 5. Frontend resolves type parameters in CALL_FUNCTION operand

The frontend resolves the type parameter at lowering time and encodes it as a
parameterized type string in the `CALL_FUNCTION` operand. For `Box::new(n3)` where
`n3: Node`:

```
CALL_FUNCTION  operands=["Box[Node]", r_n3]
```

**VM changes in `_handle_call_function`** (executor.py ~line 1134):

The base-name extraction must happen **before the scope lookup** (line 1167-1171):

```python
func_name = inst.operands[0]                               # "Box[Node]"
base_name = func_name.split("[")[0] if "[" in func_name else func_name  # "Box"
arg_regs = inst.operands[1:]
args = [_resolve_binop_operand(vm, a) for a in arg_regs]

# ... builtins check uses base_name ...

# Scope lookup uses base_name, NOT func_name
for f in reversed(vm.call_stack):
    if base_name in f.local_vars:
        func_val = f.local_vars[base_name].value
        break
```

The original `func_name` (with type parameter) must be passed to
`_try_class_constructor_call` so it can construct the `TypeExpr`:

```python
ctor_result = _try_class_constructor_call(
    func_val, args, inst, vm, cfg, registry, current_label,
    type_hint_source=func_name,  # new parameter
    ...
)
```

**VM changes in `_try_class_constructor_call`** (executor.py ~line 977):

Add `type_hint_source: str = ""` parameter. Use it instead of `class_name` for the
HeapObject:

```python
type_hint = parse_type(type_hint_source) if type_hint_source else scalar(class_name)
vm.heap[addr] = HeapObject(type_hint=type_hint)
```

This keeps the string→TypeExpr conversion at the IR boundary (IR is inherently
string-based). Once in the VM, the type is a proper `TypeExpr`.

The existing `CLASS_REF_PATTERN` regex (`\w+` for class name) is unaffected because
the class ref stored in variables is always `<class:Box@block_Box>` (unparameterized).
The type parameter lives only in the `CALL_FUNCTION` operand, not in the class ref.

### 6. Method dispatch via class body

`unwrap()` is defined as a method in the `Option` prelude class body. When called
on an `Option[Box[Node]]` object, normal method dispatch applies.

The return type flows naturally: `unwrap` returns `self.value`, and the `value` field's
`TypedValue` already carries the correct type from construction time (when the
`__init__` stored it via `STORE_FIELD`). No special post-return type propagation is
needed.

### 7. Frontend lowering rules

| Rust syntax | IR lowering |
|---|---|
| `Box::new(expr)` | `CALL_FUNCTION Box[T]` with resolved `T` from expr's type |
| `Some(expr)` | `CALL_FUNCTION Option[T]` with resolved `T` from expr's type |
| `*box_expr` (deref) | `LOAD_FIELD box_expr "value"` |
| `opt.unwrap()` | Normal method call on `Option.unwrap` |
| `opt.as_ref()` | Normal method call on `Option.as_ref` (identity) |
| `None` (in Option context) | Existing `None` literal |

## Scope

**In scope:**
- Prelude IR emission for `Box` and `Option` classes in the Rust frontend
- `HeapObject.type_hint` migration from `str | None` to `TypeExpr`
- VM `_handle_call_function`: base-name extraction before scope lookup, pass
  original operand to constructor call
- VM `_try_class_constructor_call`: new `type_hint_source` parameter, use
  `parse_type()` for HeapObject type_hint
- Frontend lowering of `Box::new`, `Some`, deref, `unwrap`, `as_ref`
- Rosetta linked list producing concrete result for Rust

**Out of scope:**
- `SymbolicValue.type_hint` migration (stays `str | None`)
- `NewObject.type_hint` migration (Pydantic, stays `str | None`)
- Pattern matching on `Option` (separate feature)
- `Result<T, E>` type
- Generic type inference beyond direct constructor argument types
- `ClassTypeDescriptor` metadata (epic red-dragon-k7g)
