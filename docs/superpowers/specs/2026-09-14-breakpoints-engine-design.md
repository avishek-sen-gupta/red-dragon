# Breakpoints Engine — Design

**Status:** Draft for review
**Date:** 2026-09-14
**Scope:** Sub-project 1 of the breakpoint facility (engine). Source locations and source-line breakpoints are separate follow-on specs.

## Context

RedDragon has no way to pause a running program at a chosen point, inspect `VMState`, and continue. The only interactive consumers (the TUI and the MCP server) run the program to completion first and then replay a recorded trace; the MCP design spec explicitly lists "no pause/resume mechanism" and "no breakpoints" as gaps.

The VM already has most of the machinery: a `Suspend` instruction makes `_run_loop` return an `ExecutionState` continuation `(vm, current_label, ip, resume_reg)`, and `resume()` / `resume_linked()` re-enter the loop at that cursor. Breakpoints reuse this path.

The primary consumer for v1 is the **Python API and tests**. TUI and MCP adapters are out of scope.

## Decomposition

| # | Sub-project | Depends on |
|---|---|---|
| 1 | **Breakpoints engine** (this spec): step-hook loop, traced-loop unification, label / position / function / paragraph breakpoints | — |
| 2 | COBOL source locations: plumb ASG `SourceSpan` onto instructions in `EmitContext.emit_inst`; add a file to `SourceLocation` | — |
| 3 | Source-line breakpoints: line → position index for all frontends | 1, 2 |

## Findings that shaped the design

1. **Two copies of the step loop.** `_run_loop` (`interpreter/run.py:367`) backs `execute_cfg`, `run_resumable`, `resume`. `execute_cfg_traced` (`interpreter/run.py:701`) is a hand-copied loop that has drifted:
   - it does not handle `Suspend`;
   - it treats every `Throw_` as a return (`run.py:801`), whereas `_run_loop` distinguishes caught throws (`run.py:449`) — a latent bug in the traced path;
   - its only addition is a deep-copied `TraceStep` per executed instruction plus an initial-state snapshot.
2. **Who uses the traced loop.** In this repo: `viz/pipeline.py`, `viz/project_pipeline.py` (via `run_linked_traced`), `mcp_server/session.py`, `scripts/symbolic_trace_harness.py`, and `interpreter/api.py::execute_traced` (test-only). The downstream `red-dragon-forge` repo does not use it (directly or via the TUI/MCP); it drives execution only through `run_linked_resumable` / `resume_linked`, i.e. `_run_loop`.
3. **Downstream outcome handling.** The downstream conversational driver in `red-dragon-forge` branches `if isinstance(outcome, Suspended): ... else: # Completed`. A new outcome variant must never be returned to callers that did not ask for breakpoints.
4. **Instruction ids are not a usable breakpoint coordinate.** Only `CobolFrontend` assigns `InstructionId`s (from a per-frontend counter starting at 0); tree-sitter frontends leave `NO_INSTRUCTION_ID`. Ids therefore are absent for 14 languages and collide across linked COBOL modules. Breakpoints use a CFG **position** `(label, index)` instead.
5. **Label namespacing.** The linker prefixes every label with its module prefix (`<prefix>.<label>`, `interpreter/project/linker.py:78`); the prefix is the module path stem (a COBOL main module is `__main__`).
6. **Function and paragraph entries are labels.** `func_symbol_table: dict[CodeLabel, FuncRef]` maps entry labels to `FuncRef(name, label)`. COBOL paragraphs and sections lower to `para_<NAME>` / `section_<NAME>` labels (`interpreter/cobol/lower_procedure.py`).

## Decisions

- Consumer: Python API / tests.
- Targets in v1: label, position, function entry, COBOL paragraph/section entry.
- Refinements in v1: none (no conditions, hit counts, or stepping).
- Data watches: dropped from v1.
- Unify the traced loop onto `_run_loop` **before** adding breakpoints.
- Engine approach: step hooks in a single loop (rejected: IR rewriting with injected `Suspend`; hard-wired breakpoint/record parameters).

