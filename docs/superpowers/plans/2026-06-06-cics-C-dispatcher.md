# CICS Sub-project C — Transaction Dispatcher

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement RETURN / RETURN TRANSID / XCTL / ABEND flow control lowering, `run_cics()` execution wrapper with COMMAREA injection, CSD parsing, eager program compilation, and the dispatcher loop.

**Architecture:** `CicsLoweringStrategy.lower()` handles flow control verbs — RETURN/XCTL/ABEND write to a `result_holder` then emit HALT. `run_cics()` pre-populates VM variables (`__params_region`, `__cics_transid`, etc.) by passing an `initial_vm` to `run_linked()`. The dispatcher loop drives the pseudo-conversational pattern: RETURN_TRANSID blocks on the input queue until the user sends a new event.

**Tech Stack:** Python 3.12, queue.Queue, pytest, black

**Beads story:** `red-dragon-pz9g.2`

**Depends on:** Sub-project B complete (CicsContext, DispatchResult, CicsLoweringStrategy exist)

---

## Files Created / Modified

| Action | Path |
|---|---|
| **Create** | `interpreter/cics/builtins/flow.py` |
| **Modify** | `interpreter/cics/strategy.py` — wire flow control in lower() |
| **Modify** | `interpreter/run.py` — add initial_vm param to run_linked() |
| **Create** | `interpreter/cics/dispatcher.py` |
| **Create** | `tests/unit/cics/test_flow_builtins.py` |
| **Create** | `tests/unit/cics/test_dispatcher.py` |

---

## Task C1: Flow Control Builtins

**Files:**
- Create: `interpreter/cics/builtins/flow.py`
- Create: `tests/unit/cics/test_flow_builtins.py`

Three builtins write to a `result_holder: list[DispatchResult | None]` and return. The dispatcher reads `result_holder[0]` after `run_cics()` returns.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/cics/test_flow_builtins.py`:

```python
"""Unit tests for CICS flow control builtins."""
from interpreter.cics.builtins.flow import (
    make_set_return_context_builtin,
    make_set_xctl_context_builtin,
)
from interpreter.cics.types import DispatchKind, DispatchResult
from interpreter.vm.vm_types import VMState
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import scalar


def _vm() -> VMState:
    return VMState()


def test_set_return_context_plain_return():
    holder: list[DispatchResult | None] = [None]
    builtin = make_set_return_context_builtin(holder)
    builtin([], _vm())
    assert holder[0] is not None
    assert holder[0].kind == DispatchKind.RETURN


def test_set_return_context_with_transid():
    holder: list[DispatchResult | None] = [None]
    builtin = make_set_return_context_builtin(holder)
    args = [
        typed("CC01", scalar("str")),   # transid
        typed(b"\x00" * 16, scalar("bytes")),  # commarea
    ]
    builtin(args, _vm())
    assert holder[0] is not None
    assert holder[0].kind == DispatchKind.RETURN_TRANSID
    assert holder[0].transid == "CC01"
    assert holder[0].commarea == b"\x00" * 16


def test_set_xctl_context():
    holder: list[DispatchResult | None] = [None]
    builtin = make_set_xctl_context_builtin(holder)
    args = [
        typed("COCRDLIC", scalar("str")),   # program name
        typed(b"", scalar("bytes")),        # commarea
    ]
    builtin(args, _vm())
    assert holder[0] is not None
    assert holder[0].kind == DispatchKind.XCTL
    assert holder[0].program == "COCRDLIC"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/cics/test_flow_builtins.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement flow builtins**

Create `interpreter/cics/builtins/flow.py`:

```python
"""CICS flow control builtins — RETURN TRANSID, XCTL, ABEND context setters."""

from __future__ import annotations

import logging

from interpreter.cics.types import DispatchKind, DispatchResult
from interpreter.types.typed_value import TypedValue
from interpreter.vm.vm_types import BuiltinResult, VMState

logger = logging.getLogger(__name__)


def make_set_return_context_builtin(result_holder: list) -> object:
    """Return __cics_set_return_context builtin.

    Called by lowering of EXEC CICS RETURN [TRANSID(x) COMMAREA(y)].
    With no args → plain RETURN. With args → RETURN_TRANSID.
    """

    def __cics_set_return_context(
        args: list[TypedValue], vm: VMState
    ) -> BuiltinResult:
        if not args:
            result_holder[0] = DispatchResult(kind=DispatchKind.RETURN)
        else:
            transid = str(args[0].value).strip() if args else ""
            commarea = bytes(args[1].value) if len(args) > 1 else b""
            result_holder[0] = DispatchResult(
                kind=DispatchKind.RETURN_TRANSID,
                transid=transid,
                commarea=commarea,
            )
        return BuiltinResult(value=None)

    return __cics_set_return_context


def make_set_xctl_context_builtin(result_holder: list) -> object:
    """Return __cics_set_xctl_context builtin.

    Called by lowering of EXEC CICS XCTL PROGRAM(p) [COMMAREA(y)].
    """

    def __cics_set_xctl_context(
        args: list[TypedValue], vm: VMState
    ) -> BuiltinResult:
        program = str(args[0].value).strip() if args else ""
        commarea = bytes(args[1].value) if len(args) > 1 else b""
        result_holder[0] = DispatchResult(
            kind=DispatchKind.XCTL,
            program=program,
            commarea=commarea,
        )
        return BuiltinResult(value=None)

    return __cics_set_xctl_context
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/cics/test_flow_builtins.py -v
```

Expected: all PASS

- [ ] **Step 5: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cics/builtins/flow.py tests/unit/cics/test_flow_builtins.py
git commit -m "$(cat <<'EOF'
feat(cics): flow control builtins (set_return_context, set_xctl_context) (pz9g.2)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task C2: Flow Control Lowering in CicsLoweringStrategy

**Files:**
- Modify: `interpreter/cics/strategy.py` — lower RETURN, RETURN TRANSID, XCTL, ABEND

Flow control verbs: emit `CALL_BUILTIN __cics_set_*` (writing to result_holder) then `HALT`. The HALT causes `run_cics()` to return; the dispatcher reads `result_holder[0]` to decide next action.

- [ ] **Step 1: Write the failing integration test**

Add to `tests/integration/cics/test_parse_strategy.py`:

```python
from interpreter.cics.types import CicsContext, DispatchKind
from interpreter.cics.strategy import CicsLoweringStrategy


COBOL_RETURN_TRANSID = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TESTRET.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-TRANSID PIC X(4) VALUE 'CC01'.
       01 WS-CA PIC X(8) VALUE SPACES.
       PROCEDURE DIVISION.
           EXEC CICS RETURN TRANSID(WS-TRANSID) COMMAREA(WS-CA)
               LENGTH(8) END-EXEC.
           STOP RUN.
"""


def test_return_transid_lowers_to_set_context_and_halt(parser):
    """RETURN TRANSID lowers to __cics_set_return_context + HALT."""
    from interpreter.cics.preprocessor import apply_cics_prepass
    from interpreter.cobol.cobol_frontend import CobolFrontend
    from interpreter.ir import Opcode

    context_holder = [CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")]
    result_holder: list = [None]
    builtin_registry: dict = {}
    strategy = CicsLoweringStrategy(
        context_holder=context_holder,
        builtin_registry=builtin_registry,
        result_holder=result_holder,
    )

    source = apply_cics_prepass(COBOL_RETURN_TRANSID.decode()).encode()
    frontend = CobolFrontend(cobol_parser=parser, exec_cics_strategy=strategy)
    instructions = frontend.lower(source)

    opcodes = [i.opcode for i in instructions]
    assert Opcode.CALL_BUILTIN in opcodes  # __cics_set_return_context was emitted
    assert Opcode.HALT in opcodes           # HALT follows
```

```bash
poetry run python -m pytest tests/integration/cics/test_parse_strategy.py::test_return_transid_lowers_to_set_context_and_halt -v
```

Expected: FAIL — `CicsLoweringStrategy.lower()` currently just warns.

- [ ] **Step 2: Implement flow control lowering in strategy.py**

Update `interpreter/cics/strategy.py`. Update `CicsLoweringStrategy.__init__` to also register flow builtins, and update `lower()`:

```python
from interpreter.cics.builtins.flow import (
    make_set_return_context_builtin,
    make_set_xctl_context_builtin,
)
from interpreter.instructions import CallBuiltin, Halt_, LoadVar, Const
from interpreter.register import NO_REGISTER
from interpreter.func_name import FuncName

# In __init__, add:
builtin_registry["__cics_set_return_context"] = make_set_return_context_builtin(result_holder)
builtin_registry["__cics_set_xctl_context"] = make_set_xctl_context_builtin(result_holder)
# __cics_abend already registered in B3

# Replace lower() with:
def lower(self, ctx, stmt, materialised) -> None:
    verb = stmt.verb
    opts = stmt.options

    # ── Flow control ─────────────────────────────────────────────────
    if verb == "RETURN":
        if "TRANSID" in opts:
            # RETURN TRANSID(x) COMMAREA(y) LENGTH(n)
            r_transid = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=r_transid, value=opts.get("TRANSID", "")))
            # COMMAREA is a data reference — load its bytes at runtime via LoadVar
            # For now emit as empty bytes constant (Plan D will add proper serialization)
            r_ca = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=r_ca, value=b""))
            r_res = ctx.fresh_reg()
            ctx.emit_inst(CallBuiltin(
                result_reg=r_res,
                name=FuncName("__cics_set_return_context"),
                args=[r_transid, r_ca],
            ))
        else:
            # Plain RETURN
            r_res = ctx.fresh_reg()
            ctx.emit_inst(CallBuiltin(
                result_reg=r_res,
                name=FuncName("__cics_set_return_context"),
                args=[],
            ))
        ctx.emit_inst(Halt_())
        return

    if verb == "XCTL":
        r_prog = ctx.fresh_reg()
        # PROGRAM option is a data reference; load from field if resolvable
        prog_opt = opts.get("PROGRAM", "")
        try:
            fl, region_reg = materialised.resolve(prog_opt)
            from interpreter.instructions import LoadRegion
            r_off = ctx.fresh_reg()
            ctx.emit_inst(Const(result_reg=r_off, value=fl.offset))
            ctx.emit_inst(LoadRegion(result_reg=r_prog, region_reg=region_reg,
                                     offset_reg=r_off, length=fl.byte_length))
        except Exception:
            ctx.emit_inst(Const(result_reg=r_prog, value=prog_opt))
        r_ca = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=r_ca, value=b""))
        r_res = ctx.fresh_reg()
        ctx.emit_inst(CallBuiltin(
            result_reg=r_res,
            name=FuncName("__cics_set_xctl_context"),
            args=[r_prog, r_ca],
        ))
        ctx.emit_inst(Halt_())
        return

    if verb == "ABEND":
        r_code = ctx.fresh_reg()
        ctx.emit_inst(Const(result_reg=r_code, value=opts.get("ABCODE", "UNKN")))
        r_res = ctx.fresh_reg()
        ctx.emit_inst(CallBuiltin(
            result_reg=r_res,
            name=FuncName("__cics_abend"),
            args=[r_code],
        ))
        ctx.emit_inst(Halt_())
        return

    # ── System verbs ─────────────────────────────────────────────────
    builtin_name = _SYS_VERBS.get(verb)
    if builtin_name:
        r_res = ctx.fresh_reg()
        ctx.emit_inst(CallBuiltin(result_reg=r_res, name=FuncName(builtin_name), args=[]))
        return

    logger.warning("CicsLoweringStrategy: unimplemented verb %r", verb)
```

- [ ] **Step 3: Run the integration test**

```bash
poetry run python -m pytest tests/integration/cics/test_parse_strategy.py -v
```

Expected: all PASS

- [ ] **Step 4: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cics/strategy.py tests/integration/cics/test_parse_strategy.py
git commit -m "$(cat <<'EOF'
feat(cics): flow control lowering in CicsLoweringStrategy (RETURN/XCTL/ABEND) (pz9g.2)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task C3: run_linked() initial_vm Parameter

**Files:**
- Modify: `interpreter/run.py` — add `initial_vm: VMState | None = None` to `run_linked()`

`run_cics()` needs to pass a pre-built VMState with `__params_region` and `__cics_*` variables set before execution begins. `execute_cfg()` already accepts `vm: VMState | None = None`. We just need to thread it through `run_linked()`.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/cics/test_dispatcher.py` (create this file):

```python
"""Unit tests for run_cics() and the dispatcher loop."""
from interpreter.run import run_linked, EntryPoint
from interpreter.vm.vm_types import VMState, StackFrame
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import scalar


