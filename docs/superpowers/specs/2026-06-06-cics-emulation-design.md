# CICS Emulation Layer — Design Specification

**Date:** 2026-06-06
**Fitness function:** Run the online transactional flows of `aws-mainframe-carddemo` end-to-end via red-dragon's VM.

---

## Overview

The CICS emulation layer is organised into five sub-projects with explicit dependencies. All implementation is TDD: failing test first, then implementation.

```
A (Parse Strategy)
    └── B (CICS Runtime / EIB)
            ├── C (Transaction Dispatcher)
            ├── D (VSAM File Engine)
            └── E (BMS Screen Engine)
```

All CICS code lives under `interpreter/cics/`.

---

## Sub-project A — Parse Strategy

### Pre-pass (text level)

A single-pass, line-oriented text transformer runs **before** ProLeap. It is faithful to what IBM's CICS translator does: keyword-trigger scanning, no COBOL parse.

**Responsibilities:**

1. **Inject `COPY DFHEIBLK.`** — scan line-by-line for `WORKING-STORAGE SECTION`; insert a new line `       COPY DFHEIBLK.` (fixed-format columns 8–72) immediately after. Shifts subsequent content down by one line.
2. **Substitute `DFHRESP(name)` → numeric literal** — per-line regex: `re.sub(r'DFHRESP\((\w+)\)', lambda m: str(DFHRESP_TABLE[m.group(1)]), line)`. Only three codes appear in carddemo (`NORMAL`=0, `NOTFND`=13, `ENDFILE`=20); full ~120-entry table is bundled.

**Not in scope for pre-pass:** EXEC CICS body parsing. ProLeap handles that.

**Authored copybooks** (bundled at `interpreter/cics/copybooks/`):

| File | Purpose |
|---|---|
| `DFHEIBLK.cpy` | EIB data structure — full IBM layout, only `EIBAID`/`EIBCALEN`/`EIBRESP`/`EIBTRNID` need meaningful runtime values for carddemo |
| `DFHAID.cpy` | Attention identifier constants (`DFHENTER`, `DFHCLEAR`, `DFHPA1/2/3`, `DFHPF1–24`) |
| `DFHBMSCA.cpy` | BMS color/attribute constants (`DFHRED`, `DFHGREEN`, `DFHBMPRO`, etc.) |

`DFHAID.cpy` and `DFHBMSCA.cpy` are already `COPY`'d by carddemo programs — the pre-pass only needs to provide them on ProLeap's copybook search path.

### ProLeap parse

ProLeap parses the pre-pass output normally. `EXEC CICS` blocks become `ExecCicsStatement` AST nodes with verb and options already extracted. No second CICS parser needed.

### `ExecCicsStatement` lowering

`ExecCicsStatement` is added to `CobolStatementType`. `dispatch_statement` gains one new branch:

```python
elif isinstance(stmt, ExecCicsStatement):
    ctx.exec_cics_strategy.lower(ctx, stmt, materialised)
```

**No `None` allowed.** Two implementations of the `ExecCicsStrategy` protocol:

- **`CatchAllLoweringStrategy`** — default, always present. Emits a warning log. No IR.
- **`CicsLoweringStrategy`** — injected for CICS mode at `CobolFrontend` construction time (same pattern as `io_provider`). Handles all EXEC CICS verbs explicitly. Contains all CICS lowering logic — no CICS knowledge anywhere else in the lowering layer.

`ExecCicsStatement` dataclass:

```python
@dataclass(frozen=True)
class ExecCicsStatement:
    verb: str                      # e.g. "SEND MAP", "READ", "RETURN"
    options: dict[str, str | None] # e.g. {"MAP": "COSGN0A", "ERASE": None}
```

### Codebase location

```
interpreter/cics/
    preprocessor.py        # text pre-pass
    strategy.py            # ExecCicsStrategy protocol, CatchAllLoweringStrategy, CicsLoweringStrategy
    copybooks/
        DFHEIBLK.cpy
        DFHAID.cpy
        DFHBMSCA.cpy
```

