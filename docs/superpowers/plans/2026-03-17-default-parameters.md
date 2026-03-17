# Default Parameter Support Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add shared IR infrastructure for default parameter resolution and wire it into the Python frontend as proof of concept, removing 1 of 16 xfail tests.

**Architecture:** A shared `__resolve_default__` IR function is lazily emitted on first use. Each default parameter emits a guard that calls this function with the `arguments` array, positional index, and default value. The function returns the caller-provided argument if present, else the default. Python frontend wires `default_parameter` and `typed_default_parameter` nodes into this system.

**Tech Stack:** Python, tree-sitter, pytest

**Spec:** `docs/superpowers/specs/2026-03-17-default-parameters-design.md`

---

## File Structure

- Create: `interpreter/frontends/common/default_params.py` — `emit_resolve_default_func` + `emit_default_param_guard`
- Modify: `interpreter/frontends/context.py:89-142` — add `_resolve_default_emitted: bool = False` field
- Modify: `interpreter/frontends/python/expressions.py:440-506` — wire default param handling
- Modify: `tests/unit/exercism/exercises/two_fer/solutions/python.py` — add default param
- Modify: `tests/unit/exercism/test_exercism_two_fer.py:151-169` — split Python xfail out
- Create: `tests/unit/test_default_params.py` — unit tests for shared infra
- Create: `tests/integration/test_default_params.py` — integration tests via VM execution

---

### Task 1: Shared `__resolve_default__` IR function + unit tests

Add the shared infrastructure that emits the `__resolve_default__` helper function and per-parameter default guards.

**Files:**
- Create: `interpreter/frontends/common/default_params.py`
- Modify: `interpreter/frontends/context.py:89-142`
- Create: `tests/unit/test_default_params.py`

**Context for implementer:**

The IR uses these opcodes (all already exist in `interpreter/ir.py`):
- `SYMBOLIC` — declares a function parameter
- `DECL_VAR` — declares a variable in current scope
- `STORE_VAR` — reassigns a variable (walks scope chain)
- `CONST` — pushes a constant
- `LOAD_VAR` — loads a variable
- `CALL_FUNCTION` — calls a function: `operands=[func_name, arg1_reg, arg2_reg, ...]`
- `BINOP` — binary operation: `operands=[lhs_reg, operator_str, rhs_reg]`
- `BRANCH_IF` — conditional branch: `operands=[cond_reg]`, `label="true_label,false_label"`
- `BRANCH` — unconditional branch: `label=target`
- `LABEL` — label declaration
- `RETURN` — return value: `operands=[value_reg]`
- `LOAD_INDEX` — index into array: `operands=[array_reg, index_reg]`

`emit_func_ref` is a method on `TreeSitterEmitContext` (`context.py:190-208`). It takes `func_name`, `func_label`, `result_reg` and registers a `FuncRef` in the symbol table.

The `arguments` array is a native Python list injected into every function frame at call time by the VM (`executor.py:1199`). `len` is a builtin function already registered.

- [ ] **Step 1: Add `_resolve_default_emitted` field to context**

In `interpreter/frontends/context.py`, add after line 142 (`_accessor_backing_field: str = ""`):

```python
    # Default parameter resolution helper — lazily emitted
    _resolve_default_emitted: bool = False
```

- [ ] **Step 2: Create `interpreter/frontends/common/default_params.py`**

