# CICS Sub-project B — CICS Runtime / EIB + System Builtins

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the shared runtime types (CicsContext, DispatchResult), initialize EIB fields in WS at procedure entry, and wire up system service builtins (ASSIGN, ASKTIME, FORMATTIME, INQUIRE, WRITEQ TD, HANDLE ABEND, ABEND).

**Architecture:** `interpreter/cics/types.py` holds the shared dataclasses used by C/D/E. `CicsLoweringStrategy.on_procedure_entry()` (from Plan A) emits a `CALL_BUILTIN __cics_init_eib` that writes EIB field bytes to the WS region at runtime. System service builtins are curried closures registered under `__cics_*` names. All EXEC CICS verbs are handled by `CicsLoweringStrategy.lower()`.

**Tech Stack:** Python 3.12, struct, interpreter/cobol/ebcdic_table.py, pytest, black

**Beads story:** `red-dragon-pz9g.1`

**Depends on:** Sub-project A complete (ExecCicsStrategy protocol present, CicsLoweringStrategy skeleton exists)

---

## Files Created / Modified

| Action | Path |
|---|---|
| **Create** | `interpreter/cics/types.py` |
| **Create** | `interpreter/cics/builtins/__init__.py` |
| **Create** | `interpreter/cics/builtins/system.py` |
| **Modify** | `interpreter/cics/strategy.py` — fill out CicsLoweringStrategy |
| **Create** | `tests/unit/cics/test_types.py` |
| **Create** | `tests/unit/cics/test_system_builtins.py` |
| **Create** | `tests/unit/cics/test_eib_init.py` |

---

## Task B1: CicsContext, DispatchKind, DispatchResult Types

**Files:**
- Create: `interpreter/cics/types.py`
- Create: `tests/unit/cics/test_types.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/cics/test_types.py`:

```python
"""Unit tests for CICS shared runtime types."""
from interpreter.cics.types import CicsContext, DispatchKind, DispatchResult


def test_cics_context_creation():
    ctx = CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")
    assert ctx.transid == "CC00"
    assert ctx.eibaid == "\x7d"
    assert len(ctx.commarea) == 0


def test_dispatch_result_return():
    r = DispatchResult(kind=DispatchKind.RETURN)
    assert r.kind == DispatchKind.RETURN
    assert r.transid is None
    assert r.commarea is None
    assert r.program is None
    assert r.abcode is None


def test_dispatch_result_return_transid():
    r = DispatchResult(
        kind=DispatchKind.RETURN_TRANSID,
        transid="CC01",
        commarea=b"\x00" * 16,
    )
    assert r.kind == DispatchKind.RETURN_TRANSID
    assert r.transid == "CC01"
    assert len(r.commarea) == 16


def test_dispatch_result_xctl():
    r = DispatchResult(kind=DispatchKind.XCTL, program="COCRDUPC", commarea=b"")
    assert r.kind == DispatchKind.XCTL
    assert r.program == "COCRDUPC"


def test_dispatch_result_abend():
    r = DispatchResult(kind=DispatchKind.ABEND, abcode="CICS")
    assert r.kind == DispatchKind.ABEND
    assert r.abcode == "CICS"


def test_dispatch_kind_static_field():
    # No isinstance dispatch — always compare .kind directly
    r = DispatchResult(kind=DispatchKind.RETURN_TRANSID, transid="X", commarea=b"")
    assert r.kind == DispatchKind.RETURN_TRANSID
    assert r.kind != DispatchKind.RETURN
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/cics/test_types.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.cics.types'`

- [ ] **Step 3: Create types.py**

Create `interpreter/cics/types.py`:

```python
"""CICS shared runtime types — CicsContext, DispatchResult, DispatchKind."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass
class CicsContext:
    """Runtime state passed into each CICS program execution."""

    transid: str
    commarea: bytes
    eibaid: str  # 1-char attention identifier (e.g. "\x7d" = DFHENTER)


class DispatchKind(Enum):
    RETURN = "return"
    RETURN_TRANSID = "return_transid"
    XCTL = "xctl"
    ABEND = "abend"


@dataclass
class DispatchResult:
    """Result returned by run_cics() to the dispatcher loop."""

    kind: DispatchKind
    transid: str | None = None      # RETURN_TRANSID
    commarea: bytes | None = None   # RETURN_TRANSID, XCTL
    program: str | None = None      # XCTL
    abcode: str | None = None       # ABEND
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/cics/test_types.py -v
```

