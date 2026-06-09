# CICS Support in RedDragon

RedDragon emulates the **CICS online tier** — the pseudo-conversational, screen-driven,
VSAM-backed transaction environment of a mainframe — closely enough to run **real,
unmodified COBOL programs** end-to-end through the interpreter. The reference workload is
the Apache-licensed [`aws-mainframe-carddemo`](https://github.com/aws-samples/aws-mainframe-carddemo)
online tier: sign-on, menu, account view/update, and transaction add all execute through
the pipeline described here.

This document covers three things:

1. **The CICS pre-pass** and how it slots into RedDragon's normal COBOL compilation phases.
2. **The transaction dispatcher loop** that routes between programs across pseudo-conversational turns.
3. **VSAM support** — the in-memory KSDS engine, its pluggable persistence backends, and the copybook-driven dump CLI.

A hard architectural invariant underlies all of it: **none of this touches the core RedDragon
engine.** There are zero edits to `interpreter/vm/**`, `ir.py`, `run.py`, `executor.py`, or
`cfg.py`. Every CICS-specific behaviour lives in `interpreter/cics/**`, the COBOL frontend
(`interpreter/cobol/**`), the ProLeap Java bridge, and tests. CICS verbs reach the VM only
through ordinary IR (`CallFunction` to registered builtins) — the same mechanism any language
frontend uses.

---

## 1. The CICS pre-pass and the compilation phases

### 1.1 The normal RedDragon COBOL pipeline

A COBOL program normally compiles through these phases:

```
source bytes
   │  ProLeapCobolParser.parse  (Java bridge: proleap-cobol-parser → JSON ASG)
   ▼
CobolASG  (data_fields, procedure statements, …)
   │  CobolFrontend.lower  (statement_dispatch → emit IR per statement)
   ▼
IR instruction list
   │  build_cfg → build_registry
   ▼
CFG + registry
   │  run_linked  (VM execution)
   ▼
result
```

EXEC CICS commands are a problem for this flow because ProLeap treats an
`EXEC CICS … END-EXEC` block as an **opaque envelope** — it does not parse the CICS verb or
its options. CICS support is therefore split into a **text pre-pass** (before ProLeap) plus
a **lowering strategy** (during frontend lowering) that turns each opaque block into IR.

### 1.2 The pre-pass — `interpreter/cics/preprocessor.py`

`apply_cics_prepass(source: str) -> str` runs **before** ProLeap sees the source and does two
purely textual things that ProLeap/COBOL cannot do for themselves:

- **`inject_dfheiblk`** — inserts `COPY DFHEIBLK.` immediately after `WORKING-STORAGE SECTION.`
  so the program's references to the Execute Interface Block (`EIBRESP`, `EIBCALEN`, `EIBAID`,
  `EIBTRNID`, …) resolve to a real copybook-defined layout. This mirrors what the IBM CICS
  translator does.
- **`substitute_dfhresp`** — replaces every `DFHRESP(name)` with its numeric EIBRESP code (e.g.
  `DFHRESP(NOTFND)` → `13`). The code table is the standard contiguous IBM 0–44 set plus the
  higher named codes the workload references; each is unique so two distinct conditions can
  never compare-equal after substitution. An unknown/typo'd condition substitutes a sentinel
  (`9999`) that can never match a real response, rather than `0` (= NORMAL) which would let a
  bogus condition masquerade as the happy path.

The pre-pass is a deliberate, single, explicit step **at the boundary**: callers run
`apply_cics_prepass(...).encode()` once and hand the result to the compiler. `compile_cics_program`
and `run_carddemo_region` both document that their `source` arguments are already pre-passed, so
there is no double-prepassing.

> These two transforms are the *only* regex/text surgery in the CICS path. Everything else — the
> CICS verb, its options, literal-vs-data-name — is recovered **structurally** (see §1.3). The
> EXEC envelope itself is *not* peeled by regex; it is matched inside the Lark grammar.

### 1.3 EXEC CICS as a structured statement — `cics_parser.py`

When ProLeap surfaces an `EXEC CICS` block, the COBOL frontend builds an `ExecCicsStatement`
(`interpreter/cobol/cobol_statements.py`) from the block's raw text. `ExecCicsStatement.from_dict`
calls **`parse_exec_cics_text(text) -> (verb, {OPTION: CicsOperand | None})`**.

