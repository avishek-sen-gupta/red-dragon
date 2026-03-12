# TypedValue Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap all register and local_vars values in `TypedValue(value, type)` and add injectable BINOP coercion for language-correct operator semantics.

**Architecture:** `TypedValue` frozen dataclass wraps every value in registers/local_vars. `apply_update` wraps raw values uniformly. BINOP gets injectable `BinopCoercionStrategy` for pre-operation type coercion. All other handlers unwrap `.value` during the transition.

**Tech Stack:** Python 3.13+, Protocol typing, pytest

**Spec:** `docs/superpowers/specs/2026-03-12-typed-value-migration-design.md`

---

## Chunk 1: TypedValue dataclass and BinopCoercionStrategy

### Task 0: TypedValue dataclass with factory helpers

**Files:**
- Create: `interpreter/typed_value.py`
- Test: `tests/unit/test_typed_value.py`

- [ ] **Step 1: Write tests for TypedValue**

Create `tests/unit/test_typed_value.py`:

```python
"""Unit tests for TypedValue dataclass and factory helpers."""

from interpreter.type_expr import UNKNOWN, ScalarType, scalar
from interpreter.typed_value import TypedValue, typed, typed_from_runtime


class TestTypedValue:
    def test_creation_with_int(self):
        tv = TypedValue(value=42, type=scalar("Int"))
        assert tv.value == 42
        assert tv.type == scalar("Int")

    def test_frozen(self):
        tv = TypedValue(value=42, type=scalar("Int"))
        try:
            tv.value = 99
            assert False, "Should have raised"
        except AttributeError:
            pass

    def test_equality(self):
        a = TypedValue(value=42, type=scalar("Int"))
        b = TypedValue(value=42, type=scalar("Int"))
        assert a == b

    def test_inequality_different_type(self):
        a = TypedValue(value=42, type=scalar("Int"))
        b = TypedValue(value=42, type=scalar("Float"))
        assert a != b

    def test_wraps_symbolic_value(self):
        from interpreter.vm_types import SymbolicValue
        sym = SymbolicValue(name="sym_0", type_hint="Int")
        tv = TypedValue(value=sym, type=UNKNOWN)
        assert tv.value is sym
        assert tv.type == UNKNOWN

    def test_wraps_pointer(self):
        from interpreter.vm_types import Pointer
        ptr = Pointer(base="obj_0", offset=4)
        tv = TypedValue(value=ptr, type=UNKNOWN)
        assert tv.value is ptr

    def test_wraps_none(self):
        tv = TypedValue(value=None, type=UNKNOWN)
        assert tv.value is None
        assert tv.type == UNKNOWN


class TestTypedFactory:
    def test_typed_with_explicit_type(self):
        tv = typed(42, scalar("Int"))
        assert tv.value == 42
        assert tv.type == scalar("Int")

    def test_typed_default_unknown(self):
        tv = typed("hello")
        assert tv.value == "hello"
        assert tv.type == UNKNOWN

    def test_typed_from_runtime_int(self):
        tv = typed_from_runtime(42)
        assert tv.value == 42
        assert tv.type == scalar("Int")

    def test_typed_from_runtime_float(self):
        tv = typed_from_runtime(3.14)
        assert tv.value == 3.14
        assert tv.type == scalar("Float")

    def test_typed_from_runtime_string(self):
        tv = typed_from_runtime("hello")
        assert tv.value == "hello"
        assert tv.type == scalar("String")

    def test_typed_from_runtime_bool(self):
        tv = typed_from_runtime(True)
        assert tv.value is True
        assert tv.type == scalar("Bool")

    def test_typed_from_runtime_unknown_type(self):
        tv = typed_from_runtime([1, 2, 3])
        assert tv.value == [1, 2, 3]
        assert tv.type == UNKNOWN

    def test_typed_from_runtime_none(self):
        tv = typed_from_runtime(None)
        assert tv.value is None
        assert tv.type == UNKNOWN

    def test_typed_from_runtime_symbolic(self):
        from interpreter.vm_types import SymbolicValue
        sym = SymbolicValue(name="sym_0")
        tv = typed_from_runtime(sym)
        assert tv.value is sym
        assert tv.type == UNKNOWN
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_typed_value.py -v`
Expected: FAIL — `interpreter.typed_value` does not exist

- [ ] **Step 3: Implement TypedValue**

Create `interpreter/typed_value.py`:

```python
"""TypedValue — wraps raw Python values with TypeExpr type metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from interpreter.constants import TypeName
from interpreter.type_expr import UNKNOWN, TypeExpr, scalar


_PYTHON_TYPE_TO_TYPE_NAME: dict[type, str] = {
    bool: TypeName.BOOL,
    int: TypeName.INT,
    float: TypeName.FLOAT,
    str: TypeName.STRING,
}


def runtime_type_name(val: Any) -> str:
    """Map a Python runtime value to its canonical TypeName.

    bool must be checked before int because ``isinstance(True, int)`` is True.
    Returns empty string for unrecognised types (no coercion will be applied).
    """
    return _PYTHON_TYPE_TO_TYPE_NAME.get(type(val), "")


@dataclass(frozen=True)
class TypedValue:
    """Immutable wrapper pairing a raw value with its declared/inferred type."""

    value: Any
    type: TypeExpr


def typed(value: Any, type_expr: TypeExpr = UNKNOWN) -> TypedValue:
    """Wrap a raw value with type info."""
    return TypedValue(value=value, type=type_expr)


def typed_from_runtime(value: Any) -> TypedValue:
    """Wrap a raw value, inferring type from Python runtime type.

    Uses runtime_type_name to map int→Int, str→String, float→Float, bool→Bool.
    Values with no mapping (list, dict, SymbolicValue, Pointer, None) get UNKNOWN.
    """
    rt = runtime_type_name(value)
    return TypedValue(value=value, type=scalar(rt) if rt else UNKNOWN)
```

