# Return Value TypedValue Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate `return_value` in StateUpdate from raw serialized values to TypedValue, with three-state Void/None/concrete semantics.

**Architecture:** Add `VOID` to TypeName, migrate `_handle_return` to produce TypedValue directly, simplify `_handle_return_flow` to store TypedValue without deserializing, and extend `materialize_raw_update` to handle raw return values from the LLM path.

**Tech Stack:** Python 3.13+, Pydantic (StateUpdate model), pytest

**Spec:** `docs/superpowers/specs/2026-03-13-return-value-typed-value-migration-design.md`

---

## Chunk 1: Complete migration

### Task 1: Add VOID to TypeName and write unit tests

**Files:**
- Modify: `interpreter/constants.py:105-119` (TypeName enum)
- Create: `tests/unit/test_return_value_typed.py`

**Context:** We need a `VOID` type to distinguish "void function, no return value possible" from "function returned None/null". This is a new entry in the `TypeName` enum.

- [ ] **Step 1: Add VOID to TypeName**

In `interpreter/constants.py`, add `VOID` to the `TypeName` enum after `REGION`:

```python
class TypeName(StrEnum):
    """Canonical type names for the type ontology DAG."""

    ANY = "Any"
    NUMBER = "Number"
    INT = "Int"
    FLOAT = "Float"
    STRING = "String"
    BOOL = "Bool"
    OBJECT = "Object"
    ARRAY = "Array"
    POINTER = "Pointer"
    MAP = "Map"
    TUPLE = "Tuple"
    REGION = "Region"
    VOID = "Void"
```

- [ ] **Step 2: Write unit tests for _handle_return TypedValue production**

Create `tests/unit/test_return_value_typed.py`:

```python
"""Unit tests for return_value TypedValue migration."""

from interpreter.constants import TypeName
from interpreter.ir import IRInstruction, Opcode
from interpreter.executor import _handle_return
from interpreter.type_expr import UNKNOWN, scalar
from interpreter.typed_value import TypedValue, typed, typed_from_runtime
from interpreter.vm_types import VMState, StackFrame


class TestHandleReturnTypedValue:
    """Tests for _handle_return producing TypedValue in return_value."""

    def test_return_with_int_operand(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        vm.current_frame.registers["%0"] = typed(42, scalar(TypeName.INT))
        inst = IRInstruction(opcode=Opcode.RETURN, operands=["%0"])
        result = _handle_return(inst, vm)
        rv = result.update.return_value
        assert isinstance(rv, TypedValue)
        assert rv.value == 42

    def test_return_with_none_operand(self):
        """return None → typed(None, UNKNOWN), distinguishable from Void."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        vm.current_frame.registers["%0"] = typed(None, UNKNOWN)
        inst = IRInstruction(opcode=Opcode.RETURN, operands=["%0"])
        result = _handle_return(inst, vm)
        rv = result.update.return_value
        assert isinstance(rv, TypedValue)
        assert rv.value is None
        assert rv.type == UNKNOWN
        assert rv.type != scalar(TypeName.VOID)

    def test_return_without_operands_is_void(self):
        """RETURN with no operands → typed(None, scalar('Void'))."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        inst = IRInstruction(opcode=Opcode.RETURN, operands=[])
        result = _handle_return(inst, vm)
        rv = result.update.return_value
        assert isinstance(rv, TypedValue)
        assert rv.value is None
        assert rv.type == scalar(TypeName.VOID)

    def test_void_and_none_are_distinguishable(self):
        """Void and None return values have different types."""
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))

        # Void (no operands)
        void_inst = IRInstruction(opcode=Opcode.RETURN, operands=[])
        void_result = _handle_return(void_inst, vm)
        void_rv = void_result.update.return_value

        # None (explicit return None)
        vm.current_frame.registers["%0"] = typed(None, UNKNOWN)
        none_inst = IRInstruction(opcode=Opcode.RETURN, operands=["%0"])
        none_result = _handle_return(none_inst, vm)
        none_rv = none_result.update.return_value

        assert void_rv.type == scalar(TypeName.VOID)
        assert none_rv.type != scalar(TypeName.VOID)
        assert void_rv.type != none_rv.type
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_return_value_typed.py -v`
Expected: FAIL — `_handle_return` still produces raw `_serialize_value(val)`, not TypedValue

- [ ] **Step 4: Implement _handle_return migration**

In `interpreter/executor.py`, change `_handle_return` (line 540):

