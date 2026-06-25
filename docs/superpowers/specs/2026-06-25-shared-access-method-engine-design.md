# Shared Access-Method Storage Engine — Design

**Status:** Designed (2026-06-25). Brainstormed for the mainframe stack (red-dragon +
jackal + cicada + squall). Awaiting user review.

**Repo:** red-dragon (the shared substrate the mainframe stack vendors). Consumers
(jackal/cicada/squall) bump the submodule to adopt it.

## What this builds (plain terms)
One **faithful, shared engine** for COBOL file input/output — opening datasets and
reading/writing their records — that every part of the mainframe stack uses, instead of the
three divergent paths that exist today. "Faithfulness of operations" is the bar: the file
operations must behave like real mainframe access methods (QSAM for sequential, VSAM for
keyed/relative). Observability/tracing is **explicitly deferred** to a later effort; the
JCL/dataset *catalog* (DSN, DISP, GDG, PDS) stays in jackal. This engine is just the
**access methods**: open / read / write / rewrite / delete / browse, done correctly.

## Driver (why now)
The mainframe stack reaches storage **three divergent ways**, and that divergence is about to
get worse as the dataset roadmap (GDG, PDS, ESDS, AIX, SORT, IEBGENER) lands:
- **COBOL execution** → `RealFileIOProvider` → the drivers in `interpreter/cobol/file_drivers.py`.
- **jackal IDCAMS** → imports `IndexedDriver`/`SequentialDriver` directly and drives them itself.
- **cicada CICS** → an entirely **separate `VsamEngine`** (`cics/vsam/engine.py`) that
  **duplicates** the KSDS logic of `IndexedDriver`, fused with CICS-specific semantics.

Consolidating onto one faithful engine — before those features pile on — means each new
capability plugs into one contract instead of widening the divergence.

## The crux: a *neutral* access-method outcome
The three consumers disagree on **how a file operation's result is reported**:
- COBOL drivers return **`IOResult.status`** = a COBOL **FILE STATUS** string (`"00"` ok,
  `"10"` AT END, `"22"` dup key, `"23"` not found, …).
- cicada's `VsamEngine` returns **EIBRESP** ints (`RESP_NORMAL=0`, `NOTFND=13`, `ENDFILE=20`,
  `DUPREC=14`, `IOERR=17`, …).

These are two vocabularies for the **same underlying conditions**. Today red-dragon's
`IOResult` bakes the COBOL vocabulary into the driver layer — which is exactly why cicada
couldn't share it and wrote its own engine.

**Decision:** the shared engine returns a **neutral outcome** — the underlying access-method
*condition*, not any consumer's status vocabulary. Each consumer's thin **adapter** maps the
neutral condition to its own vocabulary. This is the single most important interface decision;
it is what makes the engine genuinely shareable.

```
NeutralOutcome.condition ∈ {
    OK, END_OF_FILE, NOT_FOUND, DUPLICATE_KEY, KEY_SEQUENCE_ERROR,
    NO_SPACE, INVALID_KEY_LENGTH, IO_ERROR, ... }   # the access-method conditions
plus: data: bytes | None   (record bytes on a successful read; None for write-side verbs)
```
- COBOL adapter: `condition → FILE STATUS` (`OK→"00"`, `END_OF_FILE→"10"`, `NOT_FOUND→"23"`, …).
- CICS adapter (cicada, later): `condition → EIBRESP` (`OK→0`, `NOT_FOUND→13`, `END_OF_FILE→20`, …).

(Note: `IOResult.data` is `str | None` today; the neutral core is **bytes-oriented** — byte
fidelity is the dataset model — and the COBOL adapter handles the byte↔str boundary it needs.)

## Scope

**In scope (this first piece — behavior-preserving consolidation):**
- A neutral **access-method engine** in red-dragon: formalize the existing
  `FileOrganizationDriver` contract + the **PS / KSDS / RRDS** drivers behind one component
  with a **factory** ("give me a reader/writer for this backing store + organization"), and
  a **neutral outcome** type the engine returns.
- Re-express the **COBOL `CobolIOProvider`** path in terms of the neutral engine: the COBOL
  adapter maps neutral conditions → FILE STATUS, preserving today's behavior exactly.