**Important:** `runtime_type_name` and `_PYTHON_TYPE_TO_TYPE_NAME` are relocated here from `interpreter/vm.py` to avoid a circular import (`typed_value.py` → `vm.py` → `typed_value.py`). After creating this file, update `interpreter/vm.py` to import from here:

```python
# In interpreter/vm.py, replace the _PYTHON_TYPE_TO_TYPE_NAME dict and runtime_type_name function with:
from interpreter.typed_value import runtime_type_name  # noqa: F401 — re-exported
```

Also update `interpreter/type_compatibility.py` and `interpreter/ambiguity_handler.py` if they import `runtime_type_name` from `vm.py` — redirect to `typed_value.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_typed_value.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/typed_value.py tests/unit/test_typed_value.py
git commit -m "feat: add TypedValue dataclass with typed() and typed_from_runtime() helpers"
```

---

### Task 1: BinopCoercionStrategy protocol and implementations

**Files:**
- Create: `interpreter/binop_coercion.py`
- Test: `tests/unit/test_binop_coercion.py`

- [ ] **Step 1: Write tests for BinopCoercionStrategy**

Create `tests/unit/test_binop_coercion.py`:

```python
"""Unit tests for BinopCoercionStrategy implementations."""

from interpreter.binop_coercion import DefaultBinopCoercion, JavaBinopCoercion
from interpreter.type_expr import UNKNOWN, scalar
from interpreter.typed_value import typed


class TestDefaultBinopCoercion:
    """DefaultBinopCoercion: no-op coercion, basic result type inference."""

    def setup_method(self):
        self.coercion = DefaultBinopCoercion()

    # --- coerce: no-op ---

    def test_coerce_returns_raw_values(self):
        lhs = typed(42, scalar("Int"))
        rhs = typed(3, scalar("Int"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a == 42
        assert b == 3

    def test_coerce_string_plus_int_no_coercion(self):
        lhs = typed("hello", scalar("String"))
        rhs = typed(42, scalar("Int"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a == "hello"
        assert b == 42

    # --- result_type ---

    def test_result_type_int_plus_int(self):
        lhs = typed(1, scalar("Int"))
        rhs = typed(2, scalar("Int"))
        assert self.coercion.result_type("+", lhs, rhs) == scalar("Int")

    def test_result_type_float_plus_float(self):
        lhs = typed(1.0, scalar("Float"))
        rhs = typed(2.0, scalar("Float"))
        assert self.coercion.result_type("+", lhs, rhs) == scalar("Float")

    def test_result_type_int_plus_float(self):
        lhs = typed(1, scalar("Int"))
        rhs = typed(2.0, scalar("Float"))
        assert self.coercion.result_type("+", lhs, rhs) == scalar("Float")

    def test_result_type_string_plus_string(self):
        lhs = typed("a", scalar("String"))
        rhs = typed("b", scalar("String"))
        assert self.coercion.result_type("+", lhs, rhs) == scalar("String")

    def test_result_type_comparison_returns_bool(self):
        lhs = typed(1, scalar("Int"))
        rhs = typed(2, scalar("Int"))
        for op in ("==", "!=", "<", ">", "<=", ">="):
            assert self.coercion.result_type(op, lhs, rhs) == scalar("Bool")

    def test_result_type_c_family_logical_returns_bool(self):
        lhs = typed(True, scalar("Bool"))
        rhs = typed(False, scalar("Bool"))
        assert self.coercion.result_type("&&", lhs, rhs) == scalar("Bool")
        assert self.coercion.result_type("||", lhs, rhs) == scalar("Bool")

    def test_result_type_python_and_or_returns_unknown(self):
        lhs = typed(3, scalar("Int"))
        rhs = typed(5, scalar("Int"))
        assert self.coercion.result_type("and", lhs, rhs) == UNKNOWN
        assert self.coercion.result_type("or", lhs, rhs) == UNKNOWN

    def test_result_type_concat_returns_string(self):
        lhs = typed("a", scalar("String"))
        rhs = typed("b", scalar("String"))
        assert self.coercion.result_type("..", lhs, rhs) == scalar("String")
        assert self.coercion.result_type(".", lhs, rhs) == scalar("String")

    def test_result_type_unknown_op(self):
        lhs = typed(1, scalar("Int"))
        rhs = typed(2, scalar("Int"))
        assert self.coercion.result_type("???", lhs, rhs) == UNKNOWN

    def test_result_type_int_minus_int(self):
        lhs = typed(5, scalar("Int"))
        rhs = typed(3, scalar("Int"))
        assert self.coercion.result_type("-", lhs, rhs) == scalar("Int")

    def test_result_type_int_times_float(self):
        lhs = typed(2, scalar("Int"))
        rhs = typed(3.0, scalar("Float"))
        assert self.coercion.result_type("*", lhs, rhs) == scalar("Float")

    def test_result_type_unknown_operand_types(self):
        lhs = typed(42, UNKNOWN)
        rhs = typed(3, UNKNOWN)
        assert self.coercion.result_type("+", lhs, rhs) == UNKNOWN


class TestJavaBinopCoercion:
    """JavaBinopCoercion: string concatenation coercion."""

    def setup_method(self):
        self.coercion = JavaBinopCoercion()

    # --- coerce: string + non-string ---

    def test_coerce_string_plus_int_stringifies_int(self):
        lhs = typed("int:", scalar("String"))
        rhs = typed(42, scalar("Int"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a == "int:"
        assert b == "42"

    def test_coerce_int_plus_string_stringifies_int(self):
        lhs = typed(42, scalar("Int"))
        rhs = typed(" items", scalar("String"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a == "42"
        assert b == " items"

    def test_coerce_string_plus_float_stringifies_float(self):
        lhs = typed("val:", scalar("String"))
        rhs = typed(3.14, scalar("Float"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a == "val:"
        assert b == "3.14"

    def test_coerce_string_plus_bool_stringifies_bool(self):
        lhs = typed("flag:", scalar("String"))
        rhs = typed(True, scalar("Bool"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a == "flag:"
        assert b == "True"

    def test_coerce_string_plus_string_no_change(self):
        lhs = typed("hello", scalar("String"))
        rhs = typed(" world", scalar("String"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a == "hello"
        assert b == " world"

    def test_coerce_non_plus_op_no_change(self):
        lhs = typed("hello", scalar("String"))
        rhs = typed(42, scalar("Int"))
        a, b = self.coercion.coerce("-", lhs, rhs)
        assert a == "hello"
        assert b == 42

    def test_coerce_int_plus_int_no_change(self):
        lhs = typed(1, scalar("Int"))
        rhs = typed(2, scalar("Int"))
        a, b = self.coercion.coerce("+", lhs, rhs)
        assert a == 1
        assert b == 2

    # --- result_type: string concat ---

    def test_result_type_string_plus_int(self):
        lhs = typed("x", scalar("String"))
        rhs = typed(42, scalar("Int"))
        assert self.coercion.result_type("+", lhs, rhs) == scalar("String")

    def test_result_type_int_plus_string(self):
        lhs = typed(42, scalar("Int"))
        rhs = typed("x", scalar("String"))
        assert self.coercion.result_type("+", lhs, rhs) == scalar("String")

    def test_result_type_int_plus_int_delegates_to_default(self):
        lhs = typed(1, scalar("Int"))
        rhs = typed(2, scalar("Int"))
        assert self.coercion.result_type("+", lhs, rhs) == scalar("Int")

    def test_result_type_comparison_delegates_to_default(self):
        lhs = typed(1, scalar("Int"))
        rhs = typed(2, scalar("Int"))
        assert self.coercion.result_type("==", lhs, rhs) == scalar("Bool")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_binop_coercion.py -v`
