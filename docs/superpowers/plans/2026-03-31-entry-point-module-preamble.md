# Two-Phase Entry Point Execution — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `run(entry_point="main")` is called, execute the module-level preamble first (setting up ClassRefs/FuncRefs in scope), then dispatch into the target function — so constructor calls resolve instead of going symbolic.

**Architecture:** Add `vm: VMState | None` parameter to `execute_cfg` and `execute_cfg_traced`. In `run()`, when `entry_point` is specified and differs from the module entry, execute two phases: (1) module preamble from `cfg.entry`, (2) function dispatch from the looked-up label, reusing the VM.

**Tech Stack:** Python, pytest, interpreter/run.py

**Spec:** `docs/superpowers/specs/2026-03-31-entry-point-module-preamble-design.md`

---

### Task 1: Add `vm` parameter to `execute_cfg`

**Files:**
- Modify: `interpreter/run.py:265-295` (execute_cfg function signature and VM init)
- Test: `tests/unit/test_execute_cfg.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_execute_cfg.py`:

```python
def test_execute_cfg_accepts_prebuilt_vm(self):
    """execute_cfg should reuse a pre-built VM instead of creating a fresh one."""
    source = "x = 42"
    frontend = get_frontend(Language.PYTHON)
    instructions = frontend.lower(source.encode("utf-8"))
    cfg = build_cfg(instructions)
    registry = build_registry(instructions, cfg)

    # Pre-build a VM with a variable already set
    from interpreter.vm.vm import VMState, StackFrame
    from interpreter.func_name import FuncName
    from interpreter.var_name import VarName
    from interpreter.types.typed_value import typed
    from interpreter.types.type_expr import UNKNOWN

    vm = VMState()
    vm.call_stack.append(StackFrame(function_name=FuncName("__main__")))
    vm.current_frame.local_vars[VarName("preexisting")] = typed("hello", UNKNOWN)

    vm_out, stats = execute_cfg(cfg, "entry", registry, vm=vm)

    # The preexisting variable should still be in scope
    assert VarName("preexisting") in vm_out.current_frame.local_vars
    assert vm_out.current_frame.local_vars[VarName("preexisting")].value == "hello"
    # And the new variable from execution should also be there
    assert VarName("x") in vm_out.current_frame.local_vars
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_execute_cfg.py::TestExecuteCfg::test_execute_cfg_accepts_prebuilt_vm -v`

Expected: FAIL — `execute_cfg() got an unexpected keyword argument 'vm'`

- [ ] **Step 3: Add `vm` parameter to `execute_cfg`**

In `interpreter/run.py`, change the `execute_cfg` signature and VM initialization block (lines 265-295):

```python
def execute_cfg(
    cfg: CFG,
    entry_point: str,
    registry: FunctionRegistry,
    config: VMConfig = VMConfig(),
    strategies: ExecutionStrategies = ExecutionStrategies(),
    vm: VMState | None = None,
) -> tuple[VMState, ExecutionStats]:
```

Replace the VM init block (lines 289-291):

```python
    # Old:
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name=FuncName(constants.MAIN_FRAME_NAME)))
    vm.io_provider = config.io_provider

    # New:
    if vm is None:
        vm = VMState()
        vm.call_stack.append(
            StackFrame(function_name=FuncName(constants.MAIN_FRAME_NAME))
        )
        vm.io_provider = config.io_provider
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_execute_cfg.py::TestExecuteCfg::test_execute_cfg_accepts_prebuilt_vm -v`

Expected: PASS

- [ ] **Step 5: Run the full test_execute_cfg suite to check for regressions**

Run: `poetry run python -m pytest tests/unit/test_execute_cfg.py -v`

