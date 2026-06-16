# COBOL DECLARATIVES Handling — Design

**Issue:** red-dragon-m0oa.3 (epic: red-dragon-m0oa, NIST-85 file I/O conformance)
**Date:** 2026-06-16

## Goal

Make the COBOL frontend recognize `DECLARATIVES` blocks so that normal program
execution begins at the first paragraph/section **after** `END DECLARATIVES`,
exactly as standard COBOL prescribes. This fixes 9 NIST programs that currently
"skip" because the interpreter starts execution inside a declaratives USE
procedure instead of the real program body.

Affected programs (all currently skip; should pass after this change):
`SQ212A`, `IX104A`, `IX108A`, `IX204A`, `IX216A`, `RL104A`, `RL111A`, `RL112A`, `RL119A`.

**Out of scope:** actually *triggering* `USE` procedures on I/O errors (the
event-driven semantics). That is a separate follow-up, red-dragon-m0oa.4, which
this design deliberately leaves for later but does not block.

## Background

A COBOL `PROCEDURE DIVISION` may open with a `DECLARATIVES … END DECLARATIVES`
block containing event-driven sections. Each declaratives section begins with a
`USE` statement (e.g. `USE AFTER STANDARD ERROR PROCEDURE ON <file>`) that tells
the runtime to invoke that section automatically on a matching event. Declaratives
code never runs in normal sequence; the program's real entry point is the first
element after `END DECLARATIVES`.

### Root cause (verified 2026-06-16)

ProLeap already excludes declaratives **sections** from `pd.getSections()`
(SQ212A reports 3 sections: `CCVS1`, `SECT-SQ212A-0002`, `CCVS-EXIT` — the
declaratives section `SECT-SQ212A-0001` is absent). The leak is at the
**paragraph** level:

- `pd.getParagraphs()` *includes* declaratives paragraphs.
- The bridge's `findStandaloneParagraphs()` computes `allParagraphs −
  sectionParagraphs`. Declaratives paragraphs belong to no *regular* section, so
  they are misclassified as **standalone** and serialized into the top-level
  `paragraphs` list.
- `lower_procedure_division` emits standalone paragraphs **before** sections, so
  the program entry point lands on the first declaratives paragraph
  (`TEST-STATUS-44-00`), not `OPEN-FILES`.

Runtime evidence: the IR contains 4 `__cobol_open_file` instructions but 0 are
executed (passing programs execute 3); the first runtime I/O call is
`write_record`. The program runs declaratives body code, hits the `STOP RUN`
inside the declaratives, and exits — never opening `PRINT-FILE`. Programs whose
declaratives section is a bare `USE` with no paragraphs (e.g. SQ103A) pass today
only by luck of fall-through.

In SQ212A all 28 "standalone" paragraphs fall on source lines 297–432, entirely
within the `DECLARATIVES` block (lines 294–433); none overlap any section.

## Architecture

Two layers, mirroring the existing SELECT/FD-name fix (`fd_name`):

1. The Java bridge classifies declaratives content and emits it in a dedicated
   `declaratives` field, removing those paragraphs from the top-level
   `paragraphs` list.
2. The Python lowering consumes `declaratives` and emits those sections **after**
   all real flow, so the entry point stays on the first real element.

ProLeap exposes everything needed: every ASG element has `getCtx()` returning a
`ParserRuleContext` with `getStart().getLine()` / `getStop().getLine()`.
`pd.getDeclaratives()` returns a `Declaratives` whose ctx spans the whole block;
each `Declarative` has `getSectionHeader().getName()` and a ctx spanning one
declarative section. A paragraph is a declaratives paragraph iff its start line
falls within the declaratives block range.

## Components

### 1. Bridge — `proleap-bridge/src/main/java/org/reddragon/bridge/AsgSerializer.java`

**New method `serializeDeclaratives(ProcedureDivision pd)` → `JsonArray`:**
- If `pd.getDeclaratives()` is null, return an empty array.
- For each `Declarative d` in `pd.getDeclaratives().getDeclaratives()`:
  - `name = d.getSectionHeader().getName()`
  - line range `[d.getCtx().getStart().getLine(), d.getCtx().getStop().getLine()]`
  - paragraphs = those in `pd.getParagraphs()` whose `getCtx().getStart().getLine()`
    is within that range, serialized via the existing `serializeParagraphs`.
  - emit `{ "name": name, "paragraphs": [...] }` — same shape as a `sections` entry.

**New helper `isInDeclaratives(Paragraph p, Declaratives decl)` → `boolean`:**
- True iff `decl != null` and `p.getCtx().getStart().getLine()` is within
  `[decl.getCtx().getStart().getLine(), decl.getCtx().getStop().getLine()]`.

**Modify `serializeProcedureDivision`:**
- Compute `Declaratives decl = pd.getDeclaratives()`.
- `findStandaloneParagraphs` gains a third exclusion: drop any paragraph for which
  `isInDeclaratives(p, decl)` is true (in addition to the existing
  section-membership exclusion).
- After the existing `sections` / `paragraphs` / `statements` adds, add
  `asg.add("declaratives", serializeDeclaratives(pd))` when non-empty.

**Rebuild:** `mvn package -q -DskipTests` (produces the shaded jar consumed by the
Python subprocess runner).

### 2. Model — `interpreter/cobol/asg_types.py`

- `CobolASG` gains `declaratives: list[CobolSection] = field(default_factory=list)`.
- `from_dict`: `declaratives=[CobolSection.from_dict(s) for s in data.get("declaratives", [])]`.
- `to_dict`: include `result["declaratives"] = [s.to_dict() for s in self.declaratives]`
  only when non-empty (matching the existing conditional pattern).
- Reuses `CobolSection`; no new type.

### 3. Lowering — `interpreter/cobol/lower_procedure.py`

In `lower_procedure_division`, after the existing loops (statements → standalone
paragraphs → sections):
- Extend `ctx.section_paragraphs` with declaratives sections so `PERFORM … THRU`
  within declaratives resolves: for each `section` in `asg.declaratives`, add
  `section.name → [p.name for p in section.paragraphs]`.
- Lower each declaratives section via the existing `lower_section`, emitting them
  at the end of the procedure body.

Because real flow is emitted first, the entry point (first instruction after
`proc_label`) is unchanged for declaratives-free programs and now correctly lands
on the first real element for declaratives programs. Each declaratives section
ends with its `ResumeContinuation`, and the real program reaches `STOP RUN`
before the declaratives code, so there is no fall-through into a handler.

## Data flow

```
DECLARATIVES block
  → bridge buckets pd.getParagraphs() by source-line range
  → JSON: declaratives:[{name, paragraphs}], paragraphs:[real standalone only]
  → CobolASG.declaratives / CobolASG.paragraphs
  → lower_procedure_division: real flow first, declaratives sections last
  → entry point = first real element (e.g. OPEN-FILES)