`parse_exec_cics_text` is a **Lark PEG/LALR grammar** (`interpreter/cics/cics_parser.py`), not a
pile of regexes:

- The `EXEC CICS … END-EXEC` envelope is matched as anchored grammar terminals.
- The **verb** is a grammar construct: a single word (`READ`, `WRITE`, `XCTL`, `RETURN`, …) or one
  of a small set of **compound verbs** (`SEND MAP`, `SEND TEXT`, `RECEIVE MAP`,
  `HANDLE ABEND/CONDITION/AID`), stitched in the grammar/transformer — not by Python string-joining.
- Each option value is a **`CicsOperand(text, is_literal)`**. The `is_literal` flag comes
  *structurally* from whether the grammar matched a quoted `STRING` terminal or a bare `CHARS`
  operand — it is **never** re-derived downstream by sniffing quote characters. This distinction is
  load-bearing: e.g. `MAP('SGNMAP')` (a literal map name) must not be confused with a same-named
  working-storage group.
- Nested/balanced parentheses (subscripts `PROGRAM(PGM(WS-OPT))`, reference-mod `FROM(WS-MSG(1:8))`)
  are handled by the recursive `value`/`value_part` rules, not by regex paren-balancing.
- Inline `*>` COBOL comments that the bridge folds into the joined EXEC text are stripped (a clean
  drop — comments carry no semantics) while preserving the trailing `END-EXEC` anchor.

### 1.4 The lowering strategy — `strategy.py`

`CobolFrontend` accepts an injected **`ExecCicsStrategy`** (a `Protocol`). When the statement
dispatcher (`statement_dispatch.py`) meets an `ExecCicsStatement`, it calls
`ctx.exec_cics_strategy.lower(ctx, stmt, materialised)`; at procedure entry it calls
`ctx.exec_cics_strategy.on_procedure_entry(...)`.

Two implementations exist:

- **`CatchAllLoweringStrategy`** (default) — a null object. It logs a warning and emits no IR for
  every EXEC CICS statement. This is what a non-CICS COBOL compile uses, so the CICS machinery is
  inert unless explicitly opted in.
- **`CicsLoweringStrategy`** — the real one, injected for CICS mode. Its constructor registers the
  CICS **service builtins** into the VM's `Builtins.TABLE` (closures over the region's runtime
  state — VSAM engine, screen/input channels, context/result holders), then `lower()` translates
  each verb into ordinary IR.

The translation pattern is uniform: **each CICS verb lowers to a `CallFunction` to a registered
builtin** (`__cics_read`, `__cics_send_map`, `__cics_set_xctl_context`, …), with operands resolved
to registers first. This is why the core VM needs no changes — a CICS command is just a function
call in the IR.

`on_procedure_entry` emits a single `CallFunction __cics_init_eib` so the EIB is initialised before
the first statement runs.

`lower()` dispatches by verb family:

| Verb family | Verbs | Lowers to |
|---|---|---|
| Flow control | `RETURN [TRANSID][COMMAREA]`, `XCTL PROGRAM COMMAREA`, `ABEND` | `__cics_set_return_context` / `__cics_set_xctl_context` / `__cics_abend`, then a `Return_` so control leaves the program |
| BMS screen | `SEND MAP`, `RECEIVE MAP`, `SEND TEXT` | `__cics_send_map` / `__cics_receive_map` / `__cics_send_text`, passing the symbolic map's leaf field names |
| System | `ASSIGN`, `ASKTIME`, `FORMATTIME`, `INQUIRE`, `WRITEQ TD`, `HANDLE ABEND` | the matching `__cics_*` builtin; output sub-options (e.g. `ASSIGN APPLID(field)`) are written back into their fields |
| File control (VSAM) | `READ`, `WRITE`, `REWRITE`, `DELETE`, `STARTBR`, `READNEXT`, `READPREV`, `ENDBR` | the matching `__cics_*` builtin (see §3) |

Operand handling helpers make the verb code small and uniform:

- **`emit_operand_value`** — resolve an operand to a register holding its *runtime value*. A bare
  data-name that resolves to a field is decoded; a quoted literal (or unresolved name/numeric) emits
  a `Const`. A literal **never** consults the field table (the BMS name-collision fix).