Expected: all PASS

- [ ] **Step 5: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cics/types.py tests/unit/cics/test_types.py
git commit -m "$(cat <<'EOF'
feat(cics): CicsContext, DispatchKind, DispatchResult runtime types (pz9g.1)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task B2: EIB Initialization at Procedure Entry

**Files:**
- Create: `interpreter/cics/builtins/__init__.py`
- Modify: `interpreter/cics/strategy.py` — implement CicsLoweringStrategy skeleton + on_procedure_entry
- Create: `tests/unit/cics/test_eib_init.py`

`CicsLoweringStrategy` is constructed with a mutable `context_holder: list[CicsContext]` (single-element list, updated before each `run_cics()` call). `on_procedure_entry` emits `CALL_BUILTIN __cics_init_eib`. The builtin finds the WS region, encodes EIB field values, and writes them via `vm.region_set`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/cics/test_eib_init.py`:

```python
"""Unit tests for EIB initialization builtin."""
import struct
from interpreter.cics.types import CicsContext
from interpreter.cics.builtins.system import make_init_eib_builtin
from interpreter.vm.vm_types import VMState, StackFrame
from interpreter.func_name import FuncName
from interpreter.var_name import VarName
from interpreter.address import Address
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import scalar


def _make_vm_with_ws_region(region_bytes: bytearray) -> tuple[VMState, Address]:
    """Create a minimal VMState with a WS region pre-allocated."""
    vm = VMState()
    addr = Address("ws_region_0")
    vm.region_set(addr, region_bytes)
    frame = StackFrame(
        function_name=FuncName("main"),
        local_vars={VarName("__ws_region"): typed(str(addr), scalar("str"))},
    )
    vm.call_stack.append(frame)
    # data_layout mirrors DFHEIBLK fields at known offsets
    vm.data_layout = {
        "EIBTRNID": {"offset": 0, "length": 4, "category": "ALPHANUMERIC"},
        "EIBCALEN": {"offset": 4, "length": 2, "category": "BINARY"},
        "EIBAID": {"offset": 6, "length": 1, "category": "ALPHANUMERIC"},
        "EIBRESP": {"offset": 7, "length": 4, "category": "BINARY"},
        "EIBRESP2": {"offset": 11, "length": 4, "category": "BINARY"},
    }
    return vm, addr


def test_eib_init_writes_transid():
    ctx = CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")
    holder = [ctx]
    builtin = make_init_eib_builtin(holder)

    ws = bytearray(64)
    vm, addr = _make_vm_with_ws_region(ws)

    from interpreter.vm.vm_types import BuiltinResult
    result = builtin([], vm)

    region = vm.region_get(addr)
    assert region is not None
    # EIBTRNID at offset 0, 4 bytes — "CC00" in ASCII/EBCDIC representation
    assert region[0:4] != bytearray(4)  # non-zero means something was written


def test_eib_init_writes_eibcalen():
    ctx = CicsContext(transid="CC00", commarea=b"\x00" * 24, eibaid="\x7d")
    holder = [ctx]
    builtin = make_init_eib_builtin(holder)

    ws = bytearray(64)
    vm, addr = _make_vm_with_ws_region(ws)
    builtin([], vm)

    region = vm.region_get(addr)
    assert region is not None
    # EIBCALEN at offset 4, 2 bytes big-endian — should be 24
    calen = struct.unpack(">h", bytes(region[4:6]))[0]
    assert calen == 24


def test_eib_init_writes_zero_calen_for_empty_commarea():
    ctx = CicsContext(transid="CC00", commarea=b"", eibaid="\x7d")
    holder = [ctx]
    builtin = make_init_eib_builtin(holder)

    ws = bytearray(64)
    vm, addr = _make_vm_with_ws_region(ws)
    builtin([], vm)

    region = vm.region_get(addr)
    calen = struct.unpack(">h", bytes(region[4:6]))[0]
    assert calen == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/cics/test_eib_init.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.cics.builtins'`

- [ ] **Step 3: Create builtins package and make_init_eib_builtin**

Create `interpreter/cics/builtins/__init__.py` (empty).