```python
"""Shared default-parameter IR emission helpers.

Provides a lazily-emitted ``__resolve_default__`` IR function and a
per-parameter guard that calls it to resolve actual-vs-default values.
"""

from __future__ import annotations

from interpreter import constants
from interpreter.frontends.context import TreeSitterEmitContext
from interpreter.ir import Opcode


def emit_resolve_default_func(ctx: TreeSitterEmitContext) -> None:
    """Emit the ``__resolve_default__(arguments_arr, param_index, default_value)``
    IR function exactly once.  Subsequent calls are no-ops.

    The function checks ``len(arguments_arr) > param_index`` and returns
    ``arguments_arr[param_index]`` if the caller supplied the argument,
    otherwise ``default_value``.
    """
    if ctx._resolve_default_emitted:
        return
    ctx._resolve_default_emitted = True

    func_name = "__resolve_default__"
    func_label = ctx.fresh_label(f"{constants.FUNC_LABEL_PREFIX}{func_name}")
    end_label = ctx.fresh_label(f"end_{func_name}")
    provided_label = ctx.fresh_label("default_provided")
    use_default_label = ctx.fresh_label("use_default")

    ctx.emit(Opcode.BRANCH, label=end_label)
    ctx.emit(Opcode.LABEL, label=func_label)

    # param: arguments_arr
    arr_reg = ctx.fresh_reg()
    ctx.emit(Opcode.SYMBOLIC, result_reg=arr_reg, operands=[f"{constants.PARAM_PREFIX}arguments_arr"])
    ctx.emit(Opcode.DECL_VAR, operands=["arguments_arr", arr_reg])

    # param: param_index
    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.SYMBOLIC, result_reg=idx_reg, operands=[f"{constants.PARAM_PREFIX}param_index"])
    ctx.emit(Opcode.DECL_VAR, operands=["param_index", idx_reg])

    # param: default_value
    def_reg = ctx.fresh_reg()
    ctx.emit(Opcode.SYMBOLIC, result_reg=def_reg, operands=[f"{constants.PARAM_PREFIX}default_value"])
    ctx.emit(Opcode.DECL_VAR, operands=["default_value", def_reg])

    # len(arguments_arr)
    load_arr = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=load_arr, operands=["arguments_arr"])
    len_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CALL_FUNCTION, result_reg=len_reg, operands=["len", load_arr])

    # len > param_index?
    load_idx = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=load_idx, operands=["param_index"])
    cmp_reg = ctx.fresh_reg()
    ctx.emit(Opcode.BINOP, result_reg=cmp_reg, operands=[len_reg, ">", load_idx])

    ctx.emit(Opcode.BRANCH_IF, operands=[cmp_reg], label=f"{provided_label},{use_default_label}")

    # True branch: return arguments_arr[param_index]
    ctx.emit(Opcode.LABEL, label=provided_label)
    arr2 = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=arr2, operands=["arguments_arr"])
    idx2 = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=idx2, operands=["param_index"])
    elem_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_INDEX, result_reg=elem_reg, operands=[arr2, idx2])
    ctx.emit(Opcode.RETURN, operands=[elem_reg])

    # False branch: return default_value
    ctx.emit(Opcode.LABEL, label=use_default_label)
    def2 = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=def2, operands=["default_value"])
    ctx.emit(Opcode.RETURN, operands=[def2])

    ctx.emit(Opcode.LABEL, label=end_label)

    ref_reg = ctx.fresh_reg()
    ctx.emit_func_ref(func_name, func_label, result_reg=ref_reg)
    ctx.emit(Opcode.DECL_VAR, operands=[func_name, ref_reg])


def emit_default_param_guard(
    ctx: TreeSitterEmitContext,
    param_name: str,
    param_index: int,
    default_value_node,
) -> None:
    """Emit the per-parameter default resolution guard.

    After the normal ``SYMBOLIC`` + ``DECL_VAR`` for *param_name*, call this
    to emit IR that resolves the parameter to either the caller-provided
    argument or the evaluated default value.

    *param_index* is the absolute positional index (0-based), including
    required params that precede this one.  For ``def f(a, b="x")``,
    ``b`` has ``param_index=1``.

    *default_value_node* is the tree-sitter node for the default expression
    (e.g. the ``string``, ``integer``, or ``call`` node).
    """
    # Ensure __resolve_default__ is available
    emit_resolve_default_func(ctx)

    # Evaluate default value expression
    default_reg = ctx.lower_expr(default_value_node)

    # Load arguments array and param index constant
    args_reg = ctx.fresh_reg()
    ctx.emit(Opcode.LOAD_VAR, result_reg=args_reg, operands=["arguments"])

    idx_reg = ctx.fresh_reg()
    ctx.emit(Opcode.CONST, result_reg=idx_reg, operands=[param_index])

    # Call __resolve_default__(arguments, param_index, default_value)
    result_reg = ctx.fresh_reg()
    ctx.emit(
        Opcode.CALL_FUNCTION,
        result_reg=result_reg,
        operands=["__resolve_default__", args_reg, idx_reg, default_reg],
    )

    # Reassign the parameter variable
    ctx.emit(Opcode.STORE_VAR, operands=[param_name, result_reg])
```

