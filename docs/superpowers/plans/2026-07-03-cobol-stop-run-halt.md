# COBOL STOP RUN Correct Halt Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make COBOL's `STOP RUN` unconditionally terminate the entire run unit from any point in a `CALL` chain, instead of behaving identically to `GOBACK`/`EXIT PROGRAM` (which correctly return control to the immediate caller).

**Architecture:** Introduce a dedicated `Halt_` IR instruction (`Opcode.HALT`), distinct from the shared `Return_` instruction used by every other function-return path across all 15+ language frontends. `Halt_` carries no value and is never a real "return" — the VM step loop treats it as an unconditional `break` out of execution, bypassing all frame-pop/caller-resume logic. COBOL's `lower_stop_run` emits `Halt_()`; `lower_goback` and `lower_exit_program` are untouched and keep emitting `Return_`.

**Tech Stack:** Python 3.13, pytest (via `poetry run python -m pytest`), the red-dragon IR/VM (`interpreter/`), COBOL frontend (`interpreter/cobol/`).

## Global Constraints

- Design spec: `docs/superpowers/specs/2026-07-03-cobol-stop-run-halt-design.md` — read it before starting; every task below implements a section of it.
- `Halt_` is COBOL-only. No other language frontend may emit it. `GOBACK`/`EXIT PROGRAM` lowering (`lower_goback`, `lower_exit_program` in `interpreter/cobol/lower_arithmetic.py`) must NOT change.
- Follow TDD: write the failing test first, confirm it fails for the right reason, then write the minimal implementation, then confirm green.
- COBOL integration tests require `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar` in the environment. No JAR rebuild is needed for this plan — nothing in `proleap-bridge/` changes.
- Format with `poetry run python -m black .` before the final commit.
- Run the full COBOL suite (`poetry run python -m pytest tests/ -k "cobol or Cobol or COBOL" -q`) and the full suite (`poetry run python -m pytest -q`) before committing — both must be green with zero regressions.
- Single independent commit at the end (per this session's established pattern — do not commit mid-plan).

---

## File Structure

| File | Responsibility |
|---|---|
| `interpreter/ir.py` | Add `Opcode.HALT` enum member. |
| `interpreter/instructions.py` | Add `Halt_` dataclass; add `_halt` flat→typed converter; register it in `_TO_TYPED`. |
| `interpreter/handlers/control_flow.py` | Add `_handle_halt` VM handler. |
| `interpreter/vm/executor.py` | Import `_handle_halt`; register `Opcode.HALT: _handle_halt` in `LocalExecutor.DISPATCH`. |
| `interpreter/run.py` | Two step-loop sites each get an early unconditional `break` when the current instruction is `Halt_`. |
| `interpreter/cfg.py` | Add `Halt_` to the block-start-detection tuple and the no-successors terminator tuple. |
| `interpreter/cobol/lower_arithmetic.py` | `lower_stop_run` emits `Halt_()` instead of `Return_(value_reg=<synthetic zero>)`. |
| `tests/unit/test_typed_instruction_compat.py` | Direct-construction property tests for `Halt_` (opcode, no result_reg, no branch_targets, empty operands) — mirrors existing `Return_` entries. |
| `tests/unit/test_typed_instructions.py` | `TestHaltToTyped` — smoke test that `Opcode.HALT` round-trips through the flat→typed factory. |
| `tests/unit/test_execute_cfg.py` | Unit test: a `Halt_` mid-CFG stops execution immediately; instructions after it never run. |
| `tests/unit/test_execute_traced.py` | Same, for the traced execution loop (`execute_cfg_traced`). |
| `tests/unit/test_cfg.py` | Unit test: a block ending in `Halt_` has no successors (mirrors `Return_`/`Throw_` terminator treatment). |
| `tests/integration/test_cobol_programs.py` | New `TestStopRunTerminatesRunUnit` class (3 tests). |
| `tests/integration/project/test_all_languages_execution.py` | Fix `TestCobolMultiFile::test_call_subprogram` to assert correct `STOP RUN` semantics. |

---

### Task 1: Add the `Halt_` instruction (opcode, dataclass, flat→typed converter)

**Files:**
- Modify: `interpreter/ir.py:47-48` (Opcode enum)
- Modify: `interpreter/instructions.py:900-925` (add `Halt_` dataclass after `Return_`), `interpreter/instructions.py:1496-1501` (add `_halt` converter after `_return`), `interpreter/instructions.py:1629` (register in `_TO_TYPED`)
- Test: `tests/unit/test_typed_instruction_compat.py`, `tests/unit/test_typed_instructions.py`

**Interfaces:**
- Produces: `Opcode.HALT` (enum member); `Halt_` (frozen dataclass, subclass of `InstructionBase`, zero extra fields — `writes() -> None`, `reads() -> []`, `opcode -> Opcode.HALT`, `operands -> []`); `Halt_()` constructible with no arguments (all fields inherited from `InstructionBase` with defaults).

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_typed_instruction_compat.py`, add `Halt_` alongside the existing `Return_`/`Throw_` entries (the class needs importing via the existing `from interpreter.instructions import *` wildcard — no import change needed once `Halt_` exists):

In `TestOpcodeProperty.test_every_typed_class_has_opcode`, add this line right after the `Throw_` entry (currently line 48):
```python
            (Halt_(), Opcode.HALT),
```

In `TestResultRegDefault.test_no_result_types`, add `Halt_()` to the list, right after `Throw_(value_reg="%0"),` (currently line 86):
```python
            Halt_(),
```

In `TestBranchTargetsDefault.test_no_branch_targets`, add `Halt_()` to the list, right after `Return_(),` (currently line 118):
```python
            Halt_(),
```

In `TestOperandsProperty`, add a new test method right after `test_return_value` (currently ends at line 156):
```python
    def test_halt_operands(self):
        assert Halt_().operands == []
```

In `tests/unit/test_typed_instructions.py`, add a new test class right after `TestThrowToTyped` (currently ends at line 400):
```python
class TestHaltToTyped:
    def test_bare(self):
        _assert_to_typed(IRInstruction(opcode=Opcode.HALT, operands=[]))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_typed_instruction_compat.py tests/unit/test_typed_instructions.py -k "halt or Halt" -v`
Expected: FAIL — `NameError: name 'Halt_' is not defined` (compat file) and `AttributeError`/`ValueError: Unknown opcode: HALT` (typed_instructions file, since `Opcode.HALT` doesn't exist yet).

- [ ] **Step 3: Implement `Opcode.HALT`**

In `interpreter/ir.py`, in the `Opcode` enum, add `HALT` right after `THROW` (currently line 48):
```python
    HALT = "HALT"
```

- [ ] **Step 4: Implement the `Halt_` dataclass**

In `interpreter/instructions.py`, add this class immediately after `Return_` (after its closing `operands` property, currently ending at line 925):
```python
@dataclass(frozen=True)
class Halt_(InstructionBase):
    """HALT: unconditionally terminate the entire run unit (COBOL STOP RUN).

    Distinct from Return_ — a halt never returns a value to a caller and is
    invisible to return-type inference (which dispatches on exact type).
    """

    def writes(self) -> StorageIdentifier | None:
        return None

    def reads(self) -> list[StorageIdentifier]:
        return []

    @property
    def opcode(self) -> Opcode:
        return Opcode.HALT

    @property
    def operands(self) -> list[Any]:
        return []
```

- [ ] **Step 5: Implement the `_halt` flat→typed converter and register it**

In `interpreter/instructions.py`, add this function immediately after `_return` (currently ending at line 1500, right before `_throw`):
```python
def _halt(inst: Any) -> Halt_:
    return Halt_(source_location=inst.source_location)
```

In the `_TO_TYPED` dict, add the entry right after `Opcode.RETURN: _return,` (currently line 1629):
```python
    Opcode.HALT: _halt,
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_typed_instruction_compat.py tests/unit/test_typed_instructions.py -v`
Expected: PASS (all tests in both files, including pre-existing ones — this confirms no regression in either file).

---

### Task 2: VM handler and dispatch registration

**Files:**
- Modify: `interpreter/handlers/control_flow.py:82-99` (add `_handle_halt` after `_handle_return`)
- Modify: `interpreter/vm/executor.py:149-156` (import), `interpreter/vm/executor.py:203` (dispatch registration)
- Test: `tests/unit/test_execute_cfg.py`, `tests/unit/test_execute_traced.py`

**Interfaces:**
- Consumes: `Halt_` from Task 1.
- Produces: `_handle_halt(inst, vm, ctx) -> ExecutionResult` — registered under `Opcode.HALT` in `LocalExecutor.DISPATCH`. Executing a `Halt_` produces a `StateUpdate` with no `call_pop`, no `return_value`, no `next_label` — it carries no control-flow signal of its own; Task 3 makes the step loop treat `Halt_` specially.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_execute_cfg.py`, add a new test class at the end of the file:
```python
class TestExecuteCfgHalt:
    def test_halt_stops_execution_before_later_instructions_run(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": CodeLabel("entry")}),
            (Opcode.CONST, {"result_reg": Register("%0"), "operands": [1]}),
            (Opcode.STORE_VAR, {"operands": ["before_halt", "%0"]}),
            (Opcode.HALT, {}),
            (Opcode.CONST, {"result_reg": Register("%1"), "operands": [2]}),
            (Opcode.STORE_VAR, {"operands": ["after_halt", "%1"]}),
            (Opcode.RETURN, {"operands": ["%1"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, stats = execute_cfg(cfg, "entry", registry)

        assert unwrap(vm.current_frame.local_vars[VarName("before_halt")]) == 1
        assert VarName("after_halt") not in vm.current_frame.local_vars
```

In `tests/unit/test_execute_traced.py`, add a new test class at the end of the file:
```python
class TestExecuteCfgTracedHalt:
    def test_halt_stops_trace_before_later_instructions(self):
        instructions = _make_instructions(
            (Opcode.LABEL, {"label": CodeLabel("entry")}),
            (Opcode.CONST, {"result_reg": Register("%0"), "operands": [1]}),
            (Opcode.STORE_VAR, {"operands": ["before_halt", "%0"]}),
            (Opcode.HALT, {}),
            (Opcode.CONST, {"result_reg": Register("%1"), "operands": [2]}),
            (Opcode.STORE_VAR, {"operands": ["after_halt", "%1"]}),
            (Opcode.RETURN, {"operands": ["%1"]}),
        )
        cfg, registry = _build_simple_cfg(instructions)

        vm, trace = execute_cfg_traced(cfg, "entry", registry)

        # CONST, STORE_VAR, HALT executed; the two instructions after HALT never run.
        assert len(trace.steps) == 3
        assert unwrap(vm.current_frame.local_vars[VarName("before_halt")]) == 1
        assert VarName("after_halt") not in vm.current_frame.local_vars
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry run python -m pytest tests/unit/test_execute_cfg.py::TestExecuteCfgHalt tests/unit/test_execute_traced.py::TestExecuteCfgTracedHalt -v`
Expected: FAIL — `ValueError: Unknown opcode: HALT` (no handler registered yet in `LocalExecutor.DISPATCH`, so `_try_execute_locally` cannot dispatch it; depending on the exact failure path this may instead surface as an unhandled-opcode error from the executor — either way, a clear failure, not a silent wrong pass).

- [ ] **Step 3: Implement `_handle_halt`**

In `interpreter/handlers/control_flow.py`, add this function immediately after `_handle_return` (currently ending at line 99, right before `_handle_throw`):
```python
def _handle_halt(
    inst: InstructionBase, vm: VMState, ctx: HandlerContext
) -> ExecutionResult:
    t = inst
    assert isinstance(t, Halt_)
    return ExecutionResult.success(
        StateUpdate(reasoning="STOP RUN — halt run unit")
    )
```

This requires `Halt_` to be importable in this file. In `interpreter/handlers/control_flow.py`, find the `from interpreter.instructions import (` block (currently starting at line 13) and add `Halt_,` to it (alongside wherever `Return_` is already listed).

- [ ] **Step 4: Register the handler**

In `interpreter/vm/executor.py`, find the `from interpreter.handlers.control_flow import (` block (currently starting at line 149) and add `_handle_halt,` to it, alongside `_handle_return,`.

In `LocalExecutor.DISPATCH` (currently starting at line 196), add `Opcode.HALT: _handle_halt,` right after `Opcode.RETURN: _handle_return,` (currently line 203).

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_execute_cfg.py::TestExecuteCfgHalt tests/unit/test_execute_traced.py::TestExecuteCfgTracedHalt -v`
Expected: still FAIL at this point — the handler now executes without error, but the step loop doesn't yet know to stop on `Halt_`, so `after_halt` WILL currently be set (the loop falls through to `ip += 1` and keeps running). This is expected — Task 3 fixes it. Confirm the failure mode is specifically `assert VarName("after_halt") not in ...` failing (not a crash), proving the handler itself works correctly and only the step-loop halting behavior is still missing.

- [ ] **Step 6: Commit is NOT done here** — proceed directly to Task 3; these two tests stay red until Task 3 lands (that's expected and fine — TDD across an adjacent task boundary, both tasks are part of the same review-independent unit before the final commit).

---

### Task 3: Step-loop unconditional halt

**Files:**
- Modify: `interpreter/run.py:444` (main loop), `interpreter/run.py:791` (traced loop)
- Test: (uses the two tests written in Task 2, now made to pass)

**Interfaces:**
- Consumes: `Halt_` (Task 1), `_handle_halt`/dispatch (Task 2).
- Produces: both step loops now `break` immediately and unconditionally when the current instruction is `Halt_`, before any `is_return`/`is_throw`/`_handle_return_flow` logic runs.

- [ ] **Step 1: (tests already written in Task 2 — re-run them to confirm current red state)**

Run: `poetry run python -m pytest tests/unit/test_execute_cfg.py::TestExecuteCfgHalt tests/unit/test_execute_traced.py::TestExecuteCfgTracedHalt -v`
Expected: FAIL (as established at the end of Task 2 — `after_halt` incorrectly gets set).

- [ ] **Step 2: Add `Halt_` to the `run.py` imports**

In `interpreter/run.py`, find the import line (currently line 22):
```python
from interpreter.instructions import InstructionBase, Label_, Return_, Throw_, Suspend
```
Change it to:
```python
from interpreter.instructions import (
    InstructionBase,
    Label_,
    Return_,
    Throw_,
    Halt_,
    Suspend,
)
```

- [ ] **Step 3: Add the early-exit check in the main loop, AFTER `apply_update` runs**

`apply_update` must still run for a `Halt_` instruction (it's a harmless no-op there, since `Halt_`'s `StateUpdate` carries no `var_writes`/`call_pop`/anything else) — only the `_handle_return_flow` dispatch that follows it should be skipped. So the check goes AFTER `apply_update`, not before `is_return` is computed.

In `interpreter/run.py`, the current code (lines 466-478) is:
```python
        else:
            apply_update(
                vm, update, type_env=type_env, conversion_rules=conversion_rules
            )

        if is_return or (is_throw and not is_caught_throw):
            flow = _handle_return_flow(
                vm, cfg, return_frame, update, config.verbose, step
            )
            if isinstance(flow, _StopExecution):
                break
            current_label, ip = flow

        elif update.next_label and update.next_label in cfg.blocks:
            current_label = update.next_label
            ip = 0
        else:
            ip += 1
```
Change the blank line between the `apply_update` `else` block and the `if is_return...` line (currently line 470) to insert a new check, so it reads:
```python
        else:
            apply_update(
                vm, update, type_env=type_env, conversion_rules=conversion_rules
            )

        if isinstance(instruction, Halt_):
            if config.verbose:
                logger.info("[step %d] STOP RUN — halting entire run unit.", step)
            break

        if is_return or (is_throw and not is_caught_throw):
            flow = _handle_return_flow(
                vm, cfg, return_frame, update, config.verbose, step
            )
            if isinstance(flow, _StopExecution):
                break
            current_label, ip = flow

        elif update.next_label and update.next_label in cfg.blocks:
            current_label = update.next_label
            ip = 0
        else:
            ip += 1
```

- [ ] **Step 4: Add the same early-exit check in the traced loop, AFTER `trace_steps.append` runs**

The traced loop must still record a `TraceStep` for the `HALT` instruction itself (the test asserts `len(trace.steps) == 3`, i.e. `CONST`, `STORE_VAR`, `HALT` are all traced) — `apply_update` already runs earlier in this loop (before the trace snapshot), so by the time the trace is appended, `Halt_`'s (empty) update has already been applied. The check goes AFTER the `trace_steps.append(...)` block, BEFORE the `if is_return or is_throw:` dispatch.

In `interpreter/run.py`, the current code (lines 813-826) is:
```python
        # Snapshot the VM state after update
        trace_steps.append(
            TraceStep(
                step_index=len(trace_steps),
                block_label=current_label,
                instruction_index=ip,
                instruction=instruction,
                update=update,
                vm_state=copy.deepcopy(vm),
                used_llm=used_llm,
            )
        )

        if is_return or is_throw:
```
Change the blank line between the `trace_steps.append(...)` block and the `if is_return or is_throw:` line (currently line 825) to insert a new check, so it reads:
```python
        # Snapshot the VM state after update
        trace_steps.append(
            TraceStep(
                step_index=len(trace_steps),
                block_label=current_label,
                instruction_index=ip,
                instruction=instruction,
                update=update,
                vm_state=copy.deepcopy(vm),
                used_llm=used_llm,
            )
        )

        if isinstance(instruction, Halt_):
            if config.verbose:
                logger.info("[step %d] STOP RUN — halting entire run unit.", step)
            break

        if is_return or is_throw:
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `poetry run python -m pytest tests/unit/test_execute_cfg.py::TestExecuteCfgHalt tests/unit/test_execute_traced.py::TestExecuteCfgTracedHalt -v`
Expected: PASS.

- [ ] **Step 6: Run the full unit suite to check for regressions**

Run: `poetry run python -m pytest tests/unit/ -q`
Expected: all pass (no regressions from the import change or the two inserted checks).

---

### Task 4: CFG terminator treatment

**Files:**
- Modify: `interpreter/cfg.py:38` (block-start detection), `interpreter/cfg.py:89` (no-successors check)
- Test: `tests/unit/test_cfg.py`

**Interfaces:**
- Consumes: `Halt_` (Task 1).
- Produces: a basic block ending in `Halt_` has `successors == []`, matching `Return_`/`Throw_` treatment; code textually following a `Halt_` still gets its own (separate, unreachable-by-CFG-edge) block, matching how code after `Return_`/`Throw_` is handled today.

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_cfg.py`, add a new test class at the end of the file:
```python
class TestHaltTerminatesBlock:
    def test_block_ending_in_halt_has_no_successors(self):
        from interpreter.cfg import build_cfg
        from interpreter.ir import IRInstruction, Opcode, CodeLabel
        from interpreter.register import Register

        instructions = [
            IRInstruction(opcode=Opcode.LABEL, label=CodeLabel("entry")),
            IRInstruction(
                opcode=Opcode.CONST, result_reg=Register("%0"), operands=[1]
            ),
            IRInstruction(opcode=Opcode.HALT, operands=[]),
            IRInstruction(
                opcode=Opcode.CONST, result_reg=Register("%1"), operands=[2]
            ),
            IRInstruction(opcode=Opcode.RETURN, operands=["%1"]),
        ]

        cfg = build_cfg(instructions)

        entry_block = cfg.blocks[CodeLabel("entry")]
        assert entry_block.successors == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run python -m pytest tests/unit/test_cfg.py::TestHaltTerminatesBlock -v`
Expected: FAIL — without `Halt_` in the block-start tuple, `HALT` doesn't end a block, so the block will contain BOTH the `HALT` and the following `CONST`/`RETURN`, and (via the fallback "else: fall through" branch) may show a nonzero-length `successors` or otherwise not match the assertion. Confirm the actual failure message before proceeding.

- [ ] **Step 3: Implement**

In `interpreter/cfg.py`, at the current line 38:
```python
        elif isinstance(inst, (Branch, BranchIf, Return_, Throw_, ResumeContinuation)):
```
Change to:
```python
        elif isinstance(
            inst, (Branch, BranchIf, Return_, Throw_, Halt_, ResumeContinuation)
        ):
```

At the current line 89:
```python
        elif isinstance(last, (Return_, Throw_)):
            pass  # no successors
```
Change to:
```python
        elif isinstance(last, (Return_, Throw_, Halt_)):
            pass  # no successors
```

Add `Halt_` to the `from interpreter.instructions import (` block near the top of `interpreter/cfg.py` (currently starting at line 6), alongside `Return_,` and `Throw_,`.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run python -m pytest tests/unit/test_cfg.py::TestHaltTerminatesBlock -v`
Expected: PASS.

- [ ] **Step 5: Run the full CFG unit test file to check for regressions**

Run: `poetry run python -m pytest tests/unit/test_cfg.py -q`
Expected: all pass.

---

### Task 5: COBOL lowering — `STOP RUN` emits `Halt_`

**Files:**
- Modify: `interpreter/cobol/lower_arithmetic.py:1849-1858` (`lower_stop_run` only — `lower_goback` and `lower_exit_program`, immediately following, must NOT change)
- Test: (single-file regression check using an existing test; no new test needed for this task alone — Task 6 adds the multi-file tests that actually exercise the new halt behavior end-to-end)

**Interfaces:**
- Consumes: `Halt_` (Task 1).
- Produces: `lower_stop_run` now emits a single `Halt_()` instruction instead of `Const.int_` + `Return_(value_reg=...)`.

- [ ] **Step 1: Confirm the pre-change baseline (existing single-file STOP RUN tests currently pass)**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/integration/test_cobol_programs.py -k "stop_run or StopRun" -v`
Expected: PASS (these are single-file programs — a lone `STOP RUN` at the end with no `CALL` involved; the pre-existing single-frame-pop behavior already halts correctly in that case, same as the post-change `Halt_` behavior would, so this run is just a baseline sanity check before touching the lowering).

- [ ] **Step 2: Implement**

In `interpreter/cobol/lower_arithmetic.py`, change `lower_stop_run` (currently):
```python
def lower_stop_run(
    ctx: EmitContext,
    stmt: StopRunStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """STOP RUN."""
    zero_reg = ctx.fresh_reg()
    ctx.emit_inst(Const.int_(zero_reg, 0))
    ctx.emit_inst(Return_(value_reg=zero_reg))
```
to:
```python
def lower_stop_run(
    ctx: EmitContext,
    stmt: StopRunStatement,
    materialised: MaterialisedSectionedLayout,
) -> None:
    """STOP RUN — unconditionally terminates the entire run unit, unlike
    GOBACK/EXIT PROGRAM (which return control to the caller)."""
    ctx.emit_inst(Halt_())
```

Do NOT modify `lower_goback` or `lower_exit_program`, which immediately follow in the same file — they keep their existing `Const.int_` + `Return_(value_reg=zero_reg)` bodies unchanged.

Add `Halt_` to the `from interpreter.instructions import (` block near the top of `interpreter/cobol/lower_arithmetic.py` (currently starting at line 55), alongside `Return_,` (currently line 62).

- [ ] **Step 3: Re-run the baseline test to confirm it still passes**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/integration/test_cobol_programs.py -k "stop_run or StopRun" -v`
Expected: PASS (same as Step 1 — single-file `STOP RUN` still halts correctly, now via `Halt_` instead of the old single-frame `Return_`).

- [ ] **Step 4: Run the full COBOL suite to check for regressions from the lowering change alone**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/ -k "cobol or Cobol or COBOL" -q`
Expected: at this point, `TestCobolMultiFile::test_call_subprogram` (in `test_all_languages_execution.py`) and possibly other multi-file `STOP RUN` tests are now EXPECTED TO FAIL — this is the ticket's original bug being fixed out from under a test that asserted the wrong behavior. Confirm the failures are exactly the multi-file `STOP RUN`-in-subprogram tests (not something unrelated) before proceeding to Task 6, which fixes them.

---

### Task 6: Fix the incorrect multi-file test and add the new STOP RUN test suite

**Files:**
- Modify: `tests/integration/project/test_all_languages_execution.py:527,551` (docstring + assertion in `test_call_subprogram`)
- Modify: `tests/integration/test_cobol_programs.py` — add new `TestStopRunTerminatesRunUnit` class (after `TestGobackExitProgram`, which currently ends around line 6192)

**Interfaces:**
- Consumes: everything from Tasks 1-5 (this is the end-to-end validation of the whole feature).
- Produces: corrected regression coverage proving `STOP RUN` in a called subprogram halts the run unit (direct call and 3-level nested chain), and confirms `GOBACK`-at-top-level already halts correctly (pre-existing mechanism, not new).

- [ ] **Step 1: Fix `test_call_subprogram`'s docstring and assertion**

In `tests/integration/project/test_all_languages_execution.py`, the test currently (lines 520-583) has HELPER execute `MOVE 77 TO LK-TICKET` then `STOP RUN`, and MAIN execute `CALL 'HELPER' USING BY REFERENCE WS-TICKET` then `COMPUTE WS-RESULT = 42` then `STOP RUN`. The final assertions (currently lines 578-583):
```python
        # WS-TICKET at offset 0, 4 bytes — HELPER wrote 77 to LK-TICKET (copy-back)
        ticket = _decode_zoned_unsigned(main_ws, 0, 4)
        assert ticket == 77, f"WS-TICKET: expected 77 after HELPER write, got {ticket}"
        # WS-RESULT at offset 4, 4 bytes — 42 after COMPUTE
        result = _decode_zoned_unsigned(main_ws, 4, 4)
        assert result == 42, f"WS-RESULT: expected 42, got {result}"
```
Change to:
```python
        # WS-TICKET at offset 0, 4 bytes — HELPER wrote 77 to LK-TICKET (a direct
        # BY REFERENCE write into the shared params region, landing BEFORE
        # HELPER's STOP RUN executes — so this still happens even though
        # STOP RUN then halts the whole run unit).
        ticket = _decode_zoned_unsigned(main_ws, 0, 4)
        assert ticket == 77, f"WS-TICKET: expected 77 after HELPER write, got {ticket}"
        # WS-RESULT at offset 4, 4 bytes — STOP RUN in HELPER halts the entire
        # run unit, so MAIN's COMPUTE WS-RESULT = 42 (which runs AFTER the
        # CALL returns) must never execute; WS-RESULT stays at its VALUE 0.
        result = _decode_zoned_unsigned(main_ws, 4, 4)
        assert result == 0, f"WS-RESULT: expected 0 (STOP RUN halted before COMPUTE), got {result}"
```
Also update the docstring (currently lines 521-530) to describe the corrected expectation — replace:
```python
        """MAIN passes WS-TICKET BY REFERENCE; HELPER writes 77 into LK-TICKET.

        Verifies end-to-end multi-module CALL USING BY REFERENCE:
        - The params region (MAIN's WS-TICKET bytes) reaches HELPER's LINKAGE SECTION.
        - HELPER writes 77 into LK-TICKET, mutating the shared params region.
        - Copy-back after the CALL propagates 77 into MAIN's WS-TICKET.
        - MAIN's WS-RESULT equals 42 (execution continued after the CALL).

        Note: reading FROM a LINKAGE field into WS is tracked separately under
        red-dragon-4q25.33 (SECTION_LINKAGE read path).
        """
```
with:
```python
        """MAIN passes WS-TICKET BY REFERENCE; HELPER writes 77 then STOP RUNs.

        Verifies end-to-end multi-module CALL USING BY REFERENCE, AND that
        STOP RUN correctly halts the whole run unit (red-dragon-mjin):
        - The params region (MAIN's WS-TICKET bytes) reaches HELPER's LINKAGE SECTION.
        - HELPER writes 77 into LK-TICKET, mutating the shared params region
          BEFORE its STOP RUN executes.
        - HELPER's STOP RUN halts the ENTIRE run unit — MAIN's COMPUTE
          WS-RESULT = 42, which comes after the CALL, must never execute.

        Note: reading FROM a LINKAGE field into WS is tracked separately under
        red-dragon-4q25.33 (SECTION_LINKAGE read path).
        """
```

- [ ] **Step 2: Run the corrected test**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/integration/project/test_all_languages_execution.py::TestCobolMultiFile::test_call_subprogram -v`
Expected: PASS. If `ticket` is NOT 77 (i.e. the BY REFERENCE write didn't land before the halt), that's a genuine finding — stop and report it rather than adjusting the assertion to match; it would mean BY REFERENCE writes are not immediate, which is a separate concern from this plan's scope.

- [ ] **Step 3: Write the new failing multi-file STOP RUN tests**

In `tests/integration/test_cobol_programs.py`, add a new class immediately after `TestGobackExitProgram` (which currently ends around line 6192, right before whatever class follows it — insert after its last method):
```python
class TestStopRunTerminatesRunUnit:
    """STOP RUN halts the ENTIRE run unit, unlike GOBACK/EXIT PROGRAM (red-dragon-mjin)."""

    @covers(CobolFeature.STOP_RUN)
    def test_stop_run_in_subprogram_halts_caller(self, tmp_path):
        """STOP RUN in a called subprogram halts immediately; MAIN's post-CALL code never runs."""
        (tmp_path / "MAINPROG.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. MAINPROG.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-RESULT PIC 9(4) VALUE 0.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'HELPER'.",
                    "    MOVE 42 TO WS-RESULT.",
                    "    STOP RUN.",
                ]
            )
        )
        (tmp_path / "HELPER.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. HELPER.",
                    "PROCEDURE DIVISION.",
                    "    STOP RUN.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)
        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_mainprog_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=500,
        )

        singleton_ptr = None
        for frame in reversed(vm.call_stack):
            if VarName("__prog_MAINPROG") in frame.local_vars:
                singleton_ptr = frame.local_vars[VarName("__prog_MAINPROG")].value
                break
        assert singleton_ptr is not None
        assert isinstance(singleton_ptr, Pointer)
        ws_addr = Address(
            vm.heap_get(singleton_ptr.base).fields[FieldName("ws_handle")].value
        )
        region = vm.region_get(ws_addr)
        assert region is not None
        ws_result = _decode_zoned_unsigned(region, offset=0, length=4)
        assert (
            ws_result == 0
        ), f"WS-RESULT: expected 0 (STOP RUN in HELPER halted before MAIN's MOVE), got {ws_result}"

    @covers(CobolFeature.STOP_RUN)
    def test_stop_run_in_deeply_nested_call_halts_everything(self, tmp_path):
        """3-level CALL chain A->B->C; STOP RUN in C halts everything, not just B or C's frame."""
        (tmp_path / "PROGA.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. PROGA.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-A-RESULT PIC 9(4) VALUE 0.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'PROGB'.",
                    "    MOVE 1 TO WS-A-RESULT.",
                    "    STOP RUN.",
                ]
            )
        )
        (tmp_path / "PROGB.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. PROGB.",
                    "DATA DIVISION.",
                    "WORKING-STORAGE SECTION.",
                    "77 WS-B-RESULT PIC 9(4) VALUE 0.",
                    "PROCEDURE DIVISION.",
                    "    CALL 'PROGC'.",
                    "    MOVE 1 TO WS-B-RESULT.",
                    "    GOBACK.",
                ]
            )
        )
        (tmp_path / "PROGC.cbl").write_text(
            _to_fixed(
                [
                    "IDENTIFICATION DIVISION.",
                    "PROGRAM-ID. PROGC.",
                    "PROCEDURE DIVISION.",
                    "    STOP RUN.",
                ]
            )
        )

        linked = compile_directory(tmp_path, Language.COBOL)
        vm = run_linked(
            linked,
            entry_point=EntryPoint.function(
                lambda ref: str(ref.label).endswith("func_proga_0")
                and "init_params" not in str(ref.label)
            ),
            max_steps=500,
        )

        singleton_ptr = None
        for frame in reversed(vm.call_stack):
            if VarName("__prog_PROGA") in frame.local_vars:
                singleton_ptr = frame.local_vars[VarName("__prog_PROGA")].value
                break
        assert singleton_ptr is not None
        assert isinstance(singleton_ptr, Pointer)
        ws_addr = Address(
            vm.heap_get(singleton_ptr.base).fields[FieldName("ws_handle")].value
        )
        region = vm.region_get(ws_addr)
        assert region is not None
        ws_a_result = _decode_zoned_unsigned(region, offset=0, length=4)
        assert (
            ws_a_result == 0
        ), f"WS-A-RESULT: expected 0 (STOP RUN in PROGC halted the entire chain), got {ws_a_result}"

    @covers(CobolFeature.GOBACK)
    def test_goback_at_top_level_halts_vm(self):
        """GOBACK in the top-level/main program (no CALL) halts, same as STOP RUN.

        This is a regression guard for the pre-existing MAIN_FRAME_NAME/empty-stack
        mechanism in _handle_return_flow — not new behavior introduced by this fix.
        """
        vm = _run_cobol(
            [
                "IDENTIFICATION DIVISION.",
                "PROGRAM-ID. TEST-GOBACK-TOP.",
                "DATA DIVISION.",
                "WORKING-STORAGE SECTION.",
                "77 WS-FLAG PIC 9(1) VALUE 0.",
                "PROCEDURE DIVISION.",
                "MAIN-PARA.",
                "    GOBACK.",
                "    MOVE 1 TO WS-FLAG.",
            ],
            max_steps=500,
        )
        region = _first_region(vm)
        assert (
            region[0] == 0xF0
        ), f"WS-FLAG: expected 0 (GOBACK halted before MOVE 1), got {hex(region[0])}"
```

- [ ] **Step 4: Run test to verify it fails, then fix, then pass**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/integration/test_cobol_programs.py -k "TestStopRunTerminatesRunUnit" -v`

At this point in the plan (Tasks 1-5 already implemented), these three tests should already PASS, since the implementation work is done — this step is verification, not a new red/green cycle. If any fail, diagnose against the specific task above whose deliverable it's checking before moving on; do not adjust test assertions to match wrong behavior.

Expected: PASS (all 3).

- [ ] **Step 5: Run the existing `TestGobackExitProgram` class as a regression guard**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/integration/test_cobol_programs.py -k "TestGobackExitProgram" -v`
Expected: PASS, unchanged (proves `GOBACK`/`EXIT PROGRAM` still correctly return control to the caller — this class's tests must show ZERO code changes needed, only confirmation they still pass).

---

### Task 7: Full verification and commit

**Files:** none (verification only)

- [ ] **Step 1: Format**

Run: `poetry run python -m black .`

- [ ] **Step 2: Full COBOL suite**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest tests/ -k "cobol or Cobol or COBOL" -q`
Expected: all pass, zero failures.

- [ ] **Step 3: Full suite**

Run: `PROLEAP_BRIDGE_JAR=/Users/asgupta/code/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run python -m pytest -q`
Expected: all pass, zero failures, zero new skips beyond the pre-existing baseline.

- [ ] **Step 4: Commit**

```bash
git add interpreter/ir.py interpreter/instructions.py interpreter/handlers/control_flow.py interpreter/vm/executor.py interpreter/run.py interpreter/cfg.py interpreter/cobol/lower_arithmetic.py tests/unit/test_typed_instruction_compat.py tests/unit/test_typed_instructions.py tests/unit/test_execute_cfg.py tests/unit/test_execute_traced.py tests/unit/test_cfg.py tests/integration/test_cobol_programs.py tests/integration/project/test_all_languages_execution.py
git commit -m "$(cat <<'EOF'
fix(cobol): STOP RUN now halts the entire run unit, not just one call frame (red-dragon-mjin)

STOP RUN, GOBACK, and EXIT PROGRAM previously lowered to the identical
single Return_ instruction, so STOP RUN inside a called subprogram
silently acted like GOBACK/EXIT PROGRAM and returned control to the
caller instead of terminating the whole run unit — the opposite of
correct COBOL semantics. Introduces a dedicated Halt_ IR instruction
(distinct from Return_, invisible to return-type inference by
construction) that the VM step loop treats as an unconditional halt
regardless of call-stack depth. GOBACK/EXIT PROGRAM are unchanged —
they remain Return_ and correctly return to the caller.

Corrected an existing test (TestCobolMultiFile::test_call_subprogram)
that had encoded the wrong behavior as expected.

Design: docs/superpowers/specs/2026-07-03-cobol-stop-run-halt-design.md
EOF
)"
```

Note: this repo's pre-commit hook runs the full test suite (including the mandatory CardDemo CICS e2e tests) and can take several minutes — run this in the background and wait for completion rather than assuming a 2-minute foreground timeout is a failure.