Expected: FAIL — `interpreter.binop_coercion` does not exist

- [ ] **Step 3: Implement BinopCoercionStrategy**

Create `interpreter/binop_coercion.py`:

```python
"""BinopCoercionStrategy — injectable language-specific pre-operation type coercion."""

from __future__ import annotations

from typing import Any, Protocol

from interpreter.type_expr import UNKNOWN, ScalarType, TypeExpr, scalar
from interpreter.typed_value import TypedValue

_COMPARISON_OPS = frozenset({"==", "!=", "<", ">", "<=", ">=", "===", "~="})
_C_FAMILY_LOGICAL_OPS = frozenset({"&&", "||"})
_CONCAT_OPS = frozenset({"..", "."})
_ARITHMETIC_OPS = frozenset({"+", "-", "*", "/", "//", "%", "**", "mod"})
_BITWISE_OPS = frozenset({"&", "|", "^", "~", "<<", ">>"})


class BinopCoercionStrategy(Protocol):
    """Pre-coerce operands and infer result type for binary operations."""

    def coerce(self, op: str, lhs: TypedValue, rhs: TypedValue) -> tuple[Any, Any]:
        """Pre-coerce operands before operator application. Returns raw values.

        Contract: will never be called with SymbolicValue operands — the BINOP
        handler short-circuits symbolic operands before calling coerce().
        """
        ...

    def result_type(self, op: str, lhs: TypedValue, rhs: TypedValue) -> TypeExpr:
        """Infer result type from operator and operand types."""
        ...


def _scalar_name(t: TypeExpr) -> str:
    """Extract scalar name from TypeExpr, or empty string."""
    return t.name if isinstance(t, ScalarType) else ""


def _arithmetic_result(lhs_name: str, rhs_name: str) -> TypeExpr:
    """Infer arithmetic result type from operand type names."""
    if not lhs_name or not rhs_name:
        return UNKNOWN
    if lhs_name == "Float" or rhs_name == "Float":
        return scalar("Float")
    if lhs_name == "Int" and rhs_name == "Int":
        return scalar("Int")
    return UNKNOWN


class DefaultBinopCoercion:
    """No-op coercion with basic result type inference."""

    def coerce(self, op: str, lhs: TypedValue, rhs: TypedValue) -> tuple[Any, Any]:
        return lhs.value, rhs.value

    def result_type(self, op: str, lhs: TypedValue, rhs: TypedValue) -> TypeExpr:
        if op in _COMPARISON_OPS:
            return scalar("Bool")
        if op in _C_FAMILY_LOGICAL_OPS:
            return scalar("Bool")
        if op in _CONCAT_OPS:
            return scalar("String")

        lhs_name = _scalar_name(lhs.type)
        rhs_name = _scalar_name(rhs.type)

        if op in _ARITHMETIC_OPS:
            # String + String → String
            if lhs_name == "String" and rhs_name == "String" and op == "+":
                return scalar("String")
            return _arithmetic_result(lhs_name, rhs_name)
        if op in _BITWISE_OPS:
            return _arithmetic_result(lhs_name, rhs_name)
        # and/or, ?:, in, etc. — unknown
        return UNKNOWN


class JavaBinopCoercion:
    """Java-style coercion: auto-stringify for String + non-String."""

    def __init__(self) -> None:
        self._default = DefaultBinopCoercion()

    def coerce(self, op: str, lhs: TypedValue, rhs: TypedValue) -> tuple[Any, Any]:
        if op == "+":
            lhs_str = _scalar_name(lhs.type) == "String"
            rhs_str = _scalar_name(rhs.type) == "String"
            if lhs_str and not rhs_str:
                return lhs.value, str(rhs.value)
            if rhs_str and not lhs_str:
                return str(lhs.value), rhs.value
        return lhs.value, rhs.value

    def result_type(self, op: str, lhs: TypedValue, rhs: TypedValue) -> TypeExpr:
        if op == "+":
            lhs_name = _scalar_name(lhs.type)
            rhs_name = _scalar_name(rhs.type)
            if lhs_name == "String" or rhs_name == "String":
                return scalar("String")
        return self._default.result_type(op, lhs, rhs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_binop_coercion.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/binop_coercion.py tests/unit/test_binop_coercion.py
git commit -m "feat: add BinopCoercionStrategy protocol with Default and Java implementations"
```

