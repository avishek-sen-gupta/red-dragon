# TypedValue Migration — Registers and Local Variables

**Date:** 2026-03-12
**Bead:** `red-dragon-gsl.7.3.3`
**Status:** Design approved

## Problem

The VM stores raw Python values (`int`, `str`, `float`, `bool`) in registers and local variables with no type metadata attached. Type information exists in a side-car `TypeEnvironment` but is only consulted for register write coercion in `apply_update`. Operators like BINOP never see type info — they receive raw values via `_resolve_reg` and delegate to Python's native operators. When types are incompatible (Java `"int:" + 42`), Python raises `TypeError`, which the VM catches and degrades to a `SymbolicValue`.

This prevents language-correct operator semantics. Java, C#, Kotlin, Scala, and C++ all auto-stringify non-string operands in string concatenation. The VM cannot implement this without type info at the point of operation.

## Design

### TypedValue Dataclass

A frozen wrapper that pairs a raw value with its `TypeExpr`:

```python
# interpreter/typed_value.py

@dataclass(frozen=True)
class TypedValue:
    value: Any          # int, str, float, bool, SymbolicValue, Pointer, list, etc.
    type: TypeExpr      # ScalarType("Int"), UNKNOWN, UnionType, etc.
```

**Invariants:**
- Every value in `frame.registers` and `frame.local_vars` is a `TypedValue`. No exceptions.
- When the type is not known, use `UNKNOWN`. Never store a raw value.
- `SymbolicValue` and `Pointer` live inside `TypedValue.value` — they are not replaced by `TypedValue`.

**Factory helpers:**

```python
def typed(value: Any, type_expr: TypeExpr = UNKNOWN) -> TypedValue:
    """Wrap a raw value with type info."""
    return TypedValue(value=value, type=type_expr)

def typed_from_runtime(value: Any) -> TypedValue:
    """Wrap a raw value, inferring type from Python runtime type."""
    rt = runtime_type_name(value)
    return TypedValue(value=value, type=scalar(rt) if rt else UNKNOWN)
```

`typed_from_runtime` uses the existing `runtime_type_name` mapping (`int→Int`, `str→String`, `float→Float`, `bool→Bool`). Values with no Python-to-TypeExpr mapping (e.g., `list`, `dict`, `SymbolicValue`, `Pointer`) get `UNKNOWN`.

### Wrapping in apply_update

`apply_update` is the chokepoint where values land in registers and local_vars. It becomes responsible for wrapping raw values into `TypedValue`.

All handlers — including BINOP — produce raw values in `register_writes`. `apply_update` wraps everything uniformly. No handler produces `TypedValue` directly in this iteration. A follow-up issue tracks migrating handlers to produce `TypedValue` directly, at which point `apply_update` will only accept `TypedValue` inputs.

**Registers:**

```python
coerced = _coerce_value(deserialized, reg, type_env, conversion_rules)
# UNKNOWN is falsy — falls through to runtime inference when type_env has no entry
declared_type = type_env.register_types.get(reg, UNKNOWN)
inferred_type = declared_type or typed_from_runtime(coerced).type
frame.registers[reg] = typed(coerced, inferred_type)
```

**Local variables:**

```python
declared_type = type_env.var_types.get(var, UNKNOWN)
inferred_type = declared_type or typed_from_runtime(deserialized).type
frame.local_vars[var] = typed(deserialized, inferred_type)
```

**Closure sync** (in `apply_update`, lines 133-136): when syncing local_vars to `ClosureEnvironment.bindings`, unwrap the `TypedValue`:

```python
# apply_update closure sync path
env.bindings[var] = frame.local_vars[var].value
```

**Closure restore** (in call push path, executor.py): when restoring closure bindings into a new frame's `var_writes`, the raw values from `env.bindings` flow through `apply_update` which wraps them into `TypedValue` using `typed_from_runtime`.

### _resolve_reg Returns TypedValue