- Route **jackal IDCAMS** through the engine's access API instead of importing drivers and
  hand-rolling status handling. (jackal-side change, bumped via the submodule.)
- **Behavior-preserving:** red-dragon's full suite + jackal's suite are the guard. No
  observable change to any program's output.

**Out of scope (deliberately deferred — each its own follow-on):**
- **Observability / tracing** of I/O operations. (The reason the engine exists *long-term*,
  but not this piece.)
- **Fidelity hardening** — correcting status-code gaps and record-format/LRECL bugs (e.g.
  jackal's REPRO assuming PS-LRECL == KSDS-record-size). Done *after* consolidation, in
  focused, individually-tested steps, so the structural refactor and behavior changes don't
  blur the test guard.
- **cicada's `VsamEngine` migration** onto the engine. Its CICS semantics (EIBRESP mapping,
  FCT/enable-disable, task-scoped browse cursors, last-read-for-update) stay as a cicada
  **CICS adapter** — those were never storage. But its **storage core does not simply "fold
  in"**: `VsamEngine` and red-dragon's `IndexedDriver` are **two different access
  architectures over the *same* on-disk format**:
  - red-dragon's drivers are **file-resident** — records live on disk (a flat file of
    fixed-length records, sorted by key; every op seeks the file).
  - `VsamEngine` is **in-memory + a pluggable backend** — records live in a `SortedDict`,
    with `FileBackend` write-through (or `InMemoryBackend`, never persisting).
  - **The on-disk format is identical** (concatenation of fixed-length records;
    `read_flat_file`/`write_flat_file` round-trips the same byte image the drivers read). So
    the two are **data-compatible today** — that shared format is the merge anchor — but the
    **access code is not reusable as-is**.

  Merging them is therefore a real decision, **deferred to the cicada follow-on**: choose the
  **canonical access architecture** (file-resident vs in-memory+backend) — a choice with CICS
  implications (in-transaction record visibility, performance, write-through persistence
  semantics), to be made with cicada's CICS suite as the guard. What makes the merge
  *possible* is that **`FileOrganizationDriver` is an abstract Protocol — it dictates
  *operations*, not file-resident-vs-in-memory** — so cicada's storage (kept in-memory, or
  moved to file-resident) can become a `FileOrganizationDriver` implementation behind the same
  neutral contract. **This first piece presumes neither architecture and touches none of
  this** — jackal and COBOL are already both on the file-resident drivers.
- The jackal **catalog** (`jackal-vxb`: DSN/DISP/GDG/PDS) — a jackal consumer of this engine.
- New organizations **ESDS / AIX / PDS** — new drivers under the same contract, later.
- **squall** adoption.

## Components

1. **`FileOrganizationDriver` (contract)** — already exists in `file_drivers.py`. Keep its
   uniform method set (`open/close/read_seq/read_key/start/write/rewrite/delete`) but have the
   methods return the **neutral outcome** instead of the COBOL-flavored `IOResult`.
2. **The three drivers** (`SequentialDriver` PS, `IndexedDriver` KSDS, `RelativeDriver` RRDS) —
   re-expressed to return neutral outcomes. Logic unchanged; only the result type changes.
3. **`NeutralOutcome`** — a frozen dataclass: `condition: AccessCondition` (enum) + `data:
   bytes | None`. The shared vocabulary.
4. **An access factory / facade** — selects the driver for a `(backing store, organization,
   open mode, record shape)` and returns an opened reader/writer. The "one door" consumers use.
5. **COBOL adapter** — the `CobolIOProvider` implementation (today's `RealFileIOProvider`,
   refactored): drives the engine and maps `AccessCondition → FILE STATUS` for the VM. This is
   the existing seam; COBOL execution is unchanged externally.
6. **(later) CICS adapter** in cicada and **catalog** in jackal — out of scope here, but the
   neutral contract is shaped so both drop in without touching the engine.