---

## Chunk 2: apply_update wrapping, handler migration, and BINOP threading

### Task 2: apply_update wraps register_writes and var_writes into TypedValue

**Files:**
- Modify: `interpreter/vm.py:61-136` (apply_update)
- Modify: `interpreter/vm.py:184-189` (_resolve_reg)

This is the core change. After this task, all registers and local_vars contain `TypedValue`. Every downstream handler will break until migrated.

- [ ] **Step 1: Modify apply_update to wrap register writes**

In `interpreter/vm.py`, add imports at the top:

```python
from interpreter.typed_value import TypedValue, typed, typed_from_runtime
```

Replace the register writes section (lines 92-98):

```python
# Before:
for reg, val in update.register_writes.items():
    deserialized = _deserialize_value(val, vm)
    frame.registers[reg] = _coerce_value(
        deserialized, reg, type_env, conversion_rules
    )

# After:
for reg, val in update.register_writes.items():
    deserialized = _deserialize_value(val, vm)
    coerced = _coerce_value(deserialized, reg, type_env, conversion_rules)
    # UNKNOWN is falsy — falls through to runtime inference when type_env has no entry
    declared_type = type_env.register_types.get(reg, UNKNOWN)
    inferred_type = declared_type or typed_from_runtime(coerced).type
    frame.registers[reg] = typed(coerced, inferred_type)
```

- [ ] **Step 2: Modify apply_update to wrap var_writes**

Replace the var_writes section (lines 124-136):

```python
# Before:
target_frame = vm.current_frame
for var, val in update.var_writes.items():
    deserialized = _deserialize_value(val, vm)
    alias_ptr = target_frame.var_heap_aliases.get(var)
    if alias_ptr and alias_ptr.base in vm.heap:
        vm.heap[alias_ptr.base].fields[str(alias_ptr.offset)] = deserialized
    else:
        target_frame.local_vars[var] = deserialized
    if target_frame.closure_env_id and var in target_frame.captured_var_names:
        env = vm.closures.get(target_frame.closure_env_id)
        if env:
            env.bindings[var] = deserialized

# After:
target_frame = vm.current_frame
for var, val in update.var_writes.items():
    deserialized = _deserialize_value(val, vm)
    alias_ptr = target_frame.var_heap_aliases.get(var)
    if alias_ptr and alias_ptr.base in vm.heap:
        # Heap stays raw
        vm.heap[alias_ptr.base].fields[str(alias_ptr.offset)] = deserialized
    else:
        declared_type = type_env.var_types.get(var, UNKNOWN)
        inferred_type = declared_type or typed_from_runtime(deserialized).type
        target_frame.local_vars[var] = typed(deserialized, inferred_type)
    if target_frame.closure_env_id and var in target_frame.captured_var_names:
        env = vm.closures.get(target_frame.closure_env_id)
        if env:
            # Closure bindings stay raw
            env.bindings[var] = deserialized
```

- [ ] **Step 3: Do NOT run tests yet — they will fail until handlers are migrated in Steps 4+**

This is expected. Do NOT commit yet — CLAUDE.md requires all tests pass before committing. Tasks 2 and 3 form a single atomic commit.

- [ ] **Step 4: Migrate _resolve_reg and add _resolve_binop_operand**

After wrapping, `_resolve_reg` returns `TypedValue`. All handlers call `_resolve_reg`. Rather than modifying every handler individually, modify `_resolve_reg` to auto-unwrap `.value` so existing handlers work unchanged.