---

## Sub-project B — CICS Runtime / EIB

### EIB

The EIB is a **normal COBOL data structure** in WORKING-STORAGE, declared by `DFHEIBLK.cpy` and injected by the pre-pass. No VM special-casing. The CICS runtime holds Python references to EIB fields to read/write them. Fields populated at program start:

| EIB Field | Source |
|---|---|
| `EIBTRNID` | `CicsContext.transid` |
| `EIBCALEN` | `len(CicsContext.commarea)` |
| `EIBAID` | `CicsContext.eibaid` |
| `EIBRESP` | Initialised to `0`; written by each CICS call |

### System service builtins

All implemented as explicit Python functions in `interpreter/cics/builtins/system.py`. Curried at `CicsLoweringStrategy` construction time to close over shared configuration.

| Verb | Implementation |
|---|---|
| `ASSIGN APPLID(f)` | Write configurable `applid` string to field |
| `ASSIGN SYSID(f)` | Write configurable `sysid` string to field |
| `ASKTIME ABSTIME(f)` | Write `time.time()` to field |
| `FORMATTIME ABSTIME(t) YYYYMMDD(d) TIME(h)` | Format Python `datetime` into fields |
| `INQUIRE PROGRAM(name)` | Check `program_cache`; set `EIBRESP=0` (found) or `EIBRESP=27` (PGMIDERR) |
| `WRITEQ TD` | Append to a list — stub |
| `HANDLE ABEND LABEL(x)` | No-op (logged) |
| `HANDLE ABEND CANCEL` | No-op (logged) |
| `ABEND ABCODE(c)` | Return `DispatchResult(kind=ABEND, abcode=c)` |

---

## Sub-project C — Transaction Dispatcher

### `CicsContext`

```python
@dataclass
class CicsContext:
    transid: str      # EIBTRNID — 4-char transaction ID
    commarea: bytes   # raw bytes; len → EIBCALEN
    eibaid: str       # 1-char attention identifier
```

Initial context for carddemo: `CicsContext(transid='CC00', commarea=b'', eibaid=DFHENTER)`. Entry transid is configurable.

### `DispatchResult`

```python
class DispatchKind(Enum):
    RETURN         = "return"
    RETURN_TRANSID = "return_transid"
    XCTL           = "xctl"
    ABEND          = "abend"

@dataclass
class DispatchResult:
    kind:     DispatchKind
    transid:  str | None = None   # RETURN_TRANSID
    commarea: bytes | None = None # RETURN_TRANSID, XCTL
    program:  str | None = None   # XCTL
    abcode:   str | None = None   # ABEND
```

Static `kind` field — no `isinstance` dispatch.

### Lowering of CICS flow control verbs

All emitted by `CicsLoweringStrategy` — no flow control knowledge in generic lowering:

| EXEC CICS | Lowers to |
|---|---|
| `RETURN` | `HALT` |
| `RETURN TRANSID(x) COMMAREA(y) LENGTH(n)` | `CALL_BUILTIN __cics_set_return_context(x, y, n)` + `HALT` |
| `XCTL PROGRAM(p) COMMAREA(y)` | `LOAD p` + `CALL_BUILTIN __cics_set_xctl_context(p, y)` + `HALT` |
| `ABEND ABCODE(c)` | `CALL_BUILTIN __cics_abend(c)` + `HALT` |

`__cics_set_return_context` and `__cics_set_xctl_context` are curried closures that write to an injected `DispatchResult` holder, which `run_cics()` reads after `vm.run()` returns.

### `run_cics()`

```python
def run_cics(
    program: LinkedProgram,
    context: CicsContext,
    screen_queue: Queue,
    input_queue: Queue,
) -> DispatchResult
```

Pre-populates `__params_region` with `context.commarea` bytes before execution. The existing LINKAGE SECTION binding (`LoadVar(name=VarName("__params_region"))`) picks it up transparently — same mechanism as `CALL BY REFERENCE`, set up by the dispatcher instead of a CALL instruction.