Create `interpreter/cics/builtins/system.py`:

```python
"""CICS system service builtins — curried closures over shared state."""

from __future__ import annotations

import logging
import struct
import time
from datetime import datetime
from typing import TYPE_CHECKING

from interpreter.vm.vm_types import BuiltinResult, VMState
from interpreter.types.typed_value import TypedValue, typed
from interpreter.types.type_expr import scalar
from interpreter.var_name import VarName
from interpreter.address import Address

if TYPE_CHECKING:
    from interpreter.cics.types import CicsContext

logger = logging.getLogger(__name__)

# EBCDIC encode: simple ASCII→EBCDIC for printable chars
# Using the existing table in interpreter/cobol/ebcdic_table.py
def _ascii_to_ebcdic_bytes(s: str, length: int) -> list[int]:
    from interpreter.cobol.ebcdic_table import ASCII_TO_EBCDIC
    padded = s.ljust(length)[:length]
    return [ASCII_TO_EBCDIC.get(ord(c), 0x40) for c in padded]


def _get_ws_region_addr(vm: VMState) -> Address | None:
    """Find __ws_region address from the VM call stack."""
    ws_var = VarName("__ws_region")
    for frame in reversed(vm.call_stack):
        if ws_var in frame.local_vars:
            tv = frame.local_vars[ws_var]
            return Address(str(tv.value))
    return None


def make_init_eib_builtin(
    context_holder: list[CicsContext],
) -> object:
    """Return a builtin that writes EIB fields to WS at procedure entry.

    context_holder is a single-element list updated by run_cics() before each execution.
    The builtin reads from holder[0] at runtime to get transid, commarea, eibaid.
    """

    def __cics_init_eib(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        ctx = context_holder[0]
        addr = _get_ws_region_addr(vm)
        if addr is None:
            logger.warning("__cics_init_eib: no __ws_region in VM — EIB not initialised")
            return BuiltinResult(value=None)

        region = vm.region_get(addr)
        if region is None:
            logger.warning("__cics_init_eib: WS region not allocated — EIB not initialised")
            return BuiltinResult(value=None)

        layout = vm.data_layout

        def _write_field(name: str, data: list[int]) -> None:
            if name not in layout:
                return
            f = layout[name]
            off, length = f["offset"], f["length"]
            region[off : off + length] = data[:length]

        # EIBTRNID — PIC X(4) alphanumeric
        _write_field("EIBTRNID", _ascii_to_ebcdic_bytes(ctx.transid, 4))

        # EIBCALEN — PIC S9(4) COMP (2-byte big-endian)
        calen = len(ctx.commarea)
        _write_field("EIBCALEN", list(struct.pack(">h", calen)))

        # EIBAID — PIC X(1)
        aid_byte = ord(ctx.eibaid) if ctx.eibaid else 0x7D  # default DFHENTER
        _write_field("EIBAID", [aid_byte])

        # EIBRESP / EIBRESP2 — initialise to 0
        _write_field("EIBRESP", list(struct.pack(">i", 0)))
        _write_field("EIBRESP2", list(struct.pack(">i", 0)))

        # EIBTRNID also needs to be in the persistent singleton so programs
        # reading the field after init see the updated value.
        vm.region_set(addr, region)

        return BuiltinResult(value=None)

    return __cics_init_eib
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/cics/test_eib_init.py -v
```

Expected: all PASS

- [ ] **Step 5: Implement CicsLoweringStrategy skeleton in strategy.py**

In `interpreter/cics/strategy.py`, add `CicsLoweringStrategy`:

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from interpreter.cics.builtins.system import make_init_eib_builtin
from interpreter.func_name import FuncName
from interpreter.instructions import CallBuiltin
from interpreter.register import NO_REGISTER

if TYPE_CHECKING:
    from interpreter.cics.types import CicsContext
    from interpreter.cobol.emit_context import EmitContext
    from interpreter.cobol.cobol_statements import ExecCicsStatement
    from interpreter.cobol.sectioned_layout import MaterialisedSectionedLayout

logger = logging.getLogger(__name__)

_BUILTIN_INIT_EIB = FuncName("__cics_init_eib")