- **`emit_copy_in`** — `LoadRegion` a data item's raw bytes into a register (for `FROM`/`COMMAREA`/`RIDFLD`).
- **`emit_copy_back_str`** / **`emit_resp_writeback`** — encode a builtin's result back into a named
  field. `emit_resp_writeback` writes the returned EIBRESP code into `EIBRESP` (always) and into the
  `RESP(name)` field when present, packed per that field's layout (e.g. `PIC S9(8) COMP`).

`HANDLE CONDITION` and `HANDLE AID` are currently explicit **no-ops** — full runtime-dispatch
machinery is a deferred follow-up
(`docs/superpowers/plans/2026-06-07-cics-handle-condition-machinery.md`).

### 1.5 Compiling a region program — `bootstrap.py`

`compile_cics_program(source, parser, strategy, …)` produces a `LinkedProgram` ready for `run_cics`.
It compiles the main program as a module with the shared `CicsLoweringStrategy` injected, then —
when a `program_source_dir` is supplied — uses RedDragon's ordinary project machinery (import
extractor + resolver + `link_modules`) to **transitively resolve and link the program's `CALL`
targets**, each compiled with the *same* strategy so EXEC CICS in a subprogram lowers identically.
A callee that fails to compile is skipped with a warning (its `CALL` falls back to the symbolic
path) rather than aborting the whole region. Callees with no COBOL source on disk (e.g. the IBM
Language Environment service `CEEDAYS`) are supplied as `extra_subprogram_sources` stubs
(`interpreter/cics/le_stubs.py`).

So the CICS additions reuse the normal compilation phases wholesale — pre-pass feeds ProLeap, the
strategy plugs into the existing statement-dispatch lowering, and subprogram linking is the stock
project linker. The only genuinely new compile-time artifacts are the pre-pass, the EXEC-CICS
grammar, and the lowering strategy.

---

## 2. The CICS transaction dispatcher loop

A CICS region is, at heart, a router: a terminal submits a transaction id (transid); CICS looks up
the program for that transid, runs it; the program ends by `RETURN`ing (optionally with a next
transid for the next keystroke), `XCTL`ing to another program, or abending; CICS decides what runs
next. RedDragon models this in `interpreter/cics/dispatcher.py`.

### 2.1 Shared types — `types.py`

```python
@dataclass
class CicsContext:          # state handed INTO each program execution
    transid: str
    commarea: bytes
    eibaid: str             # 1-char attention id (e.g. "\x7d" = DFHENTER / PF keys)

class DispatchKind(Enum):
    RETURN; RETURN_TRANSID; XCTL; ABEND

@dataclass
class DispatchResult:        # what a program execution produced
    kind: DispatchKind
    transid: str | None      # RETURN_TRANSID — next transid
    commarea: bytes | None   # RETURN_TRANSID / XCTL — carried state
    program: str | None      # XCTL — target program
    abcode: str | None       # ABEND — abend code
```

The flow-control builtins (`__cics_set_return_context`, `__cics_set_xctl_context`, `__cics_abend`)
populate a `result_holder` with the `DispatchResult` as a side effect of the program's `RETURN`/
`XCTL`/`ABEND`. The context-setting builtins read a `context_holder` so `__cics_init_eib` can seed
the EIB from the current `CicsContext`.

### 2.2 Running one program — `run_cics`

`run_cics(program, context, screen_queue, input_queue, *, context_holder, result_holder, max_steps)`
executes a single program for one turn:

- Seeds `context_holder[0]` so the EIB builtin can initialise `EIBTRNID`/`EIBCALEN`/`EIBAID`.
- Places the **COMMAREA bytes into an addressable VM region** (`rgn_commarea`) and binds it to the
  LINKAGE `DFHCOMMAREA` via the `__params_region` local, so the program's field reads resolve through
  it. EIB-ish locals (`__cics_transid`, `__cics_eibcalen`, `__cics_eibaid`) are set on the entry
  frame.