- [ ] **Step 3: Write unit tests for `emit_resolve_default_func`**

Create `tests/unit/test_default_params.py`:

```python
"""Unit tests for default parameter shared IR infrastructure."""

from __future__ import annotations

import pytest

from interpreter.frontends.common.default_params import (
    emit_resolve_default_func,
    emit_default_param_guard,
)
from interpreter.frontends.context import TreeSitterEmitContext, GrammarConstants
from interpreter.frontend_observer import NullFrontendObserver
from interpreter.constants import Language
from interpreter.ir import Opcode


def _make_ctx() -> TreeSitterEmitContext:
    """Create a minimal TreeSitterEmitContext for testing."""
    return TreeSitterEmitContext(
        source=b"",
        language=Language.PYTHON,
        observer=NullFrontendObserver(),
        constants=GrammarConstants(),
    )


class TestEmitResolveDefaultFunc:
    """Tests for emit_resolve_default_func."""

    def test_emits_function_with_correct_label(self):
        ctx = _make_ctx()
        emit_resolve_default_func(ctx)
        labels = [i for i in ctx.instructions if i.opcode == Opcode.LABEL]
        func_labels = [l for l in labels if "func___resolve_default__" in (l.label or "")]
        assert len(func_labels) == 1, f"Expected 1 func label, got {func_labels}"

    def test_emits_three_symbolic_params(self):
        ctx = _make_ctx()
        emit_resolve_default_func(ctx)
        symbolics = [i for i in ctx.instructions if i.opcode == Opcode.SYMBOLIC]
        param_names = [s.operands[0] for s in symbolics]
        assert "param:arguments_arr" in param_names
        assert "param:param_index" in param_names
        assert "param:default_value" in param_names

    def test_emits_branch_if_for_length_check(self):
        ctx = _make_ctx()
        emit_resolve_default_func(ctx)
        branch_ifs = [i for i in ctx.instructions if i.opcode == Opcode.BRANCH_IF]
        assert len(branch_ifs) == 1

    def test_emits_func_ref_in_symbol_table(self):
        ctx = _make_ctx()
        emit_resolve_default_func(ctx)
        func_refs = [
            ref for ref in ctx.func_symbol_table.values()
            if ref.name == "__resolve_default__"
        ]
        assert len(func_refs) == 1

    def test_idempotent_on_second_call(self):
        ctx = _make_ctx()
        emit_resolve_default_func(ctx)
        count_1 = len(ctx.instructions)
        emit_resolve_default_func(ctx)
        count_2 = len(ctx.instructions)
        assert count_1 == count_2, "Second call should be a no-op"

    def test_sets_emitted_flag(self):
        ctx = _make_ctx()
        assert ctx._resolve_default_emitted is False
        emit_resolve_default_func(ctx)
        assert ctx._resolve_default_emitted is True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_default_params.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add interpreter/frontends/context.py interpreter/frontends/common/default_params.py tests/unit/test_default_params.py
git commit -m "feat: add shared __resolve_default__ IR function for default params"
```

---

### Task 2: Python frontend — wire default parameter handling

Connect `default_parameter` and `typed_default_parameter` nodes in the Python frontend to `emit_default_param_guard`.

