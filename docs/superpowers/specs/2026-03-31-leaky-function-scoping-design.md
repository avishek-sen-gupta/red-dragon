# Leaky Function Scoping Strategy for Ruby/PHP/Lua

**Date:** 2026-03-31
**Issue:** red-dragon-crds
**Status:** Approved

## Problem

In Ruby, PHP, and Lua, a `def`/`function` declared inside another function leaks into the global (enclosing module) namespace and remains callable after the outer function returns. The VM uses frame-based scoping: when a `FuncRef`/`BoundFuncRef` is stored in a nested frame's `local_vars`, it disappears when that frame is popped. Calling the inner function from global scope after the outer function has returned produces a `SymbolicValue` instead of a concrete result.

Three xfail tests in `tests/unit/rosetta/test_rosetta_nested_functions.py::TestNestedFunctionLeakyScoping::test_inner_leaks_outside_outer` document this gap.

## Chosen Approach

Add an injectable `FunctionScopingStrategy` to `ExecutionStrategies`. The default strategy (`LocalFunctionScopingStrategy`) preserves current behaviour — writes only to the current frame. The leaky strategy (`GlobalLeakFunctionScopingStrategy`) additionally writes to the global frame (`vm.call_stack[0]`) when inside a nested frame.

This follows the exact same pattern as the existing `FieldFallbackStrategy` and `BinopCoercionStrategy` per-language injectables.

## Components

### New file: `interpreter/vm/function_scoping.py`

```
FunctionScopingStrategy (ABC)
    register_func(name: VarName, value: TypedValue, vm: VMState, current_frame: StackFrame) -> None

LocalFunctionScopingStrategy
    # Default. Writes to current_frame.local_vars only.

GlobalLeakFunctionScopingStrategy
    # Writes to current_frame.local_vars.
    # When len(vm.call_stack) > 1, also writes to vm.call_stack[0].local_vars.
    # No-op duplication guard: when current_frame is already call_stack[0], only one write occurs.
```

Only applied when the value being stored is a `FuncRef` or `BoundFuncRef`. Non-function variables are unaffected.

### `ExecutionStrategies` (`interpreter/run.py`)

Add field:
```python
function_scoping: FunctionScopingStrategy = field(default_factory=LocalFunctionScopingStrategy)
```

### `_write_var_to_frame` (`interpreter/handlers/_common.py`)

Current behaviour: writes directly to `frame.local_vars[name] = value`.

New behaviour: if the value is a `FuncRef` or `BoundFuncRef`, delegate to `ctx.function_scoping.register_func(name, value, vm, frame)`. Otherwise, write directly as before.

The handler context (`HandlerContext` in `interpreter/vm/executor.py`) already carries `ExecutionStrategies`-derived fields; `function_scoping` will be threaded through in the same way as `field_fallback`.

### Per-language helper: `_function_scoping_for_language` (`interpreter/run.py`)

```python
_LEAKY_SCOPING_LANGS = frozenset({Language.RUBY, Language.PHP, Language.LUA})

def _function_scoping_for_language(lang: Language) -> FunctionScopingStrategy:
    if lang in _LEAKY_SCOPING_LANGS:
        return GlobalLeakFunctionScopingStrategy()
    return LocalFunctionScopingStrategy()
```

Called in both `_build_strategies_from_frontend` and `_build_strategies_from_linked`.

### `HandlerContext` (`interpreter/vm/executor.py`)

Add `function_scoping: FunctionScopingStrategy` field, default `LocalFunctionScopingStrategy()`.

## Data Flow

```
STORE_VAR / DECL_VAR
  → _write_var_to_frame(name, value, vm, frame, ctx)
      if isinstance(value, FuncRef | BoundFuncRef):
          ctx.function_scoping.register_func(name, value, vm, frame)
      else:
          frame.local_vars[name] = value
```

`GlobalLeakFunctionScopingStrategy.register_func`:
```
frame.local_vars[name] = value
if len(vm.call_stack) > 1:
    vm.call_stack[0].local_vars[name] = value
```

## Testing

### Unit test (`tests/unit/test_function_scoping_strategy.py`)

- `LocalFunctionScopingStrategy` writes only to current frame, not global frame, at any depth
- `GlobalLeakFunctionScopingStrategy` at depth 1: writes to current frame only (current frame IS global frame — no double-write)
- `GlobalLeakFunctionScopingStrategy` at depth 2: writes to both current frame and global frame
- Non-FuncRef values: `_write_var_to_frame` still writes directly regardless of strategy (strategy is not invoked)

### Integration test

Remove `xfail` from `TestNestedFunctionLeakyScoping::test_inner_leaks_outside_outer` for all three languages (ruby, php, lua). Existing assertions (`leaked == 6`) are correct and require no modification.

## Out of Scope

- Languages where inner functions are genuinely scoped (Python, JavaScript, Java, etc.) — `LocalFunctionScopingStrategy` default covers them.
- Nested-function-calls-nested-function chains — the global write at definition time handles any depth since `inner` is in the global frame from the moment `outer` executes its `def inner` line.
- Class method definitions — these go through `NEW_OBJECT`/`CLASS` IR, not `STORE_VAR` with a `FuncRef`.