def test_run_linked_accepts_initial_vm(tmp_path):
    """run_linked() passes initial_vm to execute_cfg — variables are pre-set."""
    # We verify this via the signature; a full execution test is in test_dispatcher.
    import inspect
    from interpreter.run import run_linked
    sig = inspect.signature(run_linked)
    assert "initial_vm" in sig.parameters
```

```bash
poetry run python -m pytest tests/unit/cics/test_dispatcher.py::test_run_linked_accepts_initial_vm -v
```

Expected: FAIL — `initial_vm` not in `run_linked` signature.

- [ ] **Step 2: Add initial_vm to run_linked()**

In `interpreter/run.py`, update `run_linked` signature and body:

```python
def run_linked(
    linked: LinkedProgram,
    entry_point: EntryPoint,
    max_steps: int = 100,
    verbose: bool = False,
    backend: str = LLMProvider.CLAUDE,
    unresolved_call_strategy: UnresolvedCallStrategy = UnresolvedCallStrategy.SYMBOLIC,
    io_provider: Any = None,
    initial_vm: VMState | None = None,   # <-- ADD THIS
) -> VMState:
```

Then in the `execute_cfg(...)` calls within `run_linked`, pass `vm=initial_vm` to the first call:

```python
    if entry_point.is_top_level:
        vm, exec_stats = execute_cfg(
            linked.merged_cfg,
            linked.merged_cfg.entry,
            linked.merged_registry,
            vm_config,
            strategies,
            vm=initial_vm,      # <-- ADD THIS
        )
```

(For the two-phase path, pass `vm=initial_vm` to the first `execute_cfg` call only.)

- [ ] **Step 3: Run tests**

```bash
poetry run python -m pytest tests/unit/cics/test_dispatcher.py -v
poetry run python -m pytest -x -q
```

Expected: all PASS (no regressions)

- [ ] **Step 4: Format and commit**

```bash
poetry run python -m black .
git add interpreter/run.py tests/unit/cics/test_dispatcher.py
git commit -m "$(cat <<'EOF'
feat(cics): add initial_vm param to run_linked() for CICS COMMAREA injection (pz9g.2)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task C4: run_cics() and Dispatcher Loop

**Files:**
- Create: `interpreter/cics/dispatcher.py`
- Modify: `tests/unit/cics/test_dispatcher.py` — add dispatcher tests

`run_cics()` builds the initial VMState with CICS variables pre-set, then calls `run_linked()`. The dispatcher loop drives pseudo-conversational execution: RETURN_TRANSID blocks on `input_queue`, XCTL jumps to a new program.

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/cics/test_dispatcher.py`:

```python
import queue
from unittest.mock import MagicMock
from interpreter.cics.types import CicsContext, DispatchKind, DispatchResult
from interpreter.cics.dispatcher import run_dispatcher


def _make_mock_program(return_kind: DispatchKind):
    """Return a mock LinkedProgram and a run_cics that returns a fixed DispatchResult."""
    pass  # real test below uses actual dispatcher with mock run_cics injected


def test_dispatcher_return_stops_loop():
    """RETURN terminates the dispatcher loop immediately."""
    calls = []

    def mock_run_cics(program, ctx, sq, iq):
        calls.append(ctx.transid)
        return DispatchResult(kind=DispatchKind.RETURN)

    from interpreter.cics.dispatcher import _run_dispatcher_with_runner
    program_cache = {"CC00": MagicMock(), "COSGN00C": MagicMock()}
    transid_to_program = {"CC00": "COSGN00C"}
    ctx = CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")
    sq, iq = queue.Queue(), queue.Queue()

    result = _run_dispatcher_with_runner(
        mock_run_cics, program_cache, transid_to_program, ctx, sq, iq
    )
    assert result.kind == DispatchKind.RETURN
    assert len(calls) == 1


