# INSPECT/STRING/UNSTRING Correctness Gaps — Design

## Problem

Five COBOL correctness gaps in `INSPECT`/`STRING`/`UNSTRING` lowering are tracked as linked
Beads issues under the `red-dragon-4q25` epic (COBOL correctness gaps, 2026-04-16 audit):

- `red-dragon-4q25.12` — `UNSTRING` supports only one delimiter; `DELIMITED BY x OR y` is
  not implemented.
- `red-dragon-4q25.13` — `INSPECT`'s `BEFORE INITIAL`/`AFTER INITIAL` boundary clauses are
  not implemented; `TALLYING`/`REPLACING` always operate on the entire source string.
- `red-dragon-4q25.14` — `UNSTRING`'s `TALLYING IN` clause (count of substrings extracted)
  is not implemented.
- `red-dragon-4q25.15` — `STRING`/`UNSTRING`'s `WITH POINTER` clause (position cursor
  across multiple invocations) is not implemented.
- `red-dragon-4q25.17` — `INSPECT` supports only one `TALLYING` target per statement;
  `INSPECT src TALLYING cnt1 FOR ALL 'A' cnt2 FOR ALL 'B'` silently drops all but the first
  counter.

All five were verified still-open against current code on 2026-07-06 (not stale): the
relevant dataclass fields (`UnstringStatement.delimited_by`, `InspectStatement.tallying_target`)
are still scalar, and a repo-wide grep for `BEFORE INITIAL`, `AFTER INITIAL`, `WITH POINTER`,
`TALLYING IN` in both `tests/` and `interpreter/` returns zero matches.

## Scope

**In scope**: all five issues above, implementing exactly the acceptance criteria already
written into each Beads issue.

**Explicitly out of scope** (tracked as separate follow-up issues, not fixed here):