`_resolve_reg` returns whatever is in the register — which is now always `TypedValue`. Handlers that haven't been migrated to type-awareness access `.value` to get the raw value. As handlers are migrated (follow-up issue), the `.value` unwrapping moves into the handler's type-aware logic.

### BINOP Coercion Strategy

An injectable, language-specific strategy for pre-operation coercion and result type inference:

```python
# interpreter/binop_coercion.py

class BinopCoercionStrategy(Protocol):
    def coerce(self, op: str, lhs: TypedValue, rhs: TypedValue) -> tuple[Any, Any]:
        """Pre-coerce operands before operator application. Returns raw values.

        Contract: will never be called with SymbolicValue operands — the BINOP
        handler short-circuits symbolic operands before calling coerce().
        """
        ...

    def result_type(self, op: str, lhs: TypedValue, rhs: TypedValue) -> TypeExpr:
        """Infer result type from operator and operand types."""
        ...
```

**`DefaultBinopCoercion`** — no-op coercion, basic result type inference:

- `coerce`: returns `(lhs.value, rhs.value)` unchanged
- `result_type`:
  - Comparison operators (`==`, `!=`, `<`, `>`, `<=`, `>=`) → `Bool`
  - C-family logical operators (`&&`, `||`) → `Bool`
  - Python-style `and`/`or` → `UNKNOWN` (Python semantics: returns one of the operands, not a boolean)
  - `Int + Int` → `Int`, `Float + Float` → `Float`, `Int + Float` → `Float`
  - `String + String` → `String`
  - Concat operators (`..`, `.`) → `String`
  - Otherwise → `UNKNOWN`

**`JavaBinopCoercion`** — extends default for string concatenation:

- `coerce`: if op is `+` and one operand is `String` type while the other is not, stringify the non-string operand
- `result_type`: if either operand is `String` and op is `+` → `String`

Serves as null object: `DefaultBinopCoercion()` as default parameter value on `_handle_binop`.

### BINOP Handler Change

`_handle_binop` is the first handler migrated to read `TypedValue` operands and use the coercion strategy. It produces raw values in `register_writes` — `apply_update` wraps them into `TypedValue`.

The `binop_coercion` parameter arrives via `**kwargs`, extracted the same way as `overload_resolver` — the handler pulls it from kwargs:

```python
def _handle_binop(inst: IRInstruction, vm: VMState, **kwargs: Any) -> ExecutionResult:
    binop_coercion = kwargs.get("binop_coercion", _DEFAULT_BINOP_COERCION)
    oper = inst.operands[0]
    lhs_typed = _resolve_reg(vm, inst.operands[1])  # TypedValue
    rhs_typed = _resolve_reg(vm, inst.operands[2])  # TypedValue

    # Unwrap for special-case checks
    lhs = lhs_typed.value
    rhs = rhs_typed.value

    # --- Pointer arithmetic (early returns, raw values) ---
    # Existing pointer logic unchanged — operates on unwrapped lhs/rhs.
    # Pointer results are raw values in register_writes; apply_update wraps them.
    # e.g.: register_writes={inst.result_reg: diff}  (int)
    #        register_writes={inst.result_reg: result_ptr}  (Pointer)

    # --- Symbolic short-circuit (before coercion) ---
    if _is_symbolic(lhs) or _is_symbolic(rhs):
        lhs_desc = _symbolic_name(lhs)
        rhs_desc = _symbolic_name(rhs)
        sym = vm.fresh_symbolic(hint=f"{lhs_desc} {oper} {rhs_desc}")
        sym.constraints = [f"{lhs_desc} {oper} {rhs_desc}"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym},
                reasoning=f"binop {lhs_desc} {oper} {rhs_desc} → symbolic {sym.name}",
            )
        )

    # --- Coerce and compute ---
    lhs_raw, rhs_raw = binop_coercion.coerce(oper, lhs_typed, rhs_typed)
    result = Operators.eval_binop(oper, lhs_raw, rhs_raw)

    if result is Operators.UNCOMPUTABLE:
        sym = vm.fresh_symbolic(hint=f"{lhs_raw!r} {oper} {rhs_raw!r}")
        sym.constraints = [f"{lhs_raw!r} {oper} {rhs_raw!r}"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym},
                reasoning=f"binop {lhs_raw!r} {oper} {rhs_raw!r} → uncomputable",
            )
        )

    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: result},
            reasoning=f"binop {lhs_raw!r} {oper} {rhs_raw!r} = {result!r}",
        )
    )
```