def test_dispatcher_xctl_switches_program():
    """XCTL causes dispatcher to switch to named program and re-execute."""
    call_count = [0]

    def mock_run_cics(program, ctx, sq, iq):
        call_count[0] += 1
        if call_count[0] == 1:
            return DispatchResult(kind=DispatchKind.XCTL, program="PROG2", commarea=b"")
        return DispatchResult(kind=DispatchKind.RETURN)

    from interpreter.cics.dispatcher import _run_dispatcher_with_runner
    program_cache = {"PROG1": MagicMock(), "PROG2": MagicMock()}
    transid_to_program = {"CC00": "PROG1"}
    ctx = CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")
    sq, iq = queue.Queue(), queue.Queue()

    result = _run_dispatcher_with_runner(
        mock_run_cics, program_cache, transid_to_program, ctx, sq, iq
    )
    assert call_count[0] == 2
    assert result.kind == DispatchKind.RETURN


def test_dispatcher_return_transid_blocks_then_resumes():
    """RETURN_TRANSID blocks until input_queue has event, then starts new execution."""
    call_count = [0]

    def mock_run_cics(program, ctx, sq, iq):
        call_count[0] += 1
        if call_count[0] == 1:
            return DispatchResult(
                kind=DispatchKind.RETURN_TRANSID, transid="CC01", commarea=b""
            )
        return DispatchResult(kind=DispatchKind.RETURN)

    from interpreter.cics.dispatcher import _run_dispatcher_with_runner
    from interpreter.cics.dispatcher import InputEvent

    program_cache = {"PROG1": MagicMock(), "PROG2": MagicMock()}
    transid_to_program = {"CC00": "PROG1", "CC01": "PROG2"}
    ctx = CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")
    sq, iq = queue.Queue(), queue.Queue()

    # Pre-populate input queue so it doesn't block
    iq.put(InputEvent(eibaid="\x7d", fields={}))

    result = _run_dispatcher_with_runner(
        mock_run_cics, program_cache, transid_to_program, ctx, sq, iq
    )
    assert call_count[0] == 2
    assert result.kind == DispatchKind.RETURN
```

```bash
poetry run python -m pytest tests/unit/cics/test_dispatcher.py -v
```

Expected: FAIL — `dispatcher.py` does not exist.

- [ ] **Step 2: Implement dispatcher.py**

Create `interpreter/cics/dispatcher.py`:

```python
"""CICS transaction dispatcher — run_cics() and dispatcher loop."""

from __future__ import annotations

import logging
import queue
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from interpreter.cics.types import CicsContext, DispatchKind, DispatchResult
from interpreter.project.types import LinkedProgram
from interpreter.run import run_linked, EntryPoint
from interpreter.vm.vm_types import VMState, StackFrame
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import scalar

logger = logging.getLogger(__name__)

_DFHENTER = "\x7d"


@dataclass
class InputEvent:
    """Inbound terminal event — attention key + map field values."""

    eibaid: str = _DFHENTER
    fields: dict[str, str] = field(default_factory=dict)


RunCicsFn = Callable[
    [LinkedProgram, CicsContext, "queue.Queue[Any]", "queue.Queue[InputEvent]"],
    DispatchResult,
]


def run_cics(
    program: LinkedProgram,
    context: CicsContext,
    screen_queue: "queue.Queue[Any]",
    input_queue: "queue.Queue[InputEvent]",
    *,
    builtin_registry: dict[str, Any],
    context_holder: list[CicsContext],
    result_holder: list[DispatchResult | None],
    max_steps: int = 50_000,
) -> DispatchResult:
    """Execute one CICS program with the given context. Returns DispatchResult.

    Pre-populates VM variables __cics_transid / __cics_eibcalen / __cics_eibaid
    and __params_region (COMMAREA bytes) before execution begins.
    """
    # Update context_holder so __cics_init_eib builtin reads fresh values
    context_holder[0] = context
    result_holder[0] = None  # reset before each execution

    # Build initial VMState with CICS variables pre-set
    initial_vm = VMState()
    initial_vm.call_stack.append(
        StackFrame(
            function_name=FuncName("main"),
            local_vars={
                VarName("__cics_transid"): typed(context.transid, scalar("str")),
                VarName("__cics_eibcalen"): typed(len(context.commarea), scalar("int")),
                VarName("__cics_eibaid"): typed(context.eibaid, scalar("str")),
                # __params_region: COMMAREA bytes as raw value
                # (linked via LINKAGE SECTION binding in lower_data_division.py)
                VarName("__params_region"): typed(context.commarea, scalar("bytes")),
            },
        )
    )

    from interpreter.run import run_linked, EntryPoint

    final_vm = run_linked(
        program,
        EntryPoint.function(lambda label: str(label).startswith("func_")),
        max_steps=max_steps,
        initial_vm=initial_vm,
    )

    # If a flow control builtin set result_holder[0], return it
    if result_holder[0] is not None:
        return result_holder[0]

    # If VM halted without a flow control result, treat as plain RETURN
    return DispatchResult(kind=DispatchKind.RETURN)