**Files:**
- Modify: `interpreter/frontends/python/expressions.py:440-506`
- Add to: `tests/unit/test_default_params.py`

**Context for implementer:**

The Python frontend has two code paths for parameter lowering:

1. **Regular functions**: dispatched via `common_decl.lower_function_def` → `common_decl.lower_params` → `common_decl.lower_param`. The common `lower_param` (`common/declarations.py:63-91`) uses `extract_param_name` to get the name but ignores defaults.

2. **Lambdas**: `lower_lambda` (`python/expressions.py:425-461`) → `_lower_python_param` (`python/expressions.py:464-506`). This is Python-specific and also ignores defaults.

For this task, modify `_lower_python_param` to handle defaults. Also modify `lower_lambda` and the Python frontend's function def dispatch to use `_lower_python_param` (which now handles defaults) instead of the common one.

The tree-sitter `default_parameter` node has field `name` (identifier) and field `value` (the default expression). `typed_default_parameter` also has `name`, `type`, and `value` fields.

The `_lower_python_param` function is called from a `for child in params_node.children` loop. The loop iterates ALL children including punctuation (parens, commas). The function returns early for punctuation. The `param_index` counter must only increment when a parameter is actually processed.

- [ ] **Step 1: Write failing unit test for Python default param IR**

Add to `tests/unit/test_default_params.py`:

```python
from interpreter.constants import Language
from interpreter.frontends import create_frontend


def _parse_python(source: str) -> list:
    """Parse Python source and return IR instructions."""
    fe = create_frontend(Language.PYTHON)
    return fe.lower(source.encode())


class TestPythonDefaultParamIR:
    """Tests for Python frontend default parameter IR emission."""

    def test_default_param_emits_resolve_call(self):
        """def f(x='hello') should emit CALL_FUNCTION __resolve_default__."""
        instructions = _parse_python("def f(x='hello'):\n    return x\nf()")
        call_fns = [
            i for i in instructions
            if i.opcode == Opcode.CALL_FUNCTION
            and "__resolve_default__" in str(i.operands[0])
        ]
        assert len(call_fns) >= 1, (
            "Expected at least 1 CALL_FUNCTION __resolve_default__"
        )

    def test_default_param_emits_store_var(self):
        """Default param guard should reassign the param via STORE_VAR."""
        instructions = _parse_python("def f(x='hello'):\n    return x\nf()")
        store_vars = [
            i for i in instructions
            if i.opcode == Opcode.STORE_VAR and i.operands[0] == "x"
        ]
        assert len(store_vars) >= 1, "Expected STORE_VAR x for default resolution"

    def test_typed_default_param_emits_resolve_call(self):
        """def f(x: int = 42) should also emit __resolve_default__."""
        instructions = _parse_python("def f(x: int = 42):\n    return x\nf()")
        call_fns = [
            i for i in instructions
            if i.opcode == Opcode.CALL_FUNCTION
            and "__resolve_default__" in str(i.operands[0])
        ]
        assert len(call_fns) >= 1

    def test_required_param_no_resolve(self):
        """def f(x) should NOT emit __resolve_default__."""
        instructions = _parse_python("def f(x):\n    return x\nf('a')")
        call_fns = [
            i for i in instructions
            if i.opcode == Opcode.CALL_FUNCTION
            and "__resolve_default__" in str(i.operands[0])
        ]
        assert len(call_fns) == 0

    def test_mixed_params_correct_index(self):
        """def f(a, b='x') — b should get param_index=1."""
        instructions = _parse_python("def f(a, b='x'):\n    return b\nf('a')")
        call_fns = [
            i for i in instructions
            if i.opcode == Opcode.CALL_FUNCTION
            and "__resolve_default__" in str(i.operands[0])
        ]
        assert len(call_fns) == 1
        # The param_index constant (1) should appear before the call
        # Find the CONST instruction that loads 1 for the index
        const_1s = [
            i for i in instructions
            if i.opcode == Opcode.CONST and i.operands == [1]
        ]
        assert len(const_1s) >= 1, "Expected CONST 1 for param_index of b"

    def test_lambda_default_param(self):
        """lambda x='hi': x should emit __resolve_default__."""
        instructions = _parse_python("f = lambda x='hi': x\nf()")
        call_fns = [
            i for i in instructions
            if i.opcode == Opcode.CALL_FUNCTION
            and "__resolve_default__" in str(i.operands[0])
        ]
        assert len(call_fns) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_default_params.py::TestPythonDefaultParamIR -v`