## Section 1 — Architecture

### Step hooks

`_run_loop` gains `hooks: Sequence[StepHook] = ()`.

```python
class StepHook(Protocol):
    def before(
        self, label: CodeLabel, ip: int, instruction: InstructionBase, vm: VMState
    ) -> StopReason | None: ...

    def after(
        self,
        label: CodeLabel,
        ip: int,
        instruction: InstructionBase,
        update: StateUpdate,
        vm: VMState,
        used_llm: bool,
    ) -> None: ...
```

- `before` is called for every instruction that is about to execute, **after** the `Label_` skip and **before** the `Suspend` check and execution. The first hook returning a `StopReason` stops the loop; the instruction does not execute.
- `after` is called once the update has been applied (after `apply_update` / call-dispatch setup) and **before** control-flow advance (halt, return flow, jump, `ip += 1`). This matches where the traced loop records today.
- With `hooks=()` the loop's behaviour is identical to today.

### Traced-loop unification

- `TraceRecorder(StepHook)`: `before` returns `None`; `after` appends `TraceStep(step_index, block_label, instruction_index, instruction, update, vm_state=copy.deepcopy(vm), used_llm)`.
- `execute_cfg_traced` becomes a wrapper: deep-copy the initial VM, build the base context exactly as `execute_cfg` does, run `_run_loop(..., hooks=[recorder])`, and assemble `ExecutionTrace(steps, stats, initial_state)`. Public signature and return type are unchanged, so TUI, MCP and `run_linked_traced` are untouched.
- The duplicated loop body is deleted.
- Behaviour changes in the traced path (both are fixes toward `_run_loop` semantics):
  - caught throws follow the catch handler instead of return flow;
  - on `Suspend`, recording stops and the trace up to that point is returned (logged at debug level). The signature has no way to express suspension.

### Outcome type

```python
@dataclass
class Paused:
    """Outcome: execution stopped by a breakpoint before executing an instruction."""
    state: ExecutionState
    reason: StopReason

RunOutcome = Union[Suspended, Paused, Completed]
```

- `_LoopResult.suspended: bool` is replaced by a stop kind (`NONE | SUSPEND | BREAKPOINT`) plus the existing cursor fields and an optional `StopReason`.
- `_wrap_outcome` maps `BREAKPOINT` → `Paused`. The paused cursor is the instruction that did **not** execute; `resume_reg` is `NO_REGISTER`.
- `Paused` can only arise when a stop-capable hook is installed, which only happens when a caller passes `breakpoints`. Callers that pass none can never observe `Paused`.

### Resuming from a pause

- `ExecutionState` gains `from_pause: bool = False` (plain data; stays picklable).
- `_run_loop` gains `skip_first_before: bool = False`: when set, `before` hooks are not consulted for the first instruction executed.
- `resume()` / `resume_linked()` pass `skip_first_before=state.from_pause`, so resuming at a breakpoint executes that instruction instead of re-pausing on it.
- For a `Paused` state, `resume()`'s `value` argument is ignored (there is no register to receive it).

## Section 2 — Breakpoint targets and API

### Targets

```python
@dataclass(frozen=True)
class AtLabel:
    label: str

@dataclass(frozen=True)
class AtPosition:
    label: str
    index: int  # index into the block's instruction list

@dataclass(frozen=True)
class AtFunction:
    name: str

@dataclass(frozen=True)
class AtParagraph:
    name: str  # COBOL paragraph or section

BreakpointTarget = Union[AtLabel, AtPosition, AtFunction, AtParagraph]
```

### Resolution

`resolve_breakpoints(targets, cfg, func_symbol_table) -> dict[tuple[CodeLabel, int], BreakpointTarget]` runs once, before any instruction executes.

