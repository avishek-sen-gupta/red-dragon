# USE AFTER STANDARD ERROR/EXCEPTION Declaratives — Design (red-dragon-m0oa.4)

**Status:** Designed (2026-06-18). Approach A (lowering-time injection), approved. Awaiting spec review → implementation plan.

**Goal:** When an I/O statement on a file completes with an error/exception status and the
statement has no applicable `AT END` / `INVALID KEY` clause, invoke the matching
`USE AFTER STANDARD ERROR/EXCEPTION` declarative procedure, then continue with the
statement after the failed I/O. Closes the "DECLARATIVE NOT EXECUTED" NIST cluster
(red-dragon-m0oa.4; surfaced by the CCVS tracer, e.g. SQ103A `SEQ-TEST-GF-10`).

**Driver:** NIST-85 file-I/O conformance (red-dragon-m0oa). Declaratives sections are already
serialized, lowered, and excluded from normal flow (red-dragon-m0oa.3); this adds the USE-clause
data and the runtime trigger that m0oa.3 deferred.

## Scope

In scope — the forms the NIST corpus actually uses (ERROR and EXCEPTION are synonyms in COBOL-85):
- `USE AFTER [STANDARD] ERROR/EXCEPTION [PROCEDURE] ON <file> [<file2> …]` (named file, incl. multiple files) — ~78 occurrences.
- `USE AFTER … PROCEDURE INPUT | OUTPUT | I-O | EXTEND` (open-mode scoped) — ~5.
- `USE GLOBAL AFTER … ON <file>` (GLOBAL) — ~4.

Out of scope (separate ticket): `USE FOR DEBUGGING` (~40 occurrences) — a distinct debug-line
declarative with different trigger semantics (`getUseDebugStatement()`), not error/exception.

## Architecture — Approach A (lowering-time injection)

All logic lives in the COBOL frontend (no core-VM change, per the standing constraint). A USE
registry is built once from the declaratives; `lower_io` injects a conditional PERFORM of the
matching USE section after each I/O verb that has no explicit `AT END`/`INVALID KEY` clause. The
USE PERFORM reuses the existing section-PERFORM continuation mechanism (`emit_perform_branch`).
Precedence falls out for free: an explicit clause means no injection.

## Components

### 1. Bridge — serialize the USE clause (`StatementSerializer`/`AsgSerializer`)
For each `Declarative`, read `decl.getUseStament()`:
- If `getUseType()` is the DEBUG form → skip (out of scope).
- Else `ua = getUseStament().getUseAfterStatement()`; emit a `"use"` object on the serialized
  declarative section:
  ```json
  "use": {
    "global": <ua.isGlobal()>,
    "target": "FILE" | "INPUT" | "OUTPUT" | "I-O" | "EXTEND",   // from AfterOn.getAfterOnType() (INPUT_OUTPUT -> "I-O")
    "files": ["SQ-FS1", ...]                                     // AfterOn.getFileCalls() names; present only when target == FILE
  }
  ```
The declarative section is already serialized (its paragraphs/statements); this adds `use`.

### 2. Python ASG (`interpreter/cobol/asg_types.py`)
`CobolSection` (declaratives entries) gains an optional `use: UseClause | None`, where
`UseClause = {global: bool, target: str, files: tuple[str, ...]}`, parsed in `from_dict`.

### 3. USE registry (built in `lower_procedure.lower_procedure_division`)
From `asg.declaratives`, build and stash on the EmitContext:
```
use_by_file:   dict[str, str]   # FILE-NAME (upper) -> section label "section_<name>"
use_by_mode:   dict[str, str]   # "INPUT"/"OUTPUT"/"I-O"/"EXTEND" -> section label
use_global:    str | None       # GLOBAL section label
```
(A file/mode maps to at most one USE procedure per program — last-wins with a warning if duplicated.)

