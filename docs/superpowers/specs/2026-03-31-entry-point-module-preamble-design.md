# Two-Phase Execution: Module Preamble Before Entry Point Dispatch

**Date:** 2026-03-31
**Issue:** red-dragon-djll
**Status:** Design approved

## Problem

When `run(source, entry_point="main")` is called, `execute_cfg` jumps directly to the function label (e.g., `func_main_4`), skipping the module-level IR preamble. The preamble contains `CONST + DECL_VAR` instructions that populate the scope with `ClassRef` and `FuncRef` values. Without these, `_handle_call_ctor` cannot find the class in the scope chain and falls through to symbolic resolution. Every constructor call produces a `SymbolicValue` instead of allocating a heap object and dispatching to `__init__`.

Affects all languages where `entry_point` targets a function inside a module.

## Root Cause

`_handle_call_ctor` (in `interpreter/handlers/calls.py:408-419`) searches the call stack for a `VarName` matching the class name. This variable is set by the module-level `DECL_VAR` instruction (e.g., `decl_var Dog %0` where `%0 = ClassRef(...)`). When `entry_point` skips the preamble, the variable is never set.

The registry already knows about the class (`registry.classes`, `registry.class_methods`), but the handler doesn't consult it — it only checks the runtime scope.

## Design: Two-Phase Execution in `run()`

### Phase 1 — Module Preamble

When `entry_point` is specified and resolves to a label different from the module entry (`cfg.entry`):

1. Call `execute_cfg(cfg, "", registry, config, strategies)` — runs the module-level code from `entry`.
2. The preamble executes all class/function declarations, static initializers, and module-level side effects.
3. Execution stops when the top-level frame returns (`_StopExecution`).
4. The VM now has all `ClassRef` and `FuncRef` values in scope.

### Between Phases — Function Lookup

Look up `entry_point` as a `VarName` in `vm.current_frame.local_vars`:

- `BoundFuncRef` → extract `func_ref.label`
- `FuncRef` → extract `label`
- Not found → fall back to `_find_entry_point(cfg, entry_point)` for backwards compatibility (substring label matching)

### Phase 2 — Function Dispatch

1. Push a new `StackFrame` onto the call stack (so the function's return triggers `_StopExecution`).
2. Call `execute_cfg(cfg, func_label, registry, phase2_config, strategies, vm=vm)` with `max_steps` reduced by preamble steps consumed.
3. The function executes with full class/function scope available.

### Stats Merging

Sum `steps` and `llm_calls` from both phases. Take phase 2's `final_heap_objects`, `final_symbolic_count`, and `closures_captured`.

### No Entry Point / Entry Point Equals Module Entry

Single-phase execution as today. Zero behavior change.

## Changes to `execute_cfg`

Add one optional parameter:

```python
def execute_cfg(
    cfg, entry_point, registry, config, strategies,
    vm: VMState | None = None,
) -> tuple[VMState, ExecutionStats]:
```

When `vm` is provided, skip VM initialization (no fresh `VMState()`, no main frame push, no `io_provider` assignment). Use the passed-in VM as-is. The step loop and all other logic remain identical.

Same parameter added to `execute_cfg_traced` for consistency. Two-phase dispatch only happens in `run()` — neither `execute_cfg` nor `execute_cfg_traced` contain two-phase logic themselves.

## Edge Cases

- **Function not in scope after preamble:** Falls back to `_find_entry_point` label matching. No error.
- **Preamble consumes all `max_steps`:** Phase 2 gets zero remaining steps and returns immediately.
- **Languages without preambles:** Preamble runs a few steps and stops. Negligible overhead.

## Tests

Three failing tests (already written in `tests/integration/test_ctor_dispatch_entry_point.py`):

1. `test_java_constructor_creates_heap_object_when_entering_main_directly` — `new Dog("Buddy")` with `entry_point="main"` produces a `Pointer`, not `SymbolicValue`.
2. `test_java_constructor_runs_init_body` — Constructor body executes: `this.name = n` stores `"Buddy"` in the heap object.
3. `test_java_inner_class_constructor_resolves` — Inner class `Point` resolves when jumping to `main` directly.

One already-passing test:

4. `test_constructor_without_entry_point_works` — Module-top execution continues to work.

## Files Changed

- `interpreter/run.py` — `execute_cfg` gains `vm` parameter; `run()` gains two-phase logic
- `interpreter/run.py` — `execute_cfg_traced` gains `vm` parameter
- `tests/integration/test_ctor_dispatch_entry_point.py` — new test file (already exists with failing tests)