- **Label matching** (`AtLabel`, `AtPosition`): a CFG block label matches if it equals the given label, or ends with `.` + the given label (module-prefixed form).
- **`AtLabel`** resolves to the index of the block's first non-`Label_` instruction.
- **`AtPosition`** resolves to `(label, index)` verbatim; `index` must be within the block.
- **`AtFunction`**: every `FuncRef` in `func_symbol_table` whose `name` equals the given name (all overloads), resolved as `AtLabel(ref.label)`.
- **`AtParagraph`**: labels `para_<NAME>` and `section_<NAME>`, compared case-insensitively on the name (COBOL names are case-insensitive), with the same module-prefix matching; resolved as `AtLabel`.
- When several targets resolve to the same position, the first target in caller order is recorded.
- A target that matches nothing, or an out-of-range `AtPosition.index`, raises `UnresolvedBreakpointError` naming the target and the nearest label candidates.

### Hook

`BreakpointHook(positions)`: `before` returns `StopReason(kind=BREAKPOINT, target=positions[(label, ip)], label=label, ip=ip)` when `(label, ip)` is a resolved position; `after` is a no-op.

### API

Keyword-only `breakpoints: Sequence[BreakpointTarget] = ()` is added to:

- `run_resumable`, `resume`
- `run_linked_resumable`, `resume_linked`

Breakpoints are re-supplied on every `resume` call rather than stored in `ExecutionState`, keeping the continuation plain picklable data. Non-resumable entry points (`run`, `run_linked`, `execute_cfg`) do not accept breakpoints — they return `VMState` and have no way to report a pause. `execute_cfg_traced` does not accept breakpoints.

For linked programs, resolution uses `linked.merged_cfg` and `linked.func_symbol_table`. For `run_linked_resumable`, breakpoints apply to both the preamble and entry-function phases.

## Section 3 — Semantics, errors, testing

### Semantics

- **Step budget:** steps executed before a pause count toward that call's `max_steps`; each `resume` call gets a fresh `max_steps` (today's `resume` behaviour). Exhausting the budget yields `Completed`, never `Paused`.
- **Re-hits:** a breakpoint fires every time execution arrives at its position (loops, recursion, repeated `PERFORM`).
- **Inside calls:** the call stack lives in `vm.call_stack`, so pausing inside a function or `PERFORM` and resuming returns to the caller correctly.
- **Snapshots:** `Paused.state.vm` is the live VM (same as `Suspended`); callers that want to keep an inspection snapshot while resuming must deep-copy it. Documented on `Paused`.

### Errors

- `UnresolvedBreakpointError` (raised at resolution time, before execution).
- No silent no-op breakpoints.

### Testing (TDD; unit + integration)

1. **Unification (no behaviour change except the two documented fixes):** existing `tests/unit/test_execute_traced.py`, `tests/unit/viz/test_run_linked_traced.py`, `tests/unit/test_suspend_resume.py`, `tests/unit/test_suspend_resume_calls.py` pass unchanged. New tests: traced execution follows a caught throw to its handler; traced execution stops recording at `Suspend`.
2. **Resolution unit tests:** each target kind; module-prefix fallback; case-insensitive paragraph/section; function overloads; unresolved target and out-of-range index raise.
3. **Loop unit tests** (hand-built CFGs): pause occurs before the instruction executes; resume executes it without re-pausing; breakpoint in a loop fires each iteration; pause inside a callee and resume back into the caller; no breakpoints never yields `Paused`.
4. **Integration tests** (`tests/integration/`):
   - Python: `AtFunction` breakpoint via `run_linked_resumable`; assert local values in the paused VM; `resume_linked` to `Completed`.
   - COBOL: `AtParagraph` breakpoint via compile + `run_linked_resumable`; assert a WORKING-STORAGE field value at the pause and its final value after `resume_linked`.
   - COBOL: `PERFORM ... 3 TIMES` of a breakpointed paragraph yields three `Paused` outcomes then `Completed`.

## Out of scope

- Source-line breakpoints and COBOL source-location plumbing (sub-projects 2 and 3).
- Data watches.
- Conditional breakpoints, hit counts, step / step-over / step-out.
- TUI and MCP breakpoint UX.
- Making instruction ids universal or link-unique.