- Chooses an entry point: a linked region uses the bootstrap-recorded `entry_func_label` (so the main
  program's entry is unambiguous among many namespaced `func_*` labels); a standalone program falls
  back to the lone `func_*` predicate.
- Runs via the stock `run_linked` and returns the `DispatchResult` left in `result_holder` (defaulting
  to a plain `RETURN`).

### 2.3 The routing rule — `_advance_routing`

The single source of truth for "what runs next" is `_advance_routing(result, current_transid,
program_cache, transid_to_program)`:

- **`RETURN_TRANSID`** → resolve the next program via `transid_to_program[next_transid]`; the transid
  becomes the returned (stripped) transid. Unknown transid → `ABEND TRNI`.
- **`XCTL`** → switch to `program_cache[program]`; **the transid carries** (same task). Unknown
  program → `ABEND PGMI`.
- **anything else** (`RETURN`, `ABEND`) → terminal; returned unchanged.

It returns either a `(next_transid, next_program, next_commarea)` tuple (continue) or a terminal
`DispatchResult` (stop). Both the autonomous loop and the turn-by-turn API funnel through it, so the
routing semantics are defined exactly once.

### 2.4 Two ways to drive the region

**Autonomous loop — `_run_dispatcher_with_runner`.** A blocking `while True` that runs the current
program, applies `_advance_routing`, and continues until a terminal result. On a pseudo-conversational
`RETURN TRANSID` it blocks on `input_queue.get()` to receive the next terminal event, whose attention
key seeds the next `EIBAID`. This is the "real region" driver used by `run_carddemo_region`.

**Turn-by-turn — `CicsRegion`.** An explicit state machine over the *same* `_advance_routing`, for
callers (tests, tools) that want to drive one turn at a time without an unbounded blocking loop:

- `start(entry_transid, *, commarea, input_event)` — begin a task and run its first program.
- `step(*, input_event)` — run the current `(program, transid, commarea)` again.
- The caller supplies an `input_event` on the entry turn and after each `RETURN_TRANSID` (a fresh
  terminal input), and **omits** it after an `XCTL` (same task, no new terminal input). This mirrors
  pseudo-conversational reality.
- Unlike the loop, `CicsRegion` does **not** do a separate `input_queue.get()` for the EIBAID: the
  supplied `input_event` is both put on the queue (for `RECEIVE MAP`) and used directly to seed the
  context's `eibaid`. It exposes `transid` and `done` properties and supports a `min_commarea_len`
  pad so a successor program that indexes a larger COMMAREA than its predecessor returned reads
  in-bounds.

```
            ┌──────────────── _advance_routing ───────────────┐
            │  RETURN_TRANSID → next program via CSD map        │
 input_event│  XCTL          → named program, transid carries   │ terminal?
   ───────► run_cics ──► DispatchResult ─────────────────────► RETURN / ABEND ──► stop
            │  (loop blocks on input_queue.get for next turn;   │
            │   CicsRegion takes the next input_event instead)  │
            └───────────────────────────────────────────────────┘
```

### 2.5 Terminal channels — `terminal.py`

Program ↔ driver I/O goes through an explicit protocol rather than a raw queue. `ScreenChannel`
(outbound: `SEND MAP`/`SEND TEXT`) and `InputChannel` (inbound: `RECEIVE MAP`) are `put(item)` +
`get(block, timeout)` protocols; `queue.Queue` conforms, and `queue.Empty` is the "no item" signal.
Both the region-side screen builtins and the driver/test side use this protocol.

### 2.6 CSD and bootstrap

`parse_csd(path)` reads a CICS CSD into a `{transid: program}` mapping
(`DEFINE TRANSACTION(x) PROGRAM(y)`). `run_carddemo_region(...)` ties everything together: parse the
CSD (or take an explicit mapping), construct one shared `CicsLoweringStrategy` over the region's
runtime state, eagerly compile every distinct program named in the CSD into a `program_cache`
(fail-fast on a missing source), and run `_run_dispatcher_with_runner` from the entry transid.

---

## 3. VSAM support

The online programs read and write VSAM KSDS datasets (accounts, customers, card cross-reference,
transactions). RedDragon models the **logical KSDS** — keyed record access over fixed-length records
— not VSAM's physical Control Interval/Area block structure. The on-disk image is the raw
fixed-length-record format `IDCAMS REPRO` produces, which is also the seed format. Everything lives
in `interpreter/cics/vsam/`.

### 3.1 Configuration — `fct.py`

`DatasetConfig(path, record_length, key_offset=0, key_length=0)` describes one dataset; `FctConfig`
maps upper-cased dataset names to configs (`from_dict` / `from_yaml`). `key_offset` supports
**alternate-index paths whose key lives inside the record** (e.g. the CARD-XREF ACCT-ID at offset
25), and `key_length` optionally pins the slice width.

### 3.2 The engine — `engine.py`

`VsamEngine(config, backend=None)` holds one `SortedDict` per dataset, **keyed by the full record
bytes** (value == key), giving ordered iteration for browse. Key matching slices
`record[key_offset : key_offset + klen]`, where `klen` is the dataset's pinned `key_length` or the
operation's key length. With the defaults this is the historical offset-0 prefix match.

`load_all()` populates each dataset from `backend.load(name, cfg)`. Operations return CICS EIBRESP
codes (`RESP_NORMAL=0`, `RESP_NOTFND=13`, `RESP_DUPREC=14`, `RESP_ENDFILE=20`, `RESP_DISABLED=84`):

- **Point ops:** `read` (linear key-match → record + resp), `write` (DUPREC if the key exists, else
  insert), `rewrite` (no RIDFLD — the key is derived from the FROM record's own key field, mirroring
  write; NOTFND if absent), `delete`.
- **Browse ops** (implicit single cursor per `(task, file, cursor_id)`): `startbr` positions at the
  first key ≥ the search prefix — and crucially positions **past end-of-file** when no key qualifies,
  so the CardDemo "seek last record" idiom (`STARTBR` with `HIGH-VALUES` then `READPREV`) walks back
  to the final record. `readnext`/`readprev` use a "between-records" cursor with a recorded direction,
  so a `READNEXT → READPREV` reversal correctly steps back over the just-read record. `endbr` releases
  the cursor.

The engine stays a **pure bytes/int API** with no CICS or VM coupling — the VSAM service builtins
(`interpreter/cics/builtins/vsam.py`) adapt it to the IR calling convention and the EIBRESP
write-back. Critically, the engine is **counter-agnostic about record internals**: it returns whole
records and never interprets COBOL field structure (OCCURS/ODO etc.), exactly like real VSAM. Record
interpretation is the *reader's* job (the COBOL program, or the dump CLI in §3.5).

### 3.3 Persistence backends — `backend.py`

A small `VsamBackend` protocol owns persistence so the engine's working set (the `SortedDict`) stays
the in-memory source of truth while load/persist are pluggable:

```python
class VsamBackend(Protocol):
    def load(self, name, cfg) -> list[bytes]: ...
    def persist(self, name, cfg, records) -> None: ...
```

- **`InMemoryBackend`** (default) — `load` reads the seed `cfg.path`; `persist` is a no-op. The
  default engine writes **no files** and behaves byte-identically to a pure in-memory store.
- **`FileBackend(backing_dir)`** — `load` reads `<backing_dir>/<NAME>.dat` if present, else seeds from
  `cfg.path` (first run); `persist` write-throughs `<backing_dir>/<NAME>.dat`. The durable copy is kept
  **separate from the read-only seeds**, so seeds are never overwritten.

The engine calls `persist` **only after a successful mutation** (`write`/`rewrite`/`delete` on a
`RESP_NORMAL` path) — never after NOTFND/DUPREC/DISABLED, never on READ/browse. `flush_to(directory)`
snapshots every dataset to `<dir>/<NAME>.dat` regardless of backend.

### 3.4 The raw codec — `format.py`

The single source of the on-disk format, shared by the backends and `flush_to`:

- `read_flat_file(path, record_length) -> list[bytes]` — split the file into fixed-length records;
  missing file → `[]`; size-not-a-multiple → `ValueError` (loud "wrong copybook / wrong file" signal).
- `write_flat_file(path, records, record_length)` — validate each record's length, then write
  **atomically** (temp file in the same dir + `os.replace`) so a crash mid-write cannot truncate the
  dataset.

A flushed/persisted file round-trips through `read_flat_file` and is itself a valid seed.

### 3.5 The dump CLI — `dump.py`

The persisted `.dat` is not plain-text readable (EBCDIC text, zoned-decimal, COMP-3, binary). The
dump CLI is a **copybook-driven decoder** built primarily to debug end-to-end runs and reusable as a
general inspector:

```
python -m interpreter.cics.vsam.dump --data ACCTDAT.dat --copybook CVACT01Y.cpy \
       [--record NAME] [--format jsonl|block] [--jar PATH]
```

It is pure orchestration of existing parts — no new decode logic:

- **Layout sourcing** — wrap the copybook in a minimal program skeleton (`COPY <member>.` in
  WORKING-STORAGE), parse it via ProLeap, and `build_data_layout(asg.data_fields)` to get a
  `DataLayout`. `select_record_layout` picks the 01 record (by `--record`, or the sole 01). The
  **record length is derived** from `layout.total_bytes` — not a CLI argument.
- **`decode_record(layout, record)`** — a pure `DataLayout + bytes → dict`. Per leaf field it slices
  the record and dispatches on the field's category to the existing COBOL decoders
  (`EbcdicTable.ebcdic_to_ascii`, `decode_zoned`, `decode_comp3`, `decode_binary`); integer fields
  (no implied decimals) decode to `int`, others to `float`. Groups nest as dicts; REDEFINES emit both
  views; OCCURS become arrays. **OCCURS DEPENDING ON honors the counter** — it decodes `N` occurrences
  (clamped to `[occurs_min, max]`), never the fixed max, so leftover bytes in unused trailing slots are
  not presented as data. (This is exactly what a real program does on read — see §3.2: VSAM returns the
  whole record; the *reader* honors the counter.)
- **Renderers** — `jsonl` (default; one JSON object per record, jq-friendly) and `block` (human-readable
  `@offset name value 0xRAW` lines, for spotting EBCDIC/COMP-3/leading-zero bugs).

`COMP-1`/`COMP-2` (IEEE float) decode raises `NotImplementedError`; filtering is out of scope (pipe to
`jq`). The CLI requires the ProLeap JAR at dump time, the same gate as the end-to-end tests.

---

## 4. Design invariants

- **No core-engine edits.** Nothing under `interpreter/vm/**`, `ir.py`, `run.py`, `executor.py`,
  `cfg.py` is modified for CICS. CICS verbs reach the VM only as `CallFunction` IR to registered
  builtins.
- **Structure over text.** Aside from the two deliberate pre-pass transforms (DFHEIBLK inject,
  DFHRESP substitute) and inline-comment stripping, CICS parsing is a grammar — the verb, options,
  and literal-vs-data-name distinction are recovered structurally, never re-sniffed.
- **One routing rule.** `_advance_routing` is the sole definition of inter-program routing, shared by
  the autonomous loop and the turn-by-turn API.
- **Pure VSAM engine.** The engine is a bytes/int store that never interprets record internals;
  persistence is a pluggable backend; record decoding is the reader's concern.
- **Default behaviour unchanged.** A non-CICS COBOL compile uses the null-object strategy; a default
  `VsamEngine` writes no files. CICS and persistence are strictly opt-in.

---

## 5. File map

| Concern | Files |
|---|---|
| Pre-pass | `interpreter/cics/preprocessor.py` |
| EXEC CICS grammar | `interpreter/cics/cics_parser.py`; `ExecCicsStatement` in `interpreter/cobol/cobol_statements.py` |
| Lowering strategy | `interpreter/cics/strategy.py`; dispatch in `interpreter/cobol/statement_dispatch.py`, entry in `interpreter/cobol/lower_procedure.py` |
| Service builtins | `interpreter/cics/builtins/{flow,screen,system,vsam}.py` |
| Dispatcher / region | `interpreter/cics/dispatcher.py`, `interpreter/cics/bootstrap.py`, `interpreter/cics/types.py` |
| Terminal I/O | `interpreter/cics/terminal.py` |
| LE service stubs | `interpreter/cics/le_stubs.py` |
| VSAM | `interpreter/cics/vsam/{fct,engine,backend,format,dump}.py` |
| BMS maps | `interpreter/cics/bms/generate.py` (symbolic copybooks via the external bms-tools pipeline) |

### Related design docs

The original per-area specs and plans live under `docs/superpowers/`:
`2026-06-06-cics-emulation-design.md` (master), and the A–F area specs/plans (parse strategy, EIB
runtime, dispatcher, VSAM, BMS, field-ref wiring), plus `2026-06-09-vsam-file-persistence-design.md`
and `2026-06-09-vsam-dump-cli-design.md`.