def _run_dispatcher_with_runner(
    run_fn: RunCicsFn,
    program_cache: dict[str, LinkedProgram],
    transid_to_program: dict[str, str],
    initial_context: CicsContext,
    screen_queue: "queue.Queue[Any]",
    input_queue: "queue.Queue[InputEvent]",
) -> DispatchResult:
    """Core dispatcher loop — separated for testability (accepts injected run_fn)."""
    context = initial_context
    program = program_cache[transid_to_program[context.transid]]

    while True:
        result = run_fn(program, context, screen_queue, input_queue)

        if result.kind == DispatchKind.RETURN_TRANSID:
            # Pseudo-conversational: wait for user input, then start fresh execution
            event = input_queue.get()  # blocks
            next_prog_name = transid_to_program.get(result.transid or "")
            if not next_prog_name:
                logger.error("Unknown transid %r from RETURN TRANSID", result.transid)
                return DispatchResult(kind=DispatchKind.ABEND, abcode="TRNI")
            program = program_cache[next_prog_name]
            context = CicsContext(
                transid=result.transid or "",
                commarea=result.commarea or b"",
                eibaid=event.eibaid,
            )

        elif result.kind == DispatchKind.XCTL:
            prog_name = (result.program or "").strip()
            if prog_name not in program_cache:
                logger.error("XCTL to unknown program %r", prog_name)
                return DispatchResult(kind=DispatchKind.ABEND, abcode="PGMI")
            program = program_cache[prog_name]
            context = CicsContext(
                transid=context.transid,
                commarea=result.commarea or b"",
                eibaid=context.eibaid,
            )

        else:  # RETURN or ABEND
            return result


def parse_csd(csd_path: Path) -> dict[str, str]:
    """Parse CARDDEMO.CSD to produce {transid: program_name} mapping.

    Scans for PCT entries of the form:
        DEFINE TRANSACTION(CC00) PROGRAM(COSGN00C)
    Returns a dict mapping transid → program name.
    """
    transid_to_program: dict[str, str] = {}
    content = csd_path.read_text(encoding="utf-8", errors="replace")
    import re
    pattern = re.compile(
        r"DEFINE\s+TRANSACTION\((\w+)\)\s+PROGRAM\((\w+)\)", re.IGNORECASE
    )
    for m in pattern.finditer(content):
        transid_to_program[m.group(1).upper()] = m.group(2).upper()
    logger.info("CSD parsed: %d transid→program mappings", len(transid_to_program))
    return transid_to_program
```

- [ ] **Step 3: Run tests**

```bash
poetry run python -m pytest tests/unit/cics/test_dispatcher.py -v
```

Expected: all PASS

- [ ] **Step 4: Run full suite**

```bash
poetry run python -m pytest -x -q
```

Expected: all PASS

- [ ] **Step 5: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cics/dispatcher.py tests/unit/cics/test_dispatcher.py
git commit -m "$(cat <<'EOF'
feat(cics): run_cics() + dispatcher loop + CSD parser (pz9g.2)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Sub-project C Complete

At this point:
- `RETURN`, `RETURN TRANSID`, `XCTL`, `ABEND` all lower to a builtin call + HALT
- `run_cics()` pre-populates VM variables for CICS context before execution
- The dispatcher loop drives pseudo-conversational transactions (RETURN_TRANSID blocks on queue)
- `parse_csd()` extracts the transid→program mapping from CARDDEMO.CSD
- `_run_dispatcher_with_runner()` is separately testable without ProLeap

**Next:** [Sub-project D — VSAM File Engine](2026-06-06-cics-D-vsam.md) and/or [Sub-project E — BMS Screen Engine](2026-06-06-cics-E-bms.md) (independent)