```python
def _handle_return(inst: IRInstruction, vm: VMState, **kwargs: Any) -> ExecutionResult:
    if inst.operands:
        val = _resolve_reg(vm, inst.operands[0])
        tv = typed_from_runtime(val)
    else:
        tv = typed(None, scalar(constants.TypeName.VOID))
    return ExecutionResult.success(
        StateUpdate(
            return_value=tv,
            call_pop=True,
            reasoning=f"return {tv.value!r}",
        )
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_return_value_typed.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Run full test suite**

Run: `poetry run python -m pytest -x -q`
Expected: All ~11,449 tests pass

- [ ] **Step 7: Format and commit**

```bash
poetry run python -m black .
git add interpreter/constants.py interpreter/executor.py tests/unit/test_return_value_typed.py
git commit -m "feat(typed-value): add VOID type, migrate _handle_return to TypedValue"
```

### Task 2: Migrate _handle_return_flow and extend materialize_raw_update

**Files:**
- Modify: `interpreter/run.py:192-196` (_handle_return_flow)
- Modify: `interpreter/vm.py:140-170` (materialize_raw_update)
- Modify: `tests/unit/test_return_value_typed.py` (add tests)

**Context:** `_handle_return_flow` currently deserializes and wraps the return value. Since `_handle_return` now produces TypedValue, the deserialization is unnecessary for the local path. The LLM path needs `materialize_raw_update` extended to also materialize `return_value`.

- [ ] **Step 1: Add tests for _handle_return_flow and materialize_raw_update**

Add to `tests/unit/test_return_value_typed.py`:

```python
from interpreter.vm import materialize_raw_update, _deserialize_value
from interpreter.vm_types import StateUpdate
from interpreter.identity_conversion_rules import IdentityConversionRules
from interpreter.type_environment import TypeEnvironment
from types import MappingProxyType

_EMPTY_TYPE_ENV = TypeEnvironment(
    register_types=MappingProxyType({}),
    var_types=MappingProxyType({}),
)
_IDENTITY_RULES = IdentityConversionRules()