Note: `SymbolicValue` objects are stored directly (not via `.to_dict()`) in `register_writes`. The `_deserialize_value` path in `apply_update` already handles `SymbolicValue` objects — the `.to_dict()` serialization was a legacy pattern for when values needed JSON-safe transport. With `TypedValue` wrapping, values stay as Python objects throughout.

### UNOP During Transition

`_handle_unop` is not migrated in this iteration. It receives `TypedValue` from `_resolve_reg` and must unwrap via `.value`:

```python
operand = _resolve_reg(vm, inst.operands[1]).value  # unwrap during transition
```

UNOP produces raw values in `register_writes`; `apply_update` wraps them. A follow-up issue adds an injectable `UnopCoercionStrategy`.

### Other Handlers During Transition

All other handlers (`_handle_const`, `_handle_load_var`, `_handle_store_var`, `_handle_load_field`, `_handle_store_field`, `_handle_call_method`, etc.) that read from registers via `_resolve_reg` must unwrap via `.value` during the transition. Each handler accesses `.value` at its entry point and continues with raw values internally. Handlers produce raw values in `register_writes`/`var_writes`/`heap_writes`; `apply_update` handles wrapping.

### Injection Path

Same pattern as `OverloadResolver`. The handler extracts `binop_coercion` from `**kwargs` (same mechanism used for `overload_resolver` and `type_env`):

```
run.py → execute_cfg(binop_coercion=...) → _try_execute_locally(binop_coercion=...)
  → LocalExecutor.execute(...) → handler **kwargs → _handle_binop extracts binop_coercion
```

Constructed in `run.py` based on source language:

```python
binop_coercion = _binop_coercion_for_language(lang)
```

Initially: `DefaultBinopCoercion` for all languages except Java which gets `JavaBinopCoercion`.

### Boundary Handling

During the transition, `TypedValue` lives in registers and local_vars. Heap fields and closures stay raw. Boundaries:

| Direction | Location | Where conversion happens | Rule |
|-----------|----------|--------------------------|------|
| Register → heap write | STORE_FIELD, STORE_INDEX | Handler extracts `.value` before creating `HeapWrite` | Unwrap |
| Heap → register | LOAD_FIELD, LOAD_INDEX | `apply_update` wraps raw heap value when writing to register | Wrap via `typed_from_runtime` |
| Local var → closure | `apply_update` closure sync (vm.py:133-136) | Unwrap: `env.bindings[var] = frame.local_vars[var].value` | Unwrap |
| Closure → local var | Call push in executor.py, closure bindings flow through `var_writes` into `apply_update` | `apply_update` wraps using `typed_from_runtime` | Wrap |
| Register → function arg | CALL_FUNCTION, CALL_METHOD parameter binding | Handler serializes `.value`; callee's `apply_update` wraps using `func_param_types` from type_env | Unwrap then wrap |

## File Layout

### New Files

| File | Contents |
|------|----------|
| `interpreter/typed_value.py` | `TypedValue` dataclass, `typed()`, `typed_from_runtime()` |
| `interpreter/binop_coercion.py` | `BinopCoercionStrategy` protocol, `DefaultBinopCoercion`, `JavaBinopCoercion` |

### Modified Files