class CicsLoweringStrategy:
    """Full CICS lowering strategy. Inject at CobolFrontend construction for CICS mode.

    context_holder — single-element list; dispatcher updates holder[0] before each run_cics().
    builtin_registry — dict updated here; dispatcher passes it to run_linked() so builtins resolve.
    """

    def __init__(
        self,
        context_holder: list[CicsContext],
        builtin_registry: dict[str, object],
    ) -> None:
        self._context_holder = context_holder
        self._builtin_registry = builtin_registry
        # Register __cics_init_eib immediately at construction
        builtin_registry[str(_BUILTIN_INIT_EIB)] = make_init_eib_builtin(context_holder)

    def on_procedure_entry(
        self,
        ctx: EmitContext,
        materialised: MaterialisedSectionedLayout,
    ) -> None:
        """Emit __cics_init_eib call to write EIB fields into WS at runtime."""
        result_reg = ctx.fresh_reg()
        ctx.emit_inst(
            CallBuiltin(
                result_reg=result_reg,
                name=_BUILTIN_INIT_EIB,
                args=[],
            )
        )

    def lower(
        self,
        ctx: EmitContext,
        stmt: ExecCicsStatement,
        materialised: MaterialisedSectionedLayout,
    ) -> None:
        """Dispatch on verb to the appropriate lowering function. Skeleton: warns for now."""
        logger.warning(
            "CicsLoweringStrategy: unimplemented verb %r — no IR emitted", stmt.verb
        )
```

- [ ] **Step 6: Run full suite to check for regressions**

```bash
poetry run python -m pytest -x -q
```

Expected: all existing tests PASS

- [ ] **Step 7: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cics/builtins/__init__.py interpreter/cics/builtins/system.py \
        interpreter/cics/strategy.py tests/unit/cics/test_eib_init.py
git commit -m "$(cat <<'EOF'
feat(cics): EIB init builtin + CicsLoweringStrategy skeleton (pz9g.1)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task B3: System Service Builtins

**Files:**
- Modify: `interpreter/cics/builtins/system.py` — add ASSIGN, ASKTIME, FORMATTIME, INQUIRE, WRITEQ TD, HANDLE ABEND builtins
- Modify: `interpreter/cics/strategy.py` — wire system verbs in `lower()`
- Create: `tests/unit/cics/test_system_builtins.py`

These builtins are stubs/simple implementations. Each is registered in `builtin_registry` at `CicsLoweringStrategy` construction.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/cics/test_system_builtins.py`:

```python
"""Unit tests for CICS system service builtins."""
from interpreter.cics.builtins.system import (
    make_assign_builtin,
    make_asktime_builtin,
    make_writeq_td_builtin,
    make_handle_abend_builtin,
    make_abend_builtin,
    make_inquire_builtin,
)
from interpreter.cics.types import DispatchKind, DispatchResult
from interpreter.vm.vm_types import VMState, BuiltinResult
from interpreter.types.typed_value import typed
from interpreter.types.type_expr import scalar


def _make_simple_vm() -> VMState:
    return VMState()


def test_assign_builtin_is_callable():
    builtin = make_assign_builtin(applid="CARDDEMO", sysid="SYS1")
    vm = _make_simple_vm()
    result = builtin([], vm)
    assert isinstance(result, BuiltinResult)


def test_asktime_builtin_returns_result():
    builtin = make_asktime_builtin()
    vm = _make_simple_vm()
    result = builtin([], vm)
    assert isinstance(result, BuiltinResult)


def test_writeq_td_appends_to_queue():
    queue: list[str] = []
    builtin = make_writeq_td_builtin(queue)
    vm = _make_simple_vm()
    # arg 0 = data string, arg 1 = queue name
    args = [typed("SOME DATA", scalar("str")), typed("CSMT", scalar("str"))]
    builtin(args, vm)
    assert len(queue) == 1
    assert "SOME DATA" in queue[0]


def test_handle_abend_is_noop():
    builtin = make_handle_abend_builtin()
    vm = _make_simple_vm()
    result = builtin([], vm)
    assert isinstance(result, BuiltinResult)


def test_abend_builtin_sets_dispatch_result():
    holder: list[DispatchResult | None] = [None]
    builtin = make_abend_builtin(holder)
    vm = _make_simple_vm()
    args = [typed("CICS", scalar("str"))]
    builtin(args, vm)
    assert holder[0] is not None
    assert holder[0].kind == DispatchKind.ABEND
    assert holder[0].abcode == "CICS"


def test_inquire_program_found():
    cache = {"COSGN00C": object(), "COADM02C": object()}
    builtin = make_inquire_builtin(cache)
    vm = _make_simple_vm()
    args = [typed("COSGN00C", scalar("str"))]
    result = builtin(args, vm)
    assert isinstance(result, BuiltinResult)
    # EIBRESP should be 0 (NORMAL) — actual EIB write is tested in integration
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run python -m pytest tests/unit/cics/test_system_builtins.py -v
```