Expected: All existing tests PASS (they don't pass `vm=`, so the `None` default applies).

- [ ] **Step 6: Commit**

```bash
git add interpreter/run.py tests/unit/test_execute_cfg.py
git commit -m "Add vm parameter to execute_cfg for pre-built VM reuse"
```

---

### Task 2: Add `vm` parameter to `execute_cfg_traced`

**Files:**
- Modify: `interpreter/run.py:415-455` (execute_cfg_traced signature and VM init)
- Test: `tests/unit/test_execute_traced.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_execute_traced.py`:

```python
def test_execute_cfg_traced_accepts_prebuilt_vm(self):
    """execute_cfg_traced should reuse a pre-built VM."""
    source = "x = 42"
    frontend = get_frontend(Language.PYTHON)
    instructions = frontend.lower(source.encode("utf-8"))
    cfg = build_cfg(instructions)
    registry = build_registry(instructions, cfg)

    from interpreter.vm.vm import VMState, StackFrame
    from interpreter.func_name import FuncName
    from interpreter.var_name import VarName
    from interpreter.types.typed_value import typed
    from interpreter.types.type_expr import UNKNOWN

    vm = VMState()
    vm.call_stack.append(StackFrame(function_name=FuncName("__main__")))
    vm.current_frame.local_vars[VarName("preexisting")] = typed("hello", UNKNOWN)

    vm_out, trace = execute_cfg_traced(cfg, "entry", registry, vm=vm)

    assert VarName("preexisting") in vm_out.current_frame.local_vars
    assert vm_out.current_frame.local_vars[VarName("preexisting")].value == "hello"
    assert VarName("x") in vm_out.current_frame.local_vars
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_execute_traced.py::TestExecuteCfgTraced::test_execute_cfg_traced_accepts_prebuilt_vm -v`

Expected: FAIL — `execute_cfg_traced() got an unexpected keyword argument 'vm'`

- [ ] **Step 3: Add `vm` parameter to `execute_cfg_traced`**

In `interpreter/run.py`, change the `execute_cfg_traced` signature and VM init block (lines 415-442):

```python
def execute_cfg_traced(
    cfg: CFG,
    entry_point: str,
    registry: FunctionRegistry,
    config: VMConfig = VMConfig(),
    strategies: ExecutionStrategies = ExecutionStrategies(),
    vm: VMState | None = None,
) -> tuple[VMState, ExecutionTrace]:
```

Replace the VM init block (lines 439-442):

```python
    # Old:
    vm = VMState()
    vm.call_stack.append(StackFrame(function_name=FuncName(constants.MAIN_FRAME_NAME)))
    vm.io_provider = config.io_provider
    initial_state = copy.deepcopy(vm)

    # New:
    if vm is None:
        vm = VMState()
        vm.call_stack.append(
            StackFrame(function_name=FuncName(constants.MAIN_FRAME_NAME))
        )
        vm.io_provider = config.io_provider
    initial_state = copy.deepcopy(vm)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_execute_traced.py::TestExecuteCfgTraced::test_execute_cfg_traced_accepts_prebuilt_vm -v`

Expected: PASS

- [ ] **Step 5: Run the full traced test suite**

Run: `poetry run python -m pytest tests/unit/test_execute_traced.py -v`

Expected: All existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add interpreter/run.py tests/unit/test_execute_traced.py
git commit -m "Add vm parameter to execute_cfg_traced for pre-built VM reuse"
```

---

### Task 3: Implement two-phase dispatch in `run()`

**Files:**
- Modify: `interpreter/run.py:704-736` (the entry point resolution and execution section of `run()`)
- Test: `tests/integration/test_ctor_dispatch_entry_point.py` (already exists with 3 failing tests)

- [ ] **Step 1: Verify the 3 tests still fail**

Run: `poetry run python -m pytest tests/integration/test_ctor_dispatch_entry_point.py -v`

Expected: 3 FAIL, 1 PASS

- [ ] **Step 2: Implement two-phase dispatch in `run()`**

In `interpreter/run.py`, replace the execution section (approximately lines 704-738). The current code is:

```python
    # 4. Pick entry
    entry = _find_entry_point(cfg, entry_point)
    ...
    exec_start = time.perf_counter()
    vm, exec_stats = execute_cfg(cfg, entry, registry, vm_config, strategies)
    vm.data_layout = frontend.data_layout
    stats.execution_time = time.perf_counter() - exec_start
```

Replace with:

```python
    # 4. Pick entry
    entry = _find_entry_point(cfg, entry_point)

    # 4b. Build function registry
    ...  # (keep registry + strategies code unchanged)

    # 5. Execute
    vm_config = VMConfig(
        backend=backend,
        max_steps=max_steps,
        verbose=verbose,
        source_language=lang,
        unresolved_call_strategy=unresolved_call_strategy,
    )
    exec_start = time.perf_counter()

    module_entry = _find_entry_point(cfg, "")
    if entry_point and entry != module_entry:
        # Phase 1: run module preamble to populate ClassRefs/FuncRefs in scope
        preamble_config = VMConfig(
            backend=backend,
            max_steps=max_steps,
            verbose=verbose,
            source_language=lang,
            unresolved_call_strategy=unresolved_call_strategy,
        )
        vm, preamble_stats = execute_cfg(
            cfg, module_entry, registry, preamble_config, strategies
        )

        # Look up entry_point function in scope
        func_label = _resolve_entry_function(vm, entry_point, cfg)

        # Phase 2: dispatch into target function
        vm.call_stack.append(
            StackFrame(
                function_name=FuncName(str(entry_point)),
                return_label=NO_LABEL,
            )
        )
        remaining = max_steps - preamble_stats.steps
        phase2_config = VMConfig(
            backend=backend,
            max_steps=max(remaining, 0),
            verbose=verbose,
            source_language=lang,
            unresolved_call_strategy=unresolved_call_strategy,
        )
        vm, phase2_stats = execute_cfg(
            cfg, func_label, registry, phase2_config, strategies, vm=vm
        )
        exec_stats = ExecutionStats(
            steps=preamble_stats.steps + phase2_stats.steps,
            llm_calls=preamble_stats.llm_calls + phase2_stats.llm_calls,
            final_heap_objects=phase2_stats.final_heap_objects,
            final_symbolic_count=phase2_stats.final_symbolic_count,
            closures_captured=phase2_stats.closures_captured,
        )
    else:
        vm, exec_stats = execute_cfg(cfg, entry, registry, vm_config, strategies)

    vm.data_layout = frontend.data_layout
    stats.execution_time = time.perf_counter() - exec_start
```

- [ ] **Step 3: Add `_resolve_entry_function` helper**

Add this function near `_find_entry_point` in `interpreter/run.py` (around line 174):

```python
def _resolve_entry_function(
    vm: VMState, entry_point: str, cfg: CFG
) -> CodeLabel:
    """Look up an entry_point function in the VM scope after module preamble.

    Checks vm.current_frame.local_vars for a FuncRef or BoundFuncRef matching
    the entry_point name. Falls back to _find_entry_point label matching.
    """
    key = VarName(entry_point)
    if key in vm.current_frame.local_vars:
        val = vm.current_frame.local_vars[key]
        raw = val.value if isinstance(val, TypedValue) else val
        if isinstance(raw, BoundFuncRef):
            return raw.func_ref.label
        if isinstance(raw, FuncRef):
            return raw.label
    return _find_entry_point(cfg, entry_point)
```

This requires adding these imports to the top of `run.py` (check which are already there):

```python
from interpreter.var_name import VarName
from interpreter.types.typed_value import TypedValue
```

`BoundFuncRef` and `FuncRef` are already imported in `run.py`.

- [ ] **Step 4: Run the 3 failing tests**

Run: `poetry run python -m pytest tests/integration/test_ctor_dispatch_entry_point.py -v`

Expected: All 4 PASS

- [ ] **Step 5: Run the full test suite to check for regressions**

Run: `poetry run python -m pytest tests/ -x -q`

Expected: All tests pass (13,162+). No regressions — all existing callers of `run()` either pass no `entry_point` or pass `entry_point=""`, both of which take the single-phase path.

- [ ] **Step 6: Run formatting**

Run: `poetry run python -m black .`

- [ ] **Step 7: Run import linter**

Run: `poetry run lint-imports`

Expected: PASS

- [ ] **Step 8: Commit**

```bash
bd backup
git add interpreter/run.py tests/integration/test_ctor_dispatch_entry_point.py
git commit -m "Implement two-phase execution: module preamble before entry_point dispatch

When entry_point targets a function inside a module, run the module-level
preamble first to populate ClassRefs and FuncRefs in scope, then dispatch
into the target function. This fixes constructor calls going symbolic when
using entry_point='main'.

Fixes: red-dragon-djll"
```

---

### Task 4: Close issue and verify

**Files:** None (housekeeping)

- [ ] **Step 1: Close the issue**

```bash
bd close red-dragon-djll --reason "Two-phase execution implemented: module preamble runs before entry_point dispatch. All 4 constructor tests pass."
```

- [ ] **Step 2: Run full verification gate**

```bash
poetry run python -m black .
poetry run lint-imports
poetry run python -m pytest tests/
```

Expected: All checks pass.

- [ ] **Step 3: Push**

```bash
git push
```
