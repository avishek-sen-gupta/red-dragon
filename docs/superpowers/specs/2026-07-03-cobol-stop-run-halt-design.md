# COBOL STOP RUN correct halt semantics — design

**Ticket:** red-dragon-mjin
**Date:** 2026-07-03

## Problem

COBOL's `STOP RUN` must terminate the *entire run unit* — the top-level program plus every subprogram currently on the call stack — regardless of which program in a `CALL` chain executes it. `GOBACK` and `EXIT PROGRAM`, executed inside a subprogram reached via `CALL`, must instead return control to the immediate caller (a normal subprogram return). `GOBACK` executed in the top-level program (never `CALL`ed into) has no caller, so it behaves like `STOP RUN`.

Today, `lower_stop_run`, `lower_goback`, and `lower_exit_program` (`interpreter/cobol/lower_arithmetic.py:1850-1880`) are identical: all three emit a single `Return_` instruction. The VM's `_handle_return_flow` (`interpreter/run.py:286-322`) treats every `Return_` as "pop exactly one call-stack frame and resume at the caller" (or halt only if the popped frame is the top-level/`MAIN_FRAME_NAME` frame or the stack is empty). So `STOP RUN` inside a called subprogram today incorrectly returns to the caller instead of halting — the opposite of the ticket's original (incorrect) title. An existing test, `TestCobolMultiFile::test_call_subprogram` (`tests/integration/project/test_all_languages_execution.py:520-583`), asserts this wrong behavior as expected and must be corrected.

## Mechanism: a dedicated `Halt_` instruction

Two designs were considered:

- **A flag on `Return_`** (e.g. `halt_all: bool`) — smaller diff, but `_infer_return`'s exact-type dispatch (`interpreter/types/type_inference.py:944,1006`) would still union `STOP RUN`'s synthetic zero value into the enclosing function's inferred return type, since the dispatch keys on `type(inst)` not the flag. This is already a latent bug shared by `GOBACK`/`EXIT PROGRAM` (which legitimately are returns, so this doesn't matter for them) — but for `STOP RUN`, which never returns to anyone, it's a real semantic mismatch.
- **A dedicated `Halt_` instruction** (chosen) — a `Halt_` is simply absent from `_infer_return`'s dispatch table, so it's correctly invisible to return-type inference with zero extra code. It's also more semantically honest: a halt is not a return.

`GOBACK` and `EXIT PROGRAM` are unchanged — they remain `Return_`, since they are genuine function returns.

### New instruction

`interpreter/ir.py`: add `HALT = "HALT"` to the `Opcode` enum (after `THROW`).

`interpreter/instructions.py`: add, mirroring `Return_`'s shape but with no value/result (a halt never returns a value to anyone):

```python
@dataclass(frozen=True)
class Halt_(InstructionBase):
    """HALT: unconditionally terminate the entire run unit (COBOL STOP RUN)."""

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

### VM handler

`interpreter/handlers/control_flow.py`: add `_handle_halt`, mirroring `_handle_return`'s shape but trivial (no return value, no call_pop):

```python
def _handle_halt(inst: InstructionBase, vm: VMState, ctx: HandlerContext) -> ExecutionResult:
    assert isinstance(inst, Halt_)
    return ExecutionResult.success(StateUpdate(reasoning="STOP RUN — halt run unit"))
```

`interpreter/vm/executor.py:203`: register `Opcode.HALT: _handle_halt` in the dispatch table alongside `Opcode.RETURN: _handle_return`.

### Step-loop halting

Both step-loop sites (`interpreter/run.py:444` in the main loop, and the parallel traced-execution loop at `interpreter/run.py:791`) get one new check, placed before the existing `is_return`/`is_throw` handling:

```python
if isinstance(instruction, Halt_):
    break  # unconditional — ignores call-stack depth entirely