Expected: All 6 tests FAIL (no `__resolve_default__` calls emitted yet).

- [ ] **Step 3: Modify `_lower_python_param` to handle defaults**

In `interpreter/frontends/python/expressions.py`, modify `_lower_python_param` (line 464-506).

The current signature is `def _lower_python_param(ctx, child) -> None:`. Change to accept `param_index`:

```python
def _lower_python_param(ctx: TreeSitterEmitContext, child, param_index: int) -> bool:
    """Lower a single Python parameter to SYMBOLIC + DECL_VAR.

    Returns True if a parameter was processed (for index counting),
    False if the child was punctuation or unrecognized.

    *param_index* is the 0-based positional index of this parameter
    (counting only actual params, not punctuation).
    """
    if child.type in (
        PythonNodeType.OPEN_PAREN,
        PythonNodeType.CLOSE_PAREN,
        PythonNodeType.COMMA,
        PythonNodeType.COLON,
    ):
        return False

    default_value_node = None

    if child.type == PythonNodeType.IDENTIFIER:
        pname = ctx.node_text(child)
    elif child.type == PythonNodeType.DEFAULT_PARAMETER:
        pname_node = child.child_by_field_name(ctx.constants.func_name_field)
        if not pname_node:
            return False
        pname = ctx.node_text(pname_node)
        default_value_node = child.child_by_field_name("value")
    elif child.type == PythonNodeType.TYPED_PARAMETER:
        id_node = next(
            (sub for sub in child.children if sub.type == PythonNodeType.IDENTIFIER),
            None,
        )
        if not id_node:
            return False
        pname = ctx.node_text(id_node)
    elif child.type == PythonNodeType.TYPED_DEFAULT_PARAMETER:
        pname_node = child.child_by_field_name(ctx.constants.func_name_field)
        if not pname_node:
            return False
        pname = ctx.node_text(pname_node)
        default_value_node = child.child_by_field_name("value")
    else:
        return False

    ctx.emit(
        Opcode.SYMBOLIC,
        result_reg=ctx.fresh_reg(),
        operands=[f"{constants.PARAM_PREFIX}{pname}"],
        node=child,
    )
    ctx.emit(
        Opcode.DECL_VAR,
        operands=[pname, f"%{ctx.reg_counter - 1}"],
    )

    if default_value_node:
        from interpreter.frontends.common.default_params import emit_default_param_guard
        emit_default_param_guard(ctx, pname, param_index, default_value_node)

    return True
```

- [ ] **Step 4: Update lambda parameter loop to pass index**

In `interpreter/frontends/python/expressions.py`, modify the lambda param loop (line 440-442):

Replace:
```python
    if params_node:
        for child in params_node.children:
            _lower_python_param(ctx, child)
```

With:
```python
    if params_node:
        param_idx = 0
        for child in params_node.children:
            if _lower_python_param(ctx, child, param_idx):
                param_idx += 1
```

- [ ] **Step 5: Add `params_lowerer` parameter to `lower_function_def`**

Python regular functions currently use `common_decl.lower_function_def` which calls `common_decl.lower_params` → `common_decl.lower_param`. The common `lower_param` doesn't handle defaults. Instead of duplicating `lower_function_def`, add a `params_lowerer` parameter.