- `ON OVERFLOW` behavior for `WITH POINTER` (acceptance criterion #4 on `4q25.15`) — there is
  no existing `ON OVERFLOW` support anywhere in the Python statement/lowering layer to build
  on; pulling it in would mean designing a new error-handling clause from scratch, a
  meaningfully larger scope than the other four fixes. `WITH POINTER`'s core position-tracking
  behavior (acceptance criteria #1-3) is implemented; the overflow-detection nuance is
  deferred.
- `UNSTRING`'s `DELIMITED BY ALL x` modifier (squeeze consecutive delimiter occurrences into
  one, rather than producing empty fields between them) — a real, separate ProLeap grammar
  feature (`unstringDelimitedByPhrase: DELIMITED BY? ALL? ...`) that none of the five issues'
  acceptance criteria ask for.

## Root cause: the parser already supports all five constructs

Investigation of the vendored ProLeap grammar (`proleap-bridge/proleap-cobol-parser`)
confirmed the ANTLR grammar (`Cobol.g4`) and its ASG object model already fully parse every
one of these five constructs:

```
unstringSendingPhrase   : identifier (unstringDelimitedByPhrase unstringOrAllPhrase*)?
unstringOrAllPhrase     : OR ALL? (identifier | literal)
unstringWithPointerPhrase : WITH? POINTER qualifiedDataName
unstringTallyingPhrase  : TALLYING IN? qualifiedDataName
inspectBeforeAfter      : (BEFORE | AFTER) INITIAL? (identifier | literal)
```

At the ASG layer: `Sending.getOrAlls(): List<OrAll>`, `UnstringStatement.getWithPointerPhrase()`
/`getTallyingPhrase()`, `AllLeading.getBeforeAfterPhrases(): List<BeforeAfterPhrase>`, and
`Tallying.getFors(): List<For>` (each `For` already carries its own independent
`getTallyCountDataItemCall()`) — all already exist and are populated by the parser today.

**No changes to the vendored third-party grammar are needed.** The gap is entirely that
`proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java` never reads
these already-parsed AST nodes into the JSON handed to Python. One spot is an outright bug,
not just an omission: `serializeInspect`'s tallying loop calls
`obj.addProperty("tallying_target", ...)` *inside* a loop over multiple `For` entries,
overwriting the same JSON object field on every iteration — with two `TALLYING` targets, only
the last one survives into the JSON at all.

## Architecture: two phases

### Phase A — one Java bridge change

All five constructs are read/emitted from the same two serializer methods
(`serializeUnstring`, `serializeInspect`) plus `serializeString`, so this is **one** bridge
change and **one** JAR rebuild, not five separate ones:

- `serializeUnstring`: emit `delimiters` as a JSON array (first entry from
  `getDelimitedByPhrase()`, remainder from `getOrAlls()`) instead of the scalar
  `delimited_by`; emit `pointer` from `getWithPointerPhrase().getPointerCall()`; emit
  `tallying_target` from `getTallyingPhrase().getTallyCountDataItemCall()`.
- `serializeString`: emit `pointer` from `getWithPointerPhrase().getPointerCall()`.
- `serializeInspect`: restructure the `TALLYING` branch to emit a `tallying_groups` JSON
  array — one entry per `For`, each carrying its own `tallying_target` and `tallying_for`
  pattern list (fixing the overwrite bug as a natural consequence of the restructure); add
  `before`/`after` fields (from `BeforeAfterPhrase`) to each pattern entry in
  `tallying_for`/`replacings`.

### Phase B — five independent Python tasks, executed sequentially

Each task: new dataclass field(s), new lowering logic, TDD tests taken directly from the
issue's own acceptance criteria. Sequential, not parallel subagents, since all five touch
the same two files (`cobol_statements.py`, `lower_string_inspect.py`).

## Data model changes

- `UnstringStatement.delimited_by: str` → `delimiters: list[str]` (first-occurrence-wins
  across all listed delimiters, per `4q25.12` AC #3 — the earliest match position among all
  candidate delimiters governs the split point).
- `UnstringStatement` gains `pointer: str = ""` (from `WithPointerPhrase`) and
  `tallying_target: str = ""` (from `TallyingPhrase`) — both default to empty string per
  this repo's "no `None` defaults" convention; an empty string means the clause is absent.
- `StringStatement` gains `pointer: str = ""`.
- `InspectStatement.tallying_target: str` + `tallying_for: list[TallyingFor]` (flat) becomes
  `tallying_groups: list[TallyingGroup]`, where `TallyingGroup` is a new frozen dataclass
  holding `target: str` + `patterns: list[TallyingFor]` — mirrors the Java ASG's own
  `List<For>` shape faithfully, since each `For` already carries its own independent tally
  target.
- `TallyingFor` (and `Replacing`) gain a `before_after: BeforeAfter` field, where
  `BeforeAfter` is a new frozen dataclass/null-object pair: a `NoBoundary` null object (the
  common case — no `BEFORE`/`AFTER INITIAL` clause present) and a real `BeforeAfter(kind,
  boundary_text)` case, rather than `Optional[...]` — per this repo's "no `None` returns,
  use the null object pattern" rule.

## Lowering approach

- **Multi-delimiter split**: for each candidate delimiter in `delimiters`, run the existing
  `STRING_FIND` builtin against the source string; take the delimiter with the earliest
  match position as the actual split point for that segment. No new builtin needed — this
  is the same `STRING_FIND`/`STRING_SPLIT` pair `lower_unstring` already calls, just invoked
  once per candidate delimiter instead of once total.
- **`WITH POINTER`**: read the pointer field's current value via the existing field-read
  path (same as any other data-item read in this file), use it as the 0-indexed starting
  offset fed into the existing `STRING_SLICE`/split call, then write the new position back
  via `ctx.emit_encode_and_write` — the exact copy-back mechanism this file already uses for
  every other write-back (`STRING`'s `INTO` target, `INSPECT REPLACING`'s source write-back).
  No new abstraction.
- **`BEFORE/AFTER INITIAL`**: `STRING_FIND` the boundary text within the source string, then
  `STRING_SLICE` the source down to (for `BEFORE`) or past (for `AFTER`) that position before
  handing the (possibly narrowed) string to the existing `build_inspect_tally_ir`/
  `build_inspect_replace_ir` calls. This reuses the exact same builtins the ref-mod slicing
  already uses elsewhere in this same file (`lower_string`, `lower_unstring`, `lower_inspect`
  all already call `STRING_SLICE` for ref-mod bounds) — not a new mechanism, a new call site.
  Per `4q25.13` AC #5: if the boundary text isn't found in the string at all, the entire
  string is examined (i.e., `STRING_FIND` returning "not found" means: skip the slice step
  entirely, fall through to the unbounded case).
- **`TALLYING IN`**: after the existing per-target split loop in `lower_unstring` runs,
  count how many `INTO` targets actually received a populated substring (this is already
  knowable from the existing `LIST_GET`/parts-list length the split already produces — no new
  computation, just a count of what's already been computed), and write that count to
  `stmt.tallying_target` via the same `emit_encode_and_write` write-back pattern used
  everywhere else.
- **Multi-target `INSPECT TALLYING`**: `lower_inspect_tallying` loops over
  `stmt.tallying_groups` instead of a single flat `tallying_for` list; for each group, run
  the existing per-pattern accumulation loop (unchanged) and write that group's own total to
  its own `group.target` — mechanically the same as today's single-target case, just
  repeated once per group instead of once total.

## Testing

Each of the five tasks writes its own integration test(s) directly from its Beads issue's
existing "ACCEPTANCE CRITERIA" section (already written in exhaustive, concrete example
form — e.g. `UNSTRING 'a,b;c' DELIMITED BY ',' OR ';' INTO f1 f2 f3` → `f1='a', f2='b',
f3='c'`) via `run()` (the same end-to-end execution path RedDragon's other COBOL coverage
tests use, per `tests/integration/test_cobol_coverage_gaps.py`'s existing pattern). Each
task's acceptance criteria explicitly include a backward-compatibility regression case
(single-delimiter `UNSTRING`, `INSPECT` without `BEFORE`/`AFTER`, single-target `TALLYING`,
etc.) — these must be written as tests too, not just the new-behavior cases.

## Follow-up issues (filed, not fixed here)

- `WITH POINTER`'s `ON OVERFLOW` interaction (split from `4q25.15`'s AC #4).
- `UNSTRING ... DELIMITED BY ALL x` (squeeze-consecutive-occurrences modifier).