```

This does not call `_handle_return_flow` at all — no frame pop, no caller-register write, no `MAIN_FRAME_NAME` check. `break` exits the step loop immediately, which is sufficient: the loop simply stops running further instructions, so any remaining call-stack frames are irrelevant (there is no continuation to resume). `apply_update` is still called earlier in the loop for other bookkeeping (line ~466-469 / ~808-811), but since `Halt_`'s `StateUpdate` carries no `call_pop`, no `var_writes`, etc., that call is a no-op — no special-casing needed there.

### CFG block-terminator treatment

`interpreter/cfg.py:38` (block-start detection) and `interpreter/cfg.py:89` (no-successors terminator check) both currently gate on `isinstance(inst, (Branch, BranchIf, Return_, Throw_, ResumeContinuation))` / `isinstance(last, (Return_, Throw_))`. Add `Halt_` to both tuples so a block ending in `Halt_` is correctly treated as having no fallthrough successor (matching `Return_`/`Throw_`'s existing treatment) — without this, CFG-based analyses would see a (nonexistent) reachable edge to the code after `STOP RUN`.

### Lowering change

`interpreter/cobol/lower_arithmetic.py`: `lower_stop_run` changes from:

```python
zero_reg = ctx.fresh_reg()
ctx.emit_inst(Const.int_(zero_reg, 0))
ctx.emit_inst(Return_(value_reg=zero_reg))
```

to:

```python
ctx.emit_inst(Halt_())
```

(The synthetic `zero_reg`/`Const.int_` was only ever there to satisfy `Return_`'s shape — `Halt_` needs no value, so it's dropped entirely.)

`lower_goback` and `lower_exit_program` are untouched.

## Scope boundaries

- No other language frontend emits `Halt_` — it is COBOL-only, used solely by `STOP RUN`. This is a pure addition; no existing instruction's default behavior changes, so all 15+ frontends and COBOL's own `GOBACK`/`EXIT PROGRAM` paths are unaffected.
- Interprocedural inlining (`interpreter/interprocedural/summaries.py:139,143`) and the LLM backend need no changes — confirmed during design investigation that `Halt_` is either irrelevant to those paths (STOP RUN bodies aren't inline candidates) or transparently unhandled without consequence (RETURN/HALT never reach the LLM backend; it's fully handled locally).
- `GOBACK`-at-top-level's existing halt behavior (via the `MAIN_FRAME_NAME`/empty-stack check in `_handle_return_flow`) is not changed by this design — it already works correctly today via a mechanism unrelated to COBOL. This design adds a regression test confirming it, rather than re-implementing it.
- Separately noted during investigation but explicitly OUT OF SCOPE for this fix: `run_project`/`analyze_project` (`interpreter/api.py:373-420`) doesn't bootstrap into any COBOL procedure division for multi-file execution at all (a distinct pre-existing gap, unrelated to STOP RUN semantics). Not addressed here.

## Test plan

All tests use the multi-file `compile_directory`/`run_linked` pattern already established by `TestGobackExitProgram` (`tests/integration/test_cobol_programs.py:6006+`).

1. **Fix the wrong test.** `TestCobolMultiFile::test_call_subprogram` (`tests/integration/project/test_all_languages_execution.py:520-583`) currently asserts that `MAIN` continues executing after a callee's `STOP RUN`. Correct it to assert the opposite: `MAIN`'s post-`CALL` code (e.g. a `MOVE 42 TO WS-RESULT` following the `CALL`) must **not** execute — `WS-RESULT` stays at its pre-`CALL` value.
2. **New `TestStopRunTerminatesRunUnit` class** (`tests/integration/test_cobol_programs.py`, alongside `TestGobackExitProgram`):
   - `STOP RUN` in a directly-called subprogram halts immediately; caller's subsequent code never runs (regression-shaped mirror of the corrected test above, but as a dedicated, clearly-named test).
   - Three-level nested `CALL` chain (A calls B calls C); `STOP RUN` in C halts the entire chain — none of B's or A's post-`CALL` code executes. This is the test that most directly targets "unwind the *entire* stack, not just one frame."
   - `GOBACK` at the top level (single-file program, no `CALL` involved) halts the VM — regression guard confirming the pre-existing `MAIN_FRAME_NAME` mechanism, not a new behavior.
3. **Regression guards (no changes expected, run to confirm no breakage):** `TestGobackExitProgram`'s existing tests — `GOBACK`/`EXIT PROGRAM` in a called subprogram still return control to the caller, caller's post-`CALL` code still executes and sees `LINKAGE` writes from the callee.
4. Full COBOL suite (`pytest tests/ -k "cobol or Cobol or COBOL"`) and full suite, both must stay green.

## Non-goals

- Not touching `run_project`/`analyze_project`'s missing COBOL procedure-division bootstrap (separate pre-existing gap, noted above).
- Not adding `Halt_` support to any other language frontend — none currently need it.
- Not attempting to model COBOL's `STOP RUN <literal>` (return-code) form differently from plain `STOP RUN` — out of scope unless a gap is found there during implementation (existing `CobolFeature`/tests for `STOP_RUN` with a return code, if any, should be checked for continued correctness but are not expected to need changes, since `STOP RUN`'s halt semantics are orthogonal to whether it carries a return code).