In `interpreter/frontends/common/declarations.py`, modify `lower_function_def` (line 19) signature and the params call:

Replace:
```python
def lower_function_def(ctx: TreeSitterEmitContext, node) -> None:
```

With:
```python
def lower_function_def(
    ctx: TreeSitterEmitContext,
    node,
    params_lowerer: Callable[[TreeSitterEmitContext, Any], None] = lower_params,
) -> None:
```

Add `from typing import Callable` to the imports at the top of the file (after the existing imports).

Replace line 35-36:
```python
    if params_node:
        lower_params(ctx, params_node)
```

With:
```python
    if params_node:
        params_lowerer(ctx, params_node)
```

Then in `interpreter/frontends/python/expressions.py`, add a `lower_python_params` function and a wrapper:

```python
def lower_python_params(ctx: TreeSitterEmitContext, params_node) -> None:
    """Lower Python function parameters, handling default values."""
    param_idx = 0
    for child in params_node.children:
        if _lower_python_param(ctx, child, param_idx):
            param_idx += 1


def lower_python_function_def(ctx: TreeSitterEmitContext, node) -> None:
    """Lower a Python function definition, handling default parameter values."""
    from interpreter.frontends.common.declarations import lower_function_def
    lower_function_def(ctx, node, params_lowerer=lower_python_params)
```

Then in `interpreter/frontends/python/frontend.py`, change the dispatch (line 111):

Replace:
```python
PythonNodeType.FUNCTION_DEFINITION: common_decl.lower_function_def,
```

With:
```python
PythonNodeType.FUNCTION_DEFINITION: python_expr.lower_python_function_def,
```

And add the import at top of `frontend.py`:
```python
from interpreter.frontends.python import expressions as python_expr
```

- [ ] **Step 6: Run unit tests**

Run: `poetry run python -m pytest tests/unit/test_default_params.py -v`
Expected: All 12 tests PASS (6 from Task 1 + 6 from Task 2).

- [ ] **Step 7: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: 11815 passed, 1 skipped, 26 xfailed.

- [ ] **Step 8: Commit**

```bash
git add interpreter/frontends/common/declarations.py interpreter/frontends/python/expressions.py interpreter/frontends/python/frontend.py tests/unit/test_default_params.py
git commit -m "feat(python): wire default_parameter and typed_default_parameter to __resolve_default__"
```

---

### Task 3: Integration tests — default param execution via VM

Verify that functions with default parameters actually work end-to-end through the VM.

**Files:**
- Create: `tests/integration/test_default_params.py`

**Context for implementer:**

Integration tests use `run()` from `interpreter.run` with `Language.PYTHON` and `unwrap_locals()` from `interpreter.typed_value` to get the final variable values.

- [ ] **Step 1: Write integration tests**

Create `tests/integration/test_default_params.py`:

```python
"""Integration tests for default parameter resolution — end-to-end VM execution."""

from __future__ import annotations

import pytest

from interpreter.constants import Language
from interpreter.run import run
from interpreter.typed_value import unwrap_locals


def _run_python(source: str, max_steps: int = 500) -> tuple:
    """Run a Python program and return (vm, unwrapped local vars)."""
    vm = run(source, language=Language.PYTHON, max_steps=max_steps)
    return vm, unwrap_locals(vm.call_stack[0].local_vars)


class TestPythonDefaultParamExecution:
    """End-to-end default parameter tests via VM execution."""

    def test_string_default_used_when_no_arg(self):
        """def f(name='you') called with no args should use default."""
        _, vars_ = _run_python("""\
def two_fer(name="you"):
    return "One for " + name + ", one for me."

answer = two_fer()""")
        assert vars_["answer"] == "One for you, one for me."

    def test_string_default_overridden_by_arg(self):
        """def f(name='you') called with arg should use the arg."""
        _, vars_ = _run_python("""\
def two_fer(name="you"):
    return "One for " + name + ", one for me."

answer = two_fer("Alice")""")
        assert vars_["answer"] == "One for Alice, one for me."

    def test_integer_default(self):
        """def f(x=42) should use 42 when called with no args."""
        _, vars_ = _run_python("""\
def add_one(x=42):
    return x + 1

answer = add_one()""")
        assert vars_["answer"] == 43

    def test_integer_default_overridden(self):
        """def f(x=42) called with 10 should use 10."""
        _, vars_ = _run_python("""\
def add_one(x=42):
    return x + 1

answer = add_one(10)""")
        assert vars_["answer"] == 11

    def test_mixed_required_and_default(self):
        """def f(a, b='world') — a is required, b has default."""
        _, vars_ = _run_python("""\
def greet(greeting, name="world"):
    return greeting + " " + name

answer = greet("hello")""")
        assert vars_["answer"] == "hello world"

    def test_mixed_required_and_default_both_provided(self):
        """def f(a, b='world') — both provided."""
        _, vars_ = _run_python("""\
def greet(greeting, name="world"):
    return greeting + " " + name

answer = greet("hi", "Alice")""")
        assert vars_["answer"] == "hi Alice"

    def test_multiple_defaults(self):
        """def f(a='x', b='y') — both default."""
        _, vars_ = _run_python("""\
def pair(a="x", b="y"):
    return a + b

answer = pair()""")
        assert vars_["answer"] == "xy"

    def test_multiple_defaults_first_overridden(self):
        """def f(a='x', b='y') — first overridden."""
        _, vars_ = _run_python("""\
def pair(a="x", b="y"):
    return a + b

answer = pair("A")""")
        assert vars_["answer"] == "Ay"

    def test_lambda_default_param(self):
        """lambda x='hi': x should use default when no arg."""
        _, vars_ = _run_python("""\
f = lambda x="hi": x
answer = f()""")
        assert vars_["answer"] == "hi"

    def test_function_without_defaults_unchanged(self):
        """Regression: functions without defaults should still work."""
        _, vars_ = _run_python("""\
def add(a, b):
    return a + b

answer = add(3, 4)""")
        assert vars_["answer"] == 7
```

- [ ] **Step 2: Run integration tests**

Run: `poetry run python -m pytest tests/integration/test_default_params.py -v`
Expected: All 10 tests PASS.

- [ ] **Step 3: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: 11815+ passed, 1 skipped, 26 xfailed (new tests added to the pass count).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_default_params.py
git commit -m "test: add integration tests for Python default parameter execution"
```

---

### Task 4: Two-fer test update — remove Python xfail

Update the Python two-fer solution to use a default parameter and remove the Python-specific xfail.

**Files:**
- Modify: `tests/unit/exercism/exercises/two_fer/solutions/python.py`
- Modify: `tests/unit/exercism/test_exercism_two_fer.py:151-169`

**Context for implementer:**

The current Python two-fer solution (`python.py`) is:
```python
def two_fer(name):
    return "One for " + name + ", one for me."

answer = two_fer("Alice")
```

`TestTwoFerDefaultParameter` (line 151-169) uses a single `@pytest.mark.xfail` on the entire parametrized test. To remove xfail for Python only, we need to either:
- Use a conditional xfail that skips Python, or
- Restructure the parametrize to exclude Python and add a separate non-xfail test for Python

The cleanest approach: keep the parametrize but add a conditional xfail that excludes Python.

- [ ] **Step 1: Update Python solution file**

Replace `tests/unit/exercism/exercises/two_fer/solutions/python.py`:

```python
def two_fer(name="you"):
    return "One for " + name + ", one for me."