### 4. Open-mode runtime query — new builtin `__cobol_file_open_mode(file) -> str`
Open-mode USE applies to whichever file is open in that mode at the I/O point, which is a runtime
fact. The IO provider already receives the mode in `open(file, mode)`; expose the current mode via
a provider method and a `__cobol_file_open_mode` builtin returning `"INPUT"/"OUTPUT"/"I-O"/"EXTEND"`
(or `""` if closed). Used only when the program has any open-mode USE.

### 5. Trigger helper — `emit_use_trigger(ctx, file_name, status_reg, has_explicit_clause, materialised)`
Shared helper in `lower_io`. No-op when `has_explicit_clause` is true or no USE applies. Otherwise
emits (resolving the section by precedence: named-file → open-mode → global):
```
err = (status_reg[0:1] != "0")          # error/exception: status class 1..9 (00/04/05 = success/info)
BranchIf err -> use_lbl, skip_lbl
use_lbl:
    <emit_perform_branch to the resolved USE section>   # SetContinuation + Branch; returns to skip_lbl
skip_lbl:
    ...
```
Named-file and GLOBAL resolve statically. Open-mode resolves at runtime: if any `use_by_mode`
exists, emit `m = __cobol_file_open_mode(file)` and a small branch chain selecting the matching
section. The first-digit-not-'0' test treats `10` (AT END) and `2x` (INVALID KEY) as triggering
when unhandled — correct COBOL: a statement with no `AT END`/`INVALID KEY` lets the USE fire.

### 6. Wire into the I/O verbs (`lower_io`)
Call `emit_use_trigger` after the status is known in `lower_read`, `lower_write`, `lower_rewrite`,
`lower_delete`, `lower_start`, `lower_open`, `lower_close`, passing
`has_explicit_clause = bool(stmt.at_end or stmt.not_at_end or stmt.invalid_key or stmt.not_invalid_key)`
(always `False` for OPEN/CLOSE, which have no such clauses).

## Data flow
I/O verb → `__cobol_io_status` → file-status field update (unchanged) → `emit_use_trigger`: if
error and no explicit clause and a USE matches, PERFORM the USE section (which may inspect the
file status, set flags, etc.) then fall through to the statement after the I/O.

## Error handling / edge cases
- No USE registered for the file/mode/global → no injection; status propagates exactly as today.
- Explicit `AT END`/`INVALID KEY` present → no injection (precedence).
- Nested I/O inside the USE procedure: out of scope (NIST USE procedures are simple status checks);
  no re-entrancy guard in this pass — note as a known limitation.
- DEBUG declaratives: skipped at serialization.

## Testing (TDD — failing test first for each)
Integration tests (`tests/integration/test_cobol_use_declaratives.py`), each observing a WS flag the
USE section sets (decoded from the region), so they fail before the trigger exists:
1. **Named-file USE fires on error:** force an I/O error on a file with `USE … ON <file>` (e.g. WRITE to an INPUT-opened file → status 48, or DELETE a missing record) → the USE section runs (flag set).
2. **Precedence:** a READ with an explicit `AT END` *and* a USE on the file → at-EOF the `AT END` branch runs and the USE does **not** (flag unset).
3. **GLOBAL USE fires** when no named-file USE matches.
4. **Open-mode USE** (`ON OUTPUT`) fires for a file opened OUTPUT.
5. **Multi-file USE** (`ON F1 F2`) fires for both files.
6. **No USE → no change:** an I/O error with no declarative behaves as today (status propagates).
Plus a bridge serialization check (the `use` object shape) and a tracer re-run confirming SQ103A's
`SEQ-TEST-GF-10` "DECLARATIVE NOT EXECUTED" failure is resolved.

## Staging (keeps each commit green)
1. Bridge: serialize `use` (+ Java rebuild). 2. ASG `UseClause` + parse. 3. Registry + named-file
trigger + tests 1/2/6. 4. GLOBAL (test 3). 5. Open-mode builtin + trigger (tests 4). 6. Multi-file
(test 5). 7. Full suite + tracer re-measure.

## Out of scope
- `USE FOR DEBUGGING` (separate ticket).
- USE-procedure re-entrancy / nested-I/O recovery beyond simple status inspection.
- No core-VM changes; no change to non-COBOL frontends.