**Strategy:** Modify `_resolve_reg` to return the raw value (`.value`) and add a new `_resolve_binop_operand` that returns the full `TypedValue`. This way, only BINOP (which needs type info) uses `_resolve_binop_operand`; all other handlers continue using `_resolve_reg` unchanged.

- [ ] **Step 1: Modify _resolve_reg to unwrap TypedValue**

In `interpreter/vm.py`, modify `_resolve_reg` (line 184):

```python
# Before:
def _resolve_reg(vm: VMState, operand: str) -> Any:
    """Resolve a register name to its value, or return the operand as-is."""
    if isinstance(operand, str) and operand.startswith("%"):
        frame = vm.current_frame
        return frame.registers.get(operand, operand)
    return operand

# After:
def _resolve_reg(vm: VMState, operand: str) -> Any:
    """Resolve a register name to its raw value, or return the operand as-is.

    Unwraps TypedValue automatically so existing handlers work unchanged.
    """
    if isinstance(operand, str) and operand.startswith("%"):
        frame = vm.current_frame
        val = frame.registers.get(operand, operand)
        if isinstance(val, TypedValue):
            return val.value
        return val
    return operand


def _resolve_binop_operand(vm: VMState, operand: str) -> TypedValue:
    """Resolve a register name to its TypedValue.

    Used by type-aware handlers (BINOP). Falls back to typed_from_runtime
    if the operand is not a register or not wrapped.
    Note: named _resolve_binop_operand to avoid conflict with existing
    _resolve_typed_reg (which does type coercion, different purpose).
    """
    if isinstance(operand, str) and operand.startswith("%"):
        frame = vm.current_frame
        val = frame.registers.get(operand, operand)
        if isinstance(val, TypedValue):
            return val
        return typed_from_runtime(val)
    return typed_from_runtime(operand)
```

- [ ] **Step 5: Modify _handle_load_var to unwrap TypedValue from local_vars**

`_handle_load_var` reads from `frame.local_vars`, which now contains `TypedValue`. Unwrap `.value` before serializing into `register_writes`.

In `interpreter/executor.py`, modify `_handle_load_var` (line 119):

```python
# In _handle_load_var, after finding val in local_vars:
# Before:
        if name in f.local_vars:
            val = f.local_vars[name]
            ...

# After:
        if name in f.local_vars:
            stored = f.local_vars[name]
            val = stored.value if isinstance(stored, TypedValue) else stored
            ...
```

- [ ] **Step 6: Modify _handle_address_of to unwrap TypedValue from local_vars**

`_handle_address_of` (executor.py line 186) reads `f.local_vars[name]` and does `isinstance(current_val, str)` checks and `_heap_addr(current_val)`. A `TypedValue` will fail both. Unwrap:

```python
# Before:
            current_val = f.local_vars[name]

# After:
            stored = f.local_vars[name]
            current_val = stored.value if isinstance(stored, TypedValue) else stored
```

- [ ] **Step 7: Modify _handle_symbolic to unwrap TypedValue from local_vars**

`_handle_symbolic` (executor.py line 246) reads `frame.local_vars[param_name]` and passes to `_serialize_value(val)`. Unwrap:

```python
# Before:
            val = frame.local_vars[param_name]

# After:
            stored = frame.local_vars[param_name]
            val = stored.value if isinstance(stored, TypedValue) else stored
```

- [ ] **Step 8: Modify _handle_new_object to unwrap TypedValue from local_vars**

`_handle_new_object` (executor.py line 270) reads `frame.local_vars[type_hint]` and wraps in `str(...)`. A `TypedValue` will stringify incorrectly. Unwrap:

```python
# Before:
            cr = _parse_class_ref(str(frame.local_vars[type_hint]))

# After:
            stored = frame.local_vars[type_hint]
            raw = stored.value if isinstance(stored, TypedValue) else stored
            cr = _parse_class_ref(str(raw))
```

- [ ] **Step 9: Modify _handle_call_function to unwrap TypedValue from local_vars**

`_handle_call_function` (executor.py line 1117) reads `f.local_vars[func_name]` for function lookup. Unwrap:

```python
# Before:
            func_val = f.local_vars[func_name]

# After:
            stored = f.local_vars[func_name]
            func_val = stored.value if isinstance(stored, TypedValue) else stored
```

- [ ] **Step 10: Modify _handle_const closure capture to unwrap local_vars**

In `_handle_const` (executor.py line 73), closure capture reads `enclosing.local_vars`. These are now `TypedValue`. The closure bindings should store raw values:

```python
# In _handle_const, line 89-91 (sync existing env):
# Before:
                for k, v in enclosing.local_vars.items():
                    if k not in env.bindings:
                        env.bindings[k] = v

# After:
                for k, v in enclosing.local_vars.items():
                    if k not in env.bindings:
                        env.bindings[k] = v.value if isinstance(v, TypedValue) else v

# Line 95 (create new env):
# Before:
                env = ClosureEnvironment(bindings=dict(enclosing.local_vars))

# After:
                env = ClosureEnvironment(
                    bindings={
                        k: v.value if isinstance(v, TypedValue) else v
                        for k, v in enclosing.local_vars.items()
                    }
                )
```

- [ ] **Step 11: Verify no-change handlers**