### Dispatcher loop

```python
while True:
    result = run_cics(program, context, screen_queue, input_queue, program_cache)
    if result.kind == DispatchKind.RETURN_TRANSID:
        input_event = input_queue.get()          # blocks — waits for terminal
        program = program_cache[transid_to_program[result.transid]]
        context = CicsContext(
            transid=result.transid,
            commarea=result.commarea,
            eibaid=input_event.eibaid,
        )
    elif result.kind == DispatchKind.XCTL:
        program = program_cache[result.program.strip()]
        context = CicsContext(
            transid=context.transid,
            commarea=result.commarea,
            eibaid=context.eibaid,
        )
    else:  # RETURN or ABEND
        break
```

`RETURN TRANSID` saves context and **blocks on the input queue** — does not immediately start a new execution. The new execution starts only when the input event arrives.

### Startup sequence

1. Parse `CARDDEMO.CSD` → `transid_to_program: dict[str, str]`
2. Eagerly pre-compile all programs → `program_cache: dict[str, LinkedProgram]`
   - Each program: pre-pass → ProLeap → `CicsLoweringStrategy` lowering
3. Fail fast if any program source is missing or fails to compile
4. Begin dispatcher loop at entry transid (`CC00` for carddemo)

### PCT resolution

- `RETURN TRANSID(x)` → `transid_to_program[x]` → `program_cache[name]`
- `XCTL PROGRAM(p)` → `program_cache[p.strip()]` directly (program name resolved at runtime from COBOL field)

### Codebase location

```
interpreter/cics/
    dispatcher.py    # run_cics(), dispatcher loop, CicsContext, DispatchResult, PCT loading
    builtins/
        flow.py      # __cics_set_return_context, __cics_set_xctl_context, __cics_abend
        system.py    # __cics_assign, __cics_asktime, __cics_formattime, __cics_inquire, __cics_writeq_td
```

---

## Sub-project D — VSAM File Engine

### Backing store

One `SortedDict` (from `sortedcontainers`) per dataset, keyed by raw key bytes, value is the raw fixed-width record bytes. Loaded from ASCII flat files at dispatcher startup.

### FCT configuration

YAML config file maps dataset names to file paths and record metadata:

```yaml
datasets:
  ACCTDAT:
    path: app/data/ASCII/acctdata.txt
    record_length: 300
  CARDDAT:
    path: app/data/ASCII/carddata.txt
    record_length: 150
  # … etc
```

Key offset and length come from `RIDFLD` and `KEYLENGTH` options at call time — not stored in config.

### Browse cursors

Keyed by `(task_id, file_name, cursor_id): int` — integer index into the sorted key list. `STARTBR` finds insertion point via `bisect`. `READNEXT` increments, `READPREV` decrements, `ENDBR` removes the entry.

### VSAM operations → builtins

All curried over the VSAM engine instance. `RIDFLD` and `INTO`/`FROM` data references are resolved by the strategy at lowering time — builtins receive typed `TypedValue` arguments, no raw memory access.

| EXEC CICS | Builtin |
|---|---|
| `READ FILE(f) INTO(t) RIDFLD(k) KEYLENGTH(n) RESP(r)` | `__cics_read` |
| `WRITE FILE(f) FROM(s) RIDFLD(k) RESP(r)` | `__cics_write` |
| `REWRITE FILE(f) FROM(s) RESP(r)` | `__cics_rewrite` |
| `DELETE FILE(f) RIDFLD(k) RESP(r)` | `__cics_delete` |
| `STARTBR FILE(f) RIDFLD(k) KEYLENGTH(n) RESP(r)` | `__cics_startbr` |
| `READNEXT FILE(f) INTO(t) RIDFLD(k) RESP(r)` | `__cics_readnext` |
| `READPREV FILE(f) INTO(t) RIDFLD(k) RESP(r)` | `__cics_readprev` |
| `ENDBR FILE(f) RESP(r)` | `__cics_endbr` |