| File | Change |
|------|--------|
| `interpreter/vm.py` | `apply_update` wraps all values into `TypedValue`; closure sync unwraps; `_resolve_reg` returns `TypedValue`; `_deserialize_value` handles `SymbolicValue` objects directly (no `.to_dict()`) |
| `interpreter/vm_types.py` | `StackFrame.registers` and `local_vars` type hints updated to `dict[str, TypedValue]` |
| `interpreter/executor.py` | `_handle_binop` extracts `binop_coercion` from `**kwargs`, reads `TypedValue`, uses coercion strategy; `_handle_unop` and all other handlers unwrap `.value` from `_resolve_reg` results; boundary handlers (STORE_FIELD, etc.) unwrap before heap/closure writes |
| `interpreter/run.py` | Construct `BinopCoercionStrategy` per language, thread through `execute_cfg` → `_try_execute_locally` → handler kwargs |

### Test Files

| File | Contents |
|------|----------|
| `tests/unit/test_typed_value.py` | `TypedValue` creation, `typed()`, `typed_from_runtime()`, frozen invariant |
| `tests/unit/test_binop_coercion.py` | `DefaultBinopCoercion` and `JavaBinopCoercion` — coercion and result_type for all operator categories, including `and`/`or` → `UNKNOWN` vs `&&`/`||` → `Bool` |
| `tests/integration/test_typed_value_binop.py` | Full-pipeline tests: Java `String + int` produces string, not SymbolicValue |

## Follow-up Issues

1. **Migrate all executor handlers to produce `TypedValue` directly** — handlers create `TypedValue` in `register_writes`; `apply_update` only accepts `TypedValue` (remove raw-value wrapping path)
2. **UNOP coercion strategy** — injectable `UnopCoercionStrategy` protocol, same pattern as BINOP
3. **Heap fields store `TypedValue`** — extend wrapping to `HeapObject.fields`
4. **Closure bindings store `TypedValue`** — extend wrapping to `ClosureEnvironment.bindings`
5. **Language-specific `BinopCoercionStrategy` implementations** — C#, Kotlin, Scala, C++ string concatenation
6. **Builtins receive `TypedValue` args** — migrate builtins to type-aware signatures

## Design Decisions

- **Uniform wrapping:** Every value is `TypedValue`, even when type is `UNKNOWN`. Consumers never branch on "is this typed or raw?"
- **Frozen dataclass:** Values are immutable. Operations produce new `TypedValue` instances.
- **SymbolicValue and Pointer nest inside TypedValue:** They are values, not replacements for `TypedValue`. `TypedValue(value=SymbolicValue(...), type=UNKNOWN)`.
- **All handlers produce raw values (this iteration):** `apply_update` wraps everything uniformly. No `isinstance(val, TypedValue)` branching. Follow-up issue migrates handlers to produce `TypedValue` directly, then `apply_update` drops the raw-value path.
- **SymbolicValue stored directly, not via `.to_dict()`:** The `.to_dict()` serialization was a legacy pattern. With `TypedValue` wrapping, values stay as Python objects. `_deserialize_value` handles both forms during the transition.
- **Language on strategy, not value:** A Java `Int` and a C# `Int` are the same `TypedValue`. The difference is in the injected `BinopCoercionStrategy`.
- **Registers and local_vars only (this iteration):** Heap fields and closure bindings stay raw. Follow-up issues track extending `TypedValue` to those locations.
- **UNOP deferred:** UNOP coercion strategy is a follow-up issue — cross-type operand mixing is rare for unary operators. During the transition, UNOP unwraps `.value` from `_resolve_reg`.
- **`and`/`or` return `UNKNOWN`, not `Bool`:** Python (and many target languages) `and`/`or` return one of their operands, not a boolean. C-family `&&`/`||` return `Bool`. The `result_type` method distinguishes these.
- **Symbolic short-circuit before coercion:** The BINOP handler checks for symbolic operands and returns a symbolic result *before* calling `binop_coercion.coerce()`. The coercion strategy's `coerce` method is never called with `SymbolicValue` operands.