```

## Error handling / edge cases

- **No declaratives:** `pd.getDeclaratives()` null → empty `declaratives` array →
  `CobolASG.declaratives` empty → lowering loop is a no-op. All 140 currently
  passing programs are unaffected.
- **Declaratives section with no paragraphs** (bare `USE`): contributes an entry
  with an empty `paragraphs` list; lowering emits just the section label +
  `ResumeContinuation`. Harmless.
- **PERFORM within declaratives:** resolved because declaratives sections and
  their paragraphs are lowered (at the end) with their normal labels and
  registered in `section_paragraphs`.
- **USE trigger on I/O error:** explicitly NOT implemented here (m0oa.4). The 9
  target programs never trigger their handlers, so correct entry-point behavior
  alone makes them pass.

## Testing

1. **Unit (bridge → model contract)** — `tests/unit/cobol/`:
   Parse a COBOL program containing a non-empty `DECLARATIVES` block; assert
   `CobolASG.declaratives` is populated with the handler section and its
   paragraphs, AND that those paragraph names are absent from `CobolASG.paragraphs`.

2. **Integration (run())** — `tests/integration/` (per project convention,
   exercise the VM, cover the reachable path):
   A minimal COBOL program with a non-empty `DECLARATIVES` USE section that writes
   `"DECL"` to the output file, and a main body (after `END DECLARATIVES`) that
   opens the file, writes `"MAIN"`, and `STOP RUN`s. Run via `run(...,
   io_provider=...)` with a real/temp file provider; assert the output contains
   `MAIN` and does **not** contain `DECL` — proving the entry point skips
   declaratives. Also assert a declaratives-free program still behaves identically
   (regression guard for entry-point ordering).

3. **NIST** — `tests/nist/test_{sq,ix,rl}.py`:
   The 9 programs transition skip → pass (they are already in the parametrize
   lists). Update the docstring skip annotations: remove the 9 from any
   "DECLARATIVES not handled" note, leaving only the genuine M-stub skips.

## Acceptance criteria

- `CobolASG.from_dict` populates `declaratives` and excludes those paragraphs from
  `paragraphs` (unit test).
- A declaratives program's entry point is the first element after `END
  DECLARATIVES` (integration test: `MAIN` present, `DECL` absent).
- All 9 listed NIST programs pass under `@pytest.mark.nist`.
- Full COBOL unit suite and the SQ/IX/RL NIST series remain green (no regression
  in the 140 already-passing programs).
- `mvn package` rebuilds the bridge jar; `poetry run python -m black .` clean.