These handlers read from registers via `_resolve_reg` which auto-unwraps, so no change needed:
- `_handle_store_var` — `_resolve_reg` auto-unwraps, `var_writes` re-wraps in `apply_update`
- `_handle_branch_if` — `_resolve_reg` auto-unwraps
- `_handle_unop` — `_resolve_reg` auto-unwraps (UNOP coercion strategy deferred to follow-up)
- `_handle_call_function`/`_handle_call_method` parameter binding — `_resolve_reg` auto-unwraps args

- [ ] **Step 12: Run full test suite**

Run: `poetry run python -m pytest -x -q`

This is the critical validation. If tests fail, the failures indicate handlers that still need `.value` unwrapping. Debug and fix as needed.

Expected: All ~11,392 tests PASS (some may need fixes)

- [ ] **Step 13: Commit**

```bash
git add interpreter/vm.py interpreter/executor.py
git commit -m "feat: apply_update wraps values into TypedValue, _resolve_reg auto-unwraps, handlers adapted"
```

---

### Task 3: Thread BinopCoercionStrategy through executor and use in BINOP

**Files:**
- Modify: `interpreter/executor.py:606-694` (_handle_binop)
- Modify: `interpreter/executor.py:1355-1380` (LocalExecutor.execute)
- Modify: `interpreter/executor.py:1383-1409` (_try_execute_locally)
- Modify: `interpreter/run.py` (construct and pass strategy)

- [ ] **Step 1: Add binop_coercion parameter to _try_execute_locally and LocalExecutor.execute**

In `interpreter/executor.py`, add import at top:

```python
from interpreter.binop_coercion import BinopCoercionStrategy, DefaultBinopCoercion
```

Add module-level default:

```python
_DEFAULT_BINOP_COERCION = DefaultBinopCoercion()
```

Modify `_try_execute_locally` signature:

```python
def _try_execute_locally(
    inst: IRInstruction,
    vm: VMState,
    cfg: CFG,
    registry: FunctionRegistry,
    current_label: str = "",
    ip: int = 0,
    call_resolver: UnresolvedCallResolver = _DEFAULT_RESOLVER,
    overload_resolver: OverloadResolver = _DEFAULT_OVERLOAD_RESOLVER,
    type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
    binop_coercion: BinopCoercionStrategy = _DEFAULT_BINOP_COERCION,
) -> ExecutionResult:
```

Thread through to `LocalExecutor.execute`:

```python
    return LocalExecutor.execute(
        inst, vm, cfg, registry, current_label, ip, call_resolver,
        overload_resolver=overload_resolver,
        type_env=type_env,
        binop_coercion=binop_coercion,
    )
```

Add `binop_coercion` parameter to `LocalExecutor.execute` and pass it through to handlers via kwargs:

```python
    def execute(
        cls,
        inst: IRInstruction,
        vm: VMState,
        cfg: CFG,
        registry: FunctionRegistry,
        current_label: str = "",
        ip: int = 0,
        call_resolver: UnresolvedCallResolver = _DEFAULT_RESOLVER,
        overload_resolver: OverloadResolver = _DEFAULT_OVERLOAD_RESOLVER,
        type_env: TypeEnvironment = _EMPTY_TYPE_ENV,
        binop_coercion: BinopCoercionStrategy = _DEFAULT_BINOP_COERCION,
    ) -> ExecutionResult:
        handler = cls.DISPATCH.get(inst.opcode)
        if not handler:
            return ExecutionResult.not_handled()
        return handler(
            inst=inst,
            vm=vm,
            cfg=cfg,
            registry=registry,
            current_label=current_label,
            ip=ip,
            call_resolver=call_resolver,
            overload_resolver=overload_resolver,
            type_env=type_env,
            binop_coercion=binop_coercion,
        )
```

- [ ] **Step 2: Modify _handle_binop to use BinopCoercionStrategy**

Replace `_handle_binop` (executor.py line 606):