## Data flow (COBOL, the one consumer in this piece)
```
COBOL IR executes  →  __cobol_* I/O call  →  CobolIOProvider (COBOL adapter)
   → access factory picks driver by org  →  driver does record I/O  →  NeutralOutcome
   → adapter maps condition → FILE STATUS, returns to the VM   (behaviour identical to today)
```
jackal IDCAMS calls the **same factory + drivers** directly (it's Python, not COBOL) and maps
the neutral outcome to whatever it needs (IDCAMS uses MAXCC, derived from success/failure).

## Error handling
- The engine **fails loud** on genuinely unsupported operations/organizations (no silent
  fallback that fabricates a wrong status). A neutral `IO_ERROR`/unsupported is a real outcome,
  not a swallowed exception.
- No `None` defaults; frozen/immutable outcome; no regex; FP core / imperative shell.
- The neutral condition set is **closed and explicit** — adding a condition is a deliberate
  enum change, not an ad-hoc string.

## Testing (TDD)
- **Behavior-preserving guard:** red-dragon's full suite (incl. the COBOL file-I/O integration
  tests) and jackal's suite must stay green — this is the proof that the neutral refactor
  changed *nothing* observable. Run both before merge.
- **Neutral-mapping unit tests:** each `AccessCondition` maps to the correct FILE STATUS in the
  COBOL adapter (`OK→"00"`, `END_OF_FILE→"10"`, `NOT_FOUND→"23"`, `DUPLICATE_KEY→"22"`, …),
  pinning the translation that replaces today's inline status strings.
- **Per-org access tests:** PS/KSDS/RRDS open/read/write/rewrite/delete/browse each return the
  correct neutral condition (e.g. reading past end → `END_OF_FILE`; `read_key` miss →
  `NOT_FOUND`; duplicate `write` → `DUPLICATE_KEY`).
- **Consumer-parity:** jackal IDCAMS REPRO (PS→KSDS) produces byte-identical output through the
  engine as before (the existing gated CardDemo e2e is the end-to-end witness).

## Constraints (red-dragon house rules)
- FP / frozen dataclasses; functional core / imperative shell; **no `None` defaults; no
  defensive guards (fail loud); no regex**.
- **Behavior-preserving** — the consolidation must not change any program's output; the full
  suites are the gate.
- Keep red-dragon **language-agnostic at the engine layer** — the engine knows "backing
  stores + records + access-method conditions", never "DSN", "DISP", "GDG", or "EIBRESP"
  (those live in the consumer adapters: jackal catalog, cicada CICS).
- Python 3.13, black, the real pre-commit hooks.

## Risks
- **The neutral refactor touches the COBOL I/O hot path** — every COBOL file op flows through
  it. Mitigation: behavior-preserving by construction (the drivers' logic is unchanged; only
  the result type + a mapping layer change), guarded by the full COBOL file-I/O test suite +
  jackal's gated e2e.
- **`IOResult` is COBOL-status-flavored and widely referenced.** Decide whether the neutral
  outcome *replaces* `IOResult` at the driver layer (with the COBOL adapter producing the old
  `IOResult` shape for the VM) or sits beside it. The plan should make the driver→adapter
  boundary explicit so VM-facing types don't change.
- **`data: str | None` vs bytes.** The neutral core is bytes; the COBOL adapter owns the
  byte↔str boundary it currently relies on. The plan must keep the VM-facing data type stable.
- **Scope creep into fidelity fixes.** Resist — this piece is *consolidation only*; faithfulness
  hardening is the explicit fast-follow so the test guard stays meaningful.
- **The "merge" is not a merge — it's a canonical-architecture choice (deferred).** Do not
  assume cicada's `VsamEngine` storage code is reusable: it is a different access architecture
  (in-memory+backend) from the drivers (file-resident). They share only the on-disk format.
  This first piece must NOT bake in "file-resident" as the only possible strategy — the
  `FileOrganizationDriver` Protocol stays architecture-neutral so a future in-memory variant
  can implement it. The actual unification (which architecture wins) is cicada follow-on work
  with its own CICS-semantics tradeoffs and test guard; it is explicitly NOT decided here.

## Bookkeeping
- This is a **red-dragon** epic (storage engine). `jackal-vxb` is **re-scoped** to "the jackal
  dataset *catalog* that consumes this engine" — a follow-on, tracked in jackal.
- Follow-ons (separate specs/issues): fidelity hardening; cicada `VsamEngine` split + CICS
  adapter; jackal catalog; ESDS/AIX/PDS drivers; observability/tracing.