answer = two_fer("Alice")
```

- [ ] **Step 2: Update xfail to exclude Python**

In `tests/unit/exercism/test_exercism_two_fer.py`, replace the `TestTwoFerDefaultParameter` class (lines 151-169):

```python
class TestTwoFerDefaultParameter:
    """Verify that calling two_fer() with no arguments uses the default parameter.

    Currently xfail for all languages except Python, which has default param
    support wired into the frontend.
    """

    @pytest.mark.parametrize("lang", sorted(EXECUTABLE_LANGUAGES))
    def test_no_arg_uses_default(self, lang):
        if lang != "python":
            pytest.xfail(
                "VM does not support default parameters for this language yet"
            )
        fn_name = _function_name(lang)
        source = build_program(SOLUTIONS[lang], fn_name, [], lang)
        vm, _stats = execute_for_language(lang, source)
        answer = extract_answer(vm, lang)
        assert answer == "One for you, one for me."
```

- [ ] **Step 3: Run the two-fer tests**

Run: `poetry run python -m pytest tests/unit/exercism/test_exercism_two_fer.py -v`
Expected: Python default param test PASSES. All other languages still xfail. Total xfailed drops from 26 to 25.

- [ ] **Step 4: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass, xfailed = 25 (down from 26).

- [ ] **Step 5: Commit**

```bash
git add tests/unit/exercism/exercises/two_fer/solutions/python.py tests/unit/exercism/test_exercism_two_fer.py
git commit -m "test(python): remove xfail for default parameter — two_fer now uses default"
```

---

### Task 5: Format, full test suite, file issues, push

**Files:**
- All modified files
- `README.md` — update if needed

- [ ] **Step 1: Run Black formatter**

Run: `poetry run python -m black .`

- [ ] **Step 2: Run full test suite**

Run: `poetry run python -m pytest --tb=short -q`
Expected: All tests pass, xfailed = 25.

- [ ] **Step 3: Commit formatting changes (if any)**

```bash
git add -A
git commit -m "style: black formatting"
```

(Skip if no changes.)

- [ ] **Step 4: File issues for remaining language frontends**

File one issue per language for wiring default parameter support:

```bash
bd create --title "Wire default parameter support for JavaScript frontend" --description "Wire default_parameter tree-sitter nodes to emit_default_param_guard in the JavaScript frontend. Shared infra already exists in common/default_params.py."
bd create --title "Wire default parameter support for TypeScript frontend" --description "Wire default_parameter tree-sitter nodes to emit_default_param_guard in the TypeScript frontend."
bd create --title "Wire default parameter support for Ruby frontend" --description "Wire default_parameter tree-sitter nodes to emit_default_param_guard in the Ruby frontend."
bd create --title "Wire default parameter support for Java frontend" --description "Wire default_parameter tree-sitter nodes to emit_default_param_guard in the Java frontend."
bd create --title "Wire default parameter support for C# frontend" --description "Wire default_parameter tree-sitter nodes to emit_default_param_guard in the C# frontend."
bd create --title "Wire default parameter support for C++ frontend" --description "Wire default_parameter tree-sitter nodes to emit_default_param_guard in the C++ frontend."
bd create --title "Wire default parameter support for Kotlin frontend" --description "Wire default_parameter tree-sitter nodes to emit_default_param_guard in the Kotlin frontend."
bd create --title "Wire default parameter support for Scala frontend" --description "Wire default_parameter tree-sitter nodes to emit_default_param_guard in the Scala frontend."
bd create --title "Wire default parameter support for PHP frontend" --description "Wire default_parameter tree-sitter nodes to emit_default_param_guard in the PHP frontend."
bd create --title "Wire default parameter support for Rust frontend" --description "Wire default_parameter tree-sitter nodes to emit_default_param_guard in the Rust frontend."
bd create --title "Wire default parameter support for Lua frontend" --description "Wire default_parameter tree-sitter nodes to emit_default_param_guard in the Lua frontend."
bd create --title "Wire default parameter support for Pascal frontend" --description "Wire default_parameter tree-sitter nodes to emit_default_param_guard in the Pascal frontend."
```

- [ ] **Step 5: Push to main**

```bash
git push origin main
```