```python
def _handle_binop(inst: IRInstruction, vm: VMState, **kwargs: Any) -> ExecutionResult:
    binop_coercion = kwargs.get("binop_coercion", _DEFAULT_BINOP_COERCION)
    oper = inst.operands[0]
    lhs_typed = _resolve_binop_operand(vm, inst.operands[1])
    rhs_typed = _resolve_binop_operand(vm, inst.operands[2])

    # Unwrap for special-case checks
    lhs = lhs_typed.value
    rhs = rhs_typed.value

    # Pointer arithmetic: Pointer +/- int or int + Pointer
    # Also handles heap address strings (array decay to pointer in C)
    lhs_ptr = (
        lhs
        if isinstance(lhs, Pointer)
        else (
            Pointer(base=lhs, offset=0)
            if isinstance(lhs, str) and _heap_addr(lhs) and _heap_addr(lhs) in vm.heap
            else None
        )
    )
    rhs_ptr = (
        rhs
        if isinstance(rhs, Pointer)
        else (
            Pointer(base=rhs, offset=0)
            if isinstance(rhs, str) and _heap_addr(rhs) and _heap_addr(rhs) in vm.heap
            else None
        )
    )
    if lhs_ptr and rhs_ptr:
        if oper == "-" and lhs_ptr.base == rhs_ptr.base:
            diff = lhs_ptr.offset - rhs_ptr.offset
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: diff},
                    reasoning=f"pointer diff {lhs!r} - {rhs!r} = {diff}",
                )
            )
        if oper in ("<", ">", "<=", ">=", "==", "!=") and lhs_ptr.base == rhs_ptr.base:
            result = Operators.eval_binop(oper, lhs_ptr.offset, rhs_ptr.offset)
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: result},
                    reasoning=f"pointer cmp {lhs!r} {oper} {rhs!r} = {result!r}",
                )
            )
    if oper in ("+", "-") and (lhs_ptr or rhs_ptr):
        ptr = lhs_ptr or rhs_ptr
        offset_val = rhs if lhs_ptr else lhs
        if isinstance(offset_val, (int, float)):
            new_offset = (
                ptr.offset + int(offset_val)
                if oper == "+" or not lhs_ptr
                else ptr.offset - int(offset_val)
            )
            result_ptr = Pointer(base=ptr.base, offset=new_offset)
            return ExecutionResult.success(
                StateUpdate(
                    register_writes={inst.result_reg: result_ptr},
                    reasoning=f"pointer arith {lhs!r} {oper} {rhs!r} = {result_ptr!r}",
                )
            )

    # Symbolic short-circuit — before coercion
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

    # Coerce and compute
    lhs_raw, rhs_raw = binop_coercion.coerce(oper, lhs_typed, rhs_typed)
    result = Operators.eval_binop(oper, lhs_raw, rhs_raw)

    if result is Operators.UNCOMPUTABLE:
        sym = vm.fresh_symbolic(hint=f"{lhs_raw!r} {oper} {rhs_raw!r}")
        sym.constraints = [f"{lhs_raw!r} {oper} {rhs_raw!r}"]
        return ExecutionResult.success(
            StateUpdate(
                register_writes={inst.result_reg: sym},
                reasoning=f"binop {lhs_raw!r} {oper} {rhs_raw!r} → uncomputable, symbolic {sym.name}",
            )
        )
    return ExecutionResult.success(
        StateUpdate(
            register_writes={inst.result_reg: result},
            reasoning=f"binop {lhs_raw!r} {oper} {rhs_raw!r} = {result!r}",
        )
    )
```

Add import for `_resolve_binop_operand` at top of executor.py:

```python
from interpreter.vm import (
    ...,
    _resolve_binop_operand,
)
```

- [ ] **Step 3: Thread binop_coercion in run.py**

In `interpreter/run.py`, add imports:

```python
from interpreter.binop_coercion import (
    BinopCoercionStrategy,
    DefaultBinopCoercion,
    JavaBinopCoercion,
)
```

Add language-to-strategy mapping function:

```python
def _binop_coercion_for_language(lang: Language) -> BinopCoercionStrategy:
    """Select BinopCoercionStrategy based on source language."""
    _JAVA_LIKE = frozenset({Language.JAVA})
    if lang in _JAVA_LIKE:
        return JavaBinopCoercion()
    return DefaultBinopCoercion()
```

In the `run()` function (around line 596), construct and pass:

```python
binop_coercion = _binop_coercion_for_language(lang)
```

Pass to both `execute_cfg` call sites and `execute_cfg_traced`:

```python
vm, exec_stats = execute_cfg(
    cfg, entry, registry, vm_config,
    type_env=type_env,
    conversion_rules=conversion_rules,
    overload_resolver=overload_resolver,
    binop_coercion=binop_coercion,
)
```

Update `execute_cfg` and `execute_cfg_traced` signatures to accept and forward `binop_coercion`:

```python
def execute_cfg(
    cfg, entry, registry, config,
    ...,
    binop_coercion: BinopCoercionStrategy = _DEFAULT_BINOP_COERCION,
) -> tuple[VMState, ExecutionStats]:
```

Thread to `_try_execute_locally` calls inside both functions.

- [ ] **Step 4: Run full test suite**

Run: `poetry run python -m pytest -x -q`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add interpreter/executor.py interpreter/run.py
git commit -m "feat: thread BinopCoercionStrategy through executor, use in _handle_binop"
```

---

## Chunk 3: Integration tests and cleanup

### Task 4: Integration tests for Java string concatenation

**Files:**
- Create: `tests/integration/test_typed_value_binop.py`

- [ ] **Step 1: Write integration tests**

Create `tests/integration/test_typed_value_binop.py`:

```python
"""Integration tests for TypedValue-aware BINOP with language coercion.

Tests that language-specific BinopCoercionStrategy produces correct results
through the full pipeline.
"""

from interpreter.run import run


class TestJavaStringConcatenation:
    """Java auto-stringifies non-string operands in string + non-string."""

    def test_string_plus_int(self):
        source = """\
class Printer {
    String show(int x) {
        return "int:" + x;
    }
}
Printer p = new Printer();
String result = p.show(42);
"""
        vm = run(source, language="java", max_steps=2000)
        assert vm.call_stack[0].local_vars.get("result").value == "int:42"

    def test_int_plus_string(self):
        source = """\
class Foo {
    String bar(int x) {
        return x + " items";
    }
}
Foo f = new Foo();
String result = f.bar(3);
"""
        vm = run(source, language="java", max_steps=2000)
        assert vm.call_stack[0].local_vars.get("result").value == "3 items"

    def test_string_plus_float(self):
        source = """\
String result = "val:" + 3.14;
"""
        vm = run(source, language="java", max_steps=2000)
        assert vm.call_stack[0].local_vars.get("result").value == "val:3.14"

    def test_string_plus_bool(self):
        source = """\
String result = "flag:" + true;
"""
        vm = run(source, language="java", max_steps=2000)
        assert vm.call_stack[0].local_vars.get("result").value == "flag:True"

    def test_string_concat_no_symbolic(self):
        """String + int should NOT produce SymbolicValue anymore."""
        from interpreter.vm_types import SymbolicValue

        source = """\
String x = "count:" + 5;
"""
        vm = run(source, language="java", max_steps=2000)
        result = vm.call_stack[0].local_vars.get("x")
        assert not isinstance(result.value, SymbolicValue)
        assert result.value == "count:5"