`EIBRESP` is written via the EIB reference held by the CICS runtime after each operation.

### Codebase location

```
interpreter/cics/
    vsam/
        engine.py    # SortedDict VSAM engine, FCT YAML loading
        fct.py       # FCT config dataclass
    builtins/
        vsam.py      # all VSAM builtins (curried over engine)
```

---

## Sub-project E — BMS Screen Engine

### Integration

`bms-tools` integrated as a **git submodule**. `BmsMapSet/BmsMap/BmsField` models loaded at `CicsLoweringStrategy` construction time from all `.bms` files in carddemo:

```python
bms_maps: dict[str, BmsMapSet]  # mapset name → model
```

### Queues

The BMS engine communicates exclusively through two queues — the runtime has no terminal knowledge:

- **Screen queue (outbound):** `SEND MAP` posts `{mapset, map, fields: dict[str, str]}`. Whatever sits on the other side (stub, text console, TUI, web frontend) is outside the runtime.
- **Input queue (inbound):** `RECEIVE MAP` blocks on it. Receives `{map, fields: dict[str, str], eibaid: str}`. The CICS runtime writes `eibaid` into the EIB before returning to the program.

The input queue is the **same queue** the dispatcher blocks on between pseudo-conversational turns.

### SEND MAP lowering

At lowering time, strategy iterates the `BmsMapSet` fields for the given map and emits a `LOAD` per output field from the `FROM` data area. All loaded values passed as typed arguments to `__cics_send_map`. No raw memory access in the builtin.

### RECEIVE MAP write-back

Field values arrive from the input queue at **runtime** — not knowable at lowering time. `__cics_receive_map` is curried over `bms_maps` and `input_queue`. It blocks on the queue, then writes each field value into the `INTO` data area by offset using the `BmsMapSet` layout. Requires write access to VM memory via `vm: VMState` (already available to all builtins).

### SEND TEXT

`EXEC CICS SEND TEXT FROM(f) LENGTH(n)` — post raw text string to screen queue. No BMS map involved.

### Codebase location

```
interpreter/cics/
    bms/
        loader.py    # load .bms files via bms-tools submodule into dict[str, BmsMapSet]
    builtins/
        screen.py    # __cics_send_map, __cics_receive_map, __cics_send_text (all curried)
```

---

## Testing Strategy

All implementation follows **TDD** — failing test first, then implementation.

### Unit tests (`tests/unit/cics/`)

- **Pre-pass:** string-in → string-out assertions. DFHEIBLK injection at correct line, DFHRESP substitution, no mutation of EXEC CICS bodies.
- **VSAM engine:** load from fixture ASCII file, assert READ/WRITE/REWRITE/DELETE/browse operations on SortedDict.
- **Each CICS builtin:** stub queues and VSAM engine. Assert on TypedValue arguments and return values.

### Integration tests (`tests/integration/cics/`)

Full dispatcher runs with scripted input queues. Assert on screen queue events and final `DispatchResult`. These are the fitness function.

Example: sign-on flow — start at `CC00`, push `{fields: {USERIDID: 'USER1', PASSWDID: 'PASS'}, eibaid: DFHENTER}` to input queue, assert SEND MAP events for main menu, assert XCTL targets correct program.

---

## Full Codebase Layout

```
interpreter/cics/
    __init__.py
    preprocessor.py
    strategy.py
    dispatcher.py
    copybooks/
        DFHEIBLK.cpy
        DFHAID.cpy
        DFHBMSCA.cpy
    builtins/
        __init__.py
        flow.py
        system.py
        vsam.py
        screen.py
    vsam/
        __init__.py
        engine.py
        fct.py
    bms/
        __init__.py
        loader.py

tests/unit/cics/
tests/integration/cics/
```

bms-tools: git submodule at `vendor/bms-tools`, referenced by `interpreter/cics/bms/loader.py`.