class TestMaterializeReturnValue:
    """Tests for materialize_raw_update handling return_value."""

    def test_raw_int_return_value_materialized(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        raw = StateUpdate(return_value=42, call_pop=True, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        rv = result.return_value
        assert isinstance(rv, TypedValue)
        assert rv.value == 42
        assert rv.type == scalar(TypeName.INT)

    def test_null_return_value_stays_none(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        raw = StateUpdate(return_value=None, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        assert result.return_value is None

    def test_symbolic_dict_return_value_materialized(self):
        from interpreter.vm_types import SymbolicValue
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        sym_dict = {"__symbolic__": True, "name": "sym_0", "type_hint": "Int"}
        raw = StateUpdate(return_value=sym_dict, call_pop=True, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        rv = result.return_value
        assert isinstance(rv, TypedValue)
        assert isinstance(rv.value, SymbolicValue)
        assert rv.value.name == "sym_0"

    def test_already_typed_return_value_passes_through(self):
        vm = VMState()
        vm.call_stack.append(StackFrame(function_name="main"))
        tv = typed(42, scalar(TypeName.INT))
        raw = StateUpdate(return_value=tv, call_pop=True, reasoning="test")
        result = materialize_raw_update(raw, vm, _EMPTY_TYPE_ENV, _IDENTITY_RULES)
        assert result.return_value is tv
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_return_value_typed.py::TestMaterializeReturnValue -v`
Expected: FAIL — `materialize_raw_update` doesn't touch `return_value` yet

- [ ] **Step 3: Extend materialize_raw_update**

In `interpreter/vm.py`, update `materialize_raw_update` (around line 168-170). Change:

```python
    return raw_update.model_copy(
        update={"register_writes": typed_reg_writes, "var_writes": typed_var_writes}
    )
```

To:

```python
    materialized_rv = raw_update.return_value
    if raw_update.return_value is not None and not isinstance(
        raw_update.return_value, TypedValue
    ):
        deserialized = _deserialize_value(raw_update.return_value, vm)
        materialized_rv = typed_from_runtime(deserialized)

    return raw_update.model_copy(
        update={
            "register_writes": typed_reg_writes,
            "var_writes": typed_var_writes,
            "return_value": materialized_rv,
        }
    )
```

- [ ] **Step 4: Simplify _handle_return_flow**

In `interpreter/run.py`, change lines 194-196:

```python
    # Before:
    if return_frame.result_reg and update.return_value is not None:
        raw = _deserialize_value(update.return_value, vm)
        caller_frame.registers[return_frame.result_reg] = typed_from_runtime(raw)

    # After:
    if return_frame.result_reg and update.return_value is not None:
        caller_frame.registers[return_frame.result_reg] = update.return_value
```

- [ ] **Step 5: Add integration tests**

Create `tests/integration/test_return_value_typed.py`:

```python
"""Integration tests for return_value TypedValue migration — end-to-end execution."""

from __future__ import annotations

from interpreter.constants import Language, TypeName
from interpreter.run import run
from interpreter.type_expr import UNKNOWN, scalar
from interpreter.typed_value import TypedValue, unwrap_locals


def _run_python(source: str, max_steps: int = 200):
    """Run a Python program and return the VM."""
    return run(source, language=Language.PYTHON, max_steps=max_steps)


class TestReturnValueTypedIntegration:
    """End-to-end tests verifying return values flow as TypedValue through the VM."""

    def test_function_returns_int(self):
        """Function returning an int stores TypedValue in caller's register."""
        vm = _run_python("""\
def add(a, b):
    return a + b
result = add(3, 4)
""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["result"] == 7

    def test_function_returns_none(self):
        """Function returning None stores None value (not Void) in caller's register."""
        vm = _run_python("""\
def get_none():
    return None
result = get_none()
""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["result"] is None

    def test_void_function_result_not_used(self):
        """Void function (no return) executes without error; other vars unaffected."""
        vm = _run_python("""\
x = 10
def side_effect():
    pass
side_effect()
y = x + 5
""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["y"] == 15

    def test_function_returns_string(self):
        """Function returning a string stores TypedValue in caller's register."""
        vm = _run_python("""\
def greet(name):
    return "hello " + name
msg = greet("world")
""")
        locals_ = unwrap_locals(vm.call_stack[0].local_vars)
        assert locals_["msg"] == "hello world"
```

- [ ] **Step 6: Run all tests (unit + integration)**

Run: `poetry run python -m pytest tests/unit/test_return_value_typed.py tests/integration/test_return_value_typed.py -v`
Expected: All tests PASS

- [ ] **Step 7: Run full test suite**

Run: `poetry run python -m pytest -x -q`
Expected: All ~11,449 tests pass

- [ ] **Step 8: Format and commit**

```bash
poetry run python -m black .
git add interpreter/vm.py interpreter/run.py tests/unit/test_return_value_typed.py tests/integration/test_return_value_typed.py
git commit -m "feat(typed-value): extend materialize_raw_update for return_value, simplify _handle_return_flow"
```

### Task 3: Clean up unused imports and update README

**Files:**
- Modify: `interpreter/run.py:39-51` (remove unused imports)
- Modify: `README.md`

**Context:** After migrating `_handle_return_flow`, three imports in `run.py` are no longer used: `_deserialize_value` (line 48, was used in `_handle_return_flow`), `_serialize_value` (line 49, already unused), and `typed_from_runtime` (line 51, was used in `_handle_return_flow`). Verify each before removing.

- [ ] **Step 1: Check _deserialize_value usage in run.py**

Run: `grep -n _deserialize_value interpreter/run.py`

If `_deserialize_value` is only in the import line, remove it from the `from interpreter.vm import (...)` block (line 48).

- [ ] **Step 2: Check _serialize_value usage in run.py**

Run: `grep -n _serialize_value interpreter/run.py`

If `_serialize_value` is only in the import line, remove it from the `from interpreter.vm import (...)` block (line 49).

- [ ] **Step 3: Check typed_from_runtime usage in run.py**

Run: `grep -n typed_from_runtime interpreter/run.py`

If `typed_from_runtime` is only in the import line, remove it (line 51: `from interpreter.typed_value import typed_from_runtime`).

- [ ] **Step 4: Update README**

Update `README.md` to reflect the return_value TypedValue migration.

- [ ] **Step 5: Run full test suite**

Run: `poetry run python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 6: Format and commit**

```bash
poetry run python -m black .
git add interpreter/run.py README.md
git commit -m "feat(typed-value): clean up return_value migration imports, update README"
```

### Task 4: Close issue and push

- [ ] **Step 1: Close the Beads issue**

```bash
bd update red-dragon-n9m --status closed
```

- [ ] **Step 2: Push**

```bash
git push origin main
```