class TestDefaultNonCoercion:
    """Non-Java languages: String + int still produces SymbolicValue (no coercion)."""

    def test_python_string_plus_int_symbolic(self):
        source = """\
x = "count:" + 5
"""
        vm = run(source, language="python", max_steps=2000)
        result = vm.call_stack[0].local_vars.get("x")
        # Python String + int is a TypeError → SymbolicValue
        from interpreter.vm_types import SymbolicValue
        assert isinstance(result.value, SymbolicValue)
```

Note: Tests access `local_vars.get("result").value` because local_vars now stores `TypedValue`. If the test harness changes in the future to expose raw values, these assertions would need updating.

- [ ] **Step 2: Run integration tests**

Run: `poetry run python -m pytest tests/integration/test_typed_value_binop.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest -x -q`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_typed_value_binop.py
git commit -m "test: add integration tests for Java BINOP string concatenation via TypedValue"
```

---

### Task 5: Fix existing tests that read from local_vars or registers

**Files:**
- Modify: `tests/unit/rosetta/conftest.py` (extract_answer, extract_array)
- Modify: Various test files that directly access `vm.call_stack[0].local_vars` or `frame.registers`

After TypedValue wrapping, tests that assert `vm.call_stack[0].local_vars.get("x") == 42` will fail because the value is now `TypedValue(value=42, type=ScalarType("Int"))`.

**Strategy:** Fix the shared test helpers first (`extract_answer`, `extract_array`), then fix individual test assertions.

- [ ] **Step 1: Fix extract_answer in tests/unit/rosetta/conftest.py**

`extract_answer` returns `frame.local_vars[name]` which is now `TypedValue`. Unwrap `.value`:

```python
# Before:
    return frame.local_vars[name]

# After:
    return frame.local_vars[name].value
```

- [ ] **Step 2: Fix extract_array in tests/unit/rosetta/conftest.py**

`extract_array` uses `frame.local_vars[name]` as a heap address. Unwrap `.value` before heap lookup:

```python
# Before:
    heap_addr = frame.local_vars[name]

# After:
    heap_addr = frame.local_vars[name].value
```

- [ ] **Step 3: Add raw_vars helper to tests/conftest.py**

Create `tests/conftest.py` (if it doesn't exist) with a helper for integration tests that read local_vars directly:

```python
from typing import Any

from interpreter.typed_value import TypedValue
from interpreter.vm_types import VMState


def raw_vars(vm: VMState) -> dict[str, Any]:
    """Extract raw values from VM's main frame local_vars, unwrapping TypedValue."""
    return {
        k: v.value for k, v in vm.call_stack[0].local_vars.items()
    }
```

Note: No `isinstance` check — the spec invariant guarantees every value in local_vars is `TypedValue`. No exceptions.

- [ ] **Step 4: Update failing tests to use .value or raw_vars**

Run `poetry run python -m pytest -x -q` and fix tests iteratively. Common patterns:

```python
# Before:
assert vm.call_stack[0].local_vars.get("result") == "hello"

# After (option A — use .value):
assert vm.call_stack[0].local_vars.get("result").value == "hello"

# After (option B — use raw_vars helper):
from tests.conftest import raw_vars
assert raw_vars(vm)["result"] == "hello"
```

The exact set of failing tests will be determined at runtime. Fix each file, run tests, repeat until green.

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest -x -q`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add -u
git commit -m "fix: update test assertions for TypedValue-wrapped local_vars and registers"
```

---

### Task 6: Format, full test suite, final commit

- [ ] **Step 1: Run Black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest -x -q`
Expected: All tests PASS

- [ ] **Step 3: Commit formatting if needed**

```bash
git add -u
git commit -m "style: format TypedValue migration code with Black"
```

---

### Task 7: Create follow-up issues and update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Create follow-up issues in Beads**

```bash
bd create "Migrate all executor handlers to produce TypedValue directly — remove raw-value wrapping from apply_update" --label typed-value
bd create "Add injectable UnopCoercionStrategy protocol, same pattern as BinopCoercionStrategy" --label typed-value
bd create "Extend TypedValue wrapping to HeapObject.fields" --label typed-value
bd create "Extend TypedValue wrapping to ClosureEnvironment.bindings" --label typed-value
bd create "Add BinopCoercionStrategy for C#, Kotlin, Scala, C++ string concatenation" --label typed-value
bd create "Migrate builtins to receive TypedValue args" --label typed-value
```

- [ ] **Step 2: Update README**

Add a brief mention of TypedValue and language-aware operator coercion in the VM capabilities section.

- [ ] **Step 3: Run Black and full test suite**

Run: `poetry run python -m black . && poetry run python -m pytest -x -q`

- [ ] **Step 4: Commit and push**

```bash
git add -u
git commit -m "docs: update README for TypedValue and BINOP coercion support"
git push origin main
```