Expected: FAIL — functions not defined yet.

- [ ] **Step 3: Add system service builtins to system.py**

Append to `interpreter/cics/builtins/system.py`:

```python
# ── System service builtins ──────────────────────────────────────────────────


def make_assign_builtin(applid: str = "CARDDEMO", sysid: str = "SYS1") -> object:
    """EXEC CICS ASSIGN APPLID(f) SYSID(f) — write config strings to output fields.

    The lowering strategy resolves the field references and passes their
    current string values as args; this builtin is a simple no-op stub
    since the strategy writes directly via LOAD/STORE IR.
    """
    def __cics_assign(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        return BuiltinResult(value=None)

    return __cics_assign


def make_asktime_builtin() -> object:
    """EXEC CICS ASKTIME ABSTIME(f) — write current time to ABSTIME field."""
    def __cics_asktime(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        # Returns current time as CICS ABSTIME (microseconds since 1900-01-01)
        # Programs using ASKTIME + FORMATTIME expect a numeric value.
        epoch_1900 = datetime(1900, 1, 1)
        now = datetime.utcnow()
        abstime = int((now - epoch_1900).total_seconds() * 1_000_000)
        return BuiltinResult(value=abstime)

    return __cics_asktime


def make_formattime_builtin() -> object:
    """EXEC CICS FORMATTIME ABSTIME(t) YYYYMMDD(d) TIME(h) — format datetime fields."""
    def __cics_formattime(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        now = datetime.utcnow()
        return BuiltinResult(value=now.strftime("%Y%m%d"))

    return __cics_formattime


def make_writeq_td_builtin(queue: list[str]) -> object:
    """EXEC CICS WRITEQ TD QUEUE(name) FROM(data) — append to transient data queue."""
    def __cics_writeq_td(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        data = str(args[0].value) if args else ""
        name = str(args[1].value) if len(args) > 1 else "CSMT"
        queue.append(f"[{name}] {data}")
        return BuiltinResult(value=None)

    return __cics_writeq_td


def make_handle_abend_builtin() -> object:
    """EXEC CICS HANDLE ABEND LABEL(x) / CANCEL — no-op (carddemo uses it for cleanup)."""
    def __cics_handle_abend(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        logger.info("HANDLE ABEND — logged, no-op in emulation")
        return BuiltinResult(value=None)

    return __cics_handle_abend


def make_abend_builtin(result_holder: list) -> object:
    """EXEC CICS ABEND ABCODE(c) — record abend result for dispatcher.

    result_holder is a single-element list; dispatcher reads it after run_cics() returns.
    """
    def __cics_abend(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        abcode = str(args[0].value) if args else "UNKN"
        result_holder[0] = DispatchResult(kind=DispatchKind.ABEND, abcode=abcode)
        return BuiltinResult(value=None)

    return __cics_abend


def make_inquire_builtin(program_cache: dict) -> object:
    """EXEC CICS INQUIRE PROGRAM(name) — check if program is known; set EIBRESP."""
    def __cics_inquire(args: list[TypedValue], vm: VMState) -> BuiltinResult:
        name = str(args[0].value).strip() if args else ""
        resp = 0 if name in program_cache else 27  # 27 = PGMIDERR
        return BuiltinResult(value=resp)

    return __cics_inquire
```

Add the missing import at the top of `system.py`:

```python
from interpreter.cics.types import DispatchKind, DispatchResult
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run python -m pytest tests/unit/cics/test_system_builtins.py -v
```

Expected: all PASS

- [ ] **Step 5: Wire system verbs into CicsLoweringStrategy.lower()**

