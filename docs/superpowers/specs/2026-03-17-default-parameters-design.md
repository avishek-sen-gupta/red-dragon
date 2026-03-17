# Default Parameter Support — Design Spec

**Issue:** red-dragon xfail cluster — 16 tests in `TestTwoFerDefaultParameter`
**Scope:** Shared IR infrastructure + Python frontend proof of concept
**Date:** 2026-03-17

---

## Problem

The VM does not support default parameter values. When a function is called with fewer arguments than declared parameters, the missing parameters receive `SymbolicValue` instead of a default value. This causes 16 xfail tests (one per language) in `TestTwoFerDefaultParameter`.

Currently, the Python frontend handles `default_parameter` and `typed_default_parameter` tree-sitter nodes by extracting only the parameter name — the default value expression is ignored (`interpreter/frontends/python/expressions.py:476-493`).

## Design

### Approach: Arguments-length guard via shared IR helper

Emit a shared `__resolve_default__` IR function in the program prelude. For each default parameter, emit a call to this function that checks `arguments.length` at runtime and returns either the caller-provided argument or the default value.

### `__resolve_default__` IR function

A small IR function emitted once per program on first use (lazily by `emit_default_param_guard`):

```
BRANCH end___resolve_default__
LABEL func___resolve_default__
  SYMBOLIC %0 param:arguments_arr    ; the function's arguments array
  DECL_VAR arguments_arr %0
  SYMBOLIC %1 param:param_index      ; positional index of this param
  DECL_VAR param_index %1
  SYMBOLIC %2 param:default_value    ; pre-evaluated default value
  DECL_VAR default_value %2

  LOAD_VAR %3 arguments_arr
  CALL_FUNCTION %4 "len" [%3]        ; len(arguments_arr)
  LOAD_VAR %5 param_index
  BINOP %6 %4 ">" %5                 ; len > param_index?
  BRANCH_IF_FALSE %6 use_default
  LOAD_VAR %7 arguments_arr
  LOAD_VAR %8 param_index
  LOAD_INDEX %9 %7 %8                ; arguments_arr[param_index]
  RETURN %9
  LABEL use_default
  LOAD_VAR %10 default_value
  RETURN %10
LABEL end___resolve_default__
emit_func_ref("__resolve_default__", func___resolve_default__)
DECL_VAR __resolve_default__ <func_ref_reg>
```

### Per-default-parameter emission

For each parameter with a default value, the frontend emits:

```
; 1. Normal SYMBOLIC + DECL_VAR for the param (existing behavior)
SYMBOLIC %p param:name
DECL_VAR name %p

; 2. Evaluate the default value expression
CONST %d <default_value>             ; or lower_expr(default_value_node)

; 3. Load arguments array and param index
LOAD_VAR %args arguments
CONST %idx <param_index>

; 4. Call __resolve_default__(arguments, param_index, default_value)
CALL_FUNCTION %result __resolve_default__ [%args, %idx, %d]

; 5. Reassign the parameter variable
STORE_VAR name %result
```

This adds 5 instructions per default parameter. The `SYMBOLIC` + `DECL_VAR` pair is kept so the parameter is declared in the function's scope regardless.

### Shared infrastructure location

New file: `interpreter/frontends/common/default_params.py`

Two public functions:

1. **`emit_resolve_default_func(ctx)`** — Emits the `__resolve_default__` IR function using `emit_func_ref` (consistent with the codebase's `FuncRef` pattern). Called lazily from `emit_default_param_guard` on first use, guarded by `hasattr(ctx, '_resolve_default_emitted')`. Lazy emission avoids modifying all frontend preludes — Rust and Pascal override `_emit_prelude` without calling `super()`.

2. **`emit_default_param_guard(ctx, param_name, param_index, default_value_node)`** — Emits the 5-instruction guard for one default parameter. Evaluates `default_value_node` via `ctx.lower_expr()`, then calls `__resolve_default__`. Reassigns `param_name` with the result via `STORE_VAR`. The `param_index` is the absolute positional index including any required params that precede this default param (e.g., in `def f(a, b="x")`, `b` has `param_index=1`).

### Default value evaluation semantics

The default value expression is always evaluated (even when the caller provides the argument). The result is discarded if the argument was provided. This matches JavaScript, Kotlin, and Scala semantics. It diverges from Python's evaluate-once semantics for mutable defaults, but this is an acceptable simplification — the two-fer tests and most real-world defaults use literals or simple expressions where always-evaluate is indistinguishable.

Only literal and simple expressions are in scope for this iteration (string literals, numeric literals, simple calls like `list()`). Complex default expressions referencing forward-declared functions are not targeted.

### Python frontend wiring

In `interpreter/frontends/python/expressions.py`, the `_lower_python_param` function (line 464) currently handles `default_parameter` and `typed_default_parameter` by extracting only the parameter name. After this change:

1. Extract the default value expression node (the named child after `=` — e.g., `string`, `integer`, or `call` node)
2. Track the parameter's positional index (count of parameters seen so far)
3. After emitting the normal `SYMBOLIC` + `DECL_VAR`, call `emit_default_param_guard(ctx, pname, param_index, default_value_node)`

The call sites that iterate parameters are:
- `_lower_python_param` called from the `for child in params_node.children` loop in `_lower_python_function_def` (regular functions)
- Lambda parameter lowering in `_lower_lambda_expr` (line 440-442)

Both call sites need a parameter index counter threaded through. The simplest approach: modify the loop that calls `_lower_python_param` to pass an `enumerate` index.

### Two-fer test changes

1. **Update Python solution** (`tests/unit/exercism/exercises/two_fer/solutions/python.py`):
   - Change `def two_fer(name):` to `def two_fer(name="you"):`

2. **Update test fixture** (`tests/unit/exercism/test_exercism_two_fer.py`):
   - In `TestTwoFerDefaultParameter`, change the xfail for Python from `strict=True` to removing it entirely (Python test should pass)
   - Keep xfail for all other 14 languages (they still need frontend wiring)

3. **`_case_args` unchanged**: The workaround in `_case_args` (substituting `"you"` for `None`) only affects `TestTwoFerExecution`, not `TestTwoFerDefaultParameter`. The default-parameter test class already calls with `[]` args (line 165), so no `_case_args` change is needed.

### What this does NOT change

- No VM changes. The `arguments` array and `len` builtin already exist.
- No registry changes. `__resolve_default__` is a normal function in the symbol table.
- No changes to other language frontends. Each will be wired separately (one issue per language).

## File changes

| File | Action |
|------|--------|
| `interpreter/frontends/common/default_params.py` | Create — shared helper functions |
| `interpreter/frontends/python/expressions.py` | Modify — wire default param handling |
| `tests/unit/exercism/exercises/two_fer/solutions/python.py` | Modify — add default param |
| `tests/unit/exercism/test_exercism_two_fer.py` | Modify — remove Python xfail |
| `tests/unit/test_default_params.py` | Create — unit tests for shared infra |
| `tests/integration/test_default_params.py` | Create — integration tests via VM |

## Deferred work (one issue per language)

File issues for: JavaScript, TypeScript, Ruby, Go, Java, C#, C++, Kotlin, Scala, PHP, Rust, Lua, Pascal. (C excluded — language has no default parameters.)