In `interpreter/cics/strategy.py`, update `CicsLoweringStrategy.__init__` to register all system builtins, and update `lower()` to lower system verbs to `CALL_BUILTIN`:

```python
from interpreter.cics.builtins.system import (
    make_assign_builtin,
    make_asktime_builtin,
    make_formattime_builtin,
    make_inquire_builtin,
    make_writeq_td_builtin,
    make_handle_abend_builtin,
    make_abend_builtin,
    make_init_eib_builtin,
)
from interpreter.func_name import FuncName
from interpreter.instructions import CallBuiltin, Halt_
from interpreter.register import NO_REGISTER

_SYS_VERBS = {
    "ASSIGN": "__cics_assign",
    "ASKTIME": "__cics_asktime",
    "FORMATTIME": "__cics_formattime",
    "INQUIRE": "__cics_inquire",
    "WRITEQ TD": "__cics_writeq_td",
    "HANDLE ABEND": "__cics_handle_abend",
    "HANDLE CONDITION": "__cics_handle_abend",  # same no-op
    "HANDLE AID": "__cics_handle_abend",
}

class CicsLoweringStrategy:
    def __init__(
        self,
        context_holder: list[CicsContext],
        builtin_registry: dict[str, object],
        result_holder: list,
        program_cache: dict | None = None,
        td_queue: list[str] | None = None,
        applid: str = "CARDDEMO",
        sysid: str = "SYS1",
    ) -> None:
        self._context_holder = context_holder
        self._builtin_registry = builtin_registry
        self._result_holder = result_holder
        prog_cache = program_cache or {}
        td = td_queue if td_queue is not None else []

        # Register all builtins
        builtin_registry["__cics_init_eib"] = make_init_eib_builtin(context_holder)
        builtin_registry["__cics_assign"] = make_assign_builtin(applid, sysid)
        builtin_registry["__cics_asktime"] = make_asktime_builtin()
        builtin_registry["__cics_formattime"] = make_formattime_builtin()
        builtin_registry["__cics_inquire"] = make_inquire_builtin(prog_cache)
        builtin_registry["__cics_writeq_td"] = make_writeq_td_builtin(td)
        builtin_registry["__cics_handle_abend"] = make_handle_abend_builtin()
        builtin_registry["__cics_abend"] = make_abend_builtin(result_holder)

    def on_procedure_entry(self, ctx, materialised) -> None:
        result_reg = ctx.fresh_reg()
        ctx.emit_inst(CallBuiltin(result_reg=result_reg, name=FuncName("__cics_init_eib"), args=[]))

    def lower(self, ctx, stmt, materialised) -> None:
        builtin_name = _SYS_VERBS.get(stmt.verb)
        if builtin_name:
            result_reg = ctx.fresh_reg()
            ctx.emit_inst(CallBuiltin(result_reg=result_reg, name=FuncName(builtin_name), args=[]))
            return
        logger.warning("CicsLoweringStrategy: unimplemented verb %r — no IR emitted", stmt.verb)
```

Note: argument resolution (loading field values for ASSIGN/ASKTIME targets) is handled in Sub-project C when flow control verbs are wired up. For now system verbs emit a no-arg call — sufficient to prevent crashes.

- [ ] **Step 6: Run full suite**

```bash
poetry run python -m pytest -x -q
```

Expected: all PASS

- [ ] **Step 7: Format and commit**

```bash
poetry run python -m black .
git add interpreter/cics/builtins/system.py interpreter/cics/strategy.py \
        tests/unit/cics/test_system_builtins.py
git commit -m "$(cat <<'EOF'
feat(cics): system service builtins + CicsLoweringStrategy wiring (pz9g.1)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Sub-project B Complete

At this point:
- `CicsContext`, `DispatchKind`, `DispatchResult` are defined in `interpreter/cics/types.py`
- EIB fields (EIBTRNID, EIBCALEN, EIBAID, EIBRESP) are written to WS at procedure entry via `__cics_init_eib`
- System service verbs (ASSIGN, ASKTIME, FORMATTIME, INQUIRE, WRITEQ TD, HANDLE ABEND, ABEND) lower to registered builtins
- `CicsLoweringStrategy` is wired — still logs warnings for RETURN/XCTL/file/screen verbs

**Next:** [Sub-project C — Transaction Dispatcher](2026-06-06-cics-C-dispatcher.md)
