# COBOL Source Spans: Threading Line Numbers Into IR

**Date:** 2026-09-16
**Status:** Approved, ready for implementation plan

## Problem

COBOL-derived IR carries no source locations. Probing a small program
(WORKING-STORAGE fields plus `MOVE`/`ADD`/`DISPLAY`/`STOP RUN`) through
`CobolFrontend.lower()` gives:

```
total IR: 313   with source_location: 0
```

Every instruction prints `<unknown>`. The consequences are concrete:

- The TUI cannot highlight the COBOL line corresponding to an executing
  instruction, and the IR panel shows no positions.
- VM errors and abends cannot name the COBOL line that caused them.
- The memory-effect sidecar records `<unknown>` for every COBOL region
  read and write (`emit_context.py:241,272`), so dataflow attribution
  loses its link back to source.

The line information is not missing. It survives from ANTLR all the way
to the Python ASG and is discarded only at the final hop:

1. The Java bridge emits it. `StatementSerializer.java:159-162` adds
   `line_start`, `col_start`, `line_end` and `col_end` to every
   statement; `AsgSerializer.java:390-393` does the same per paragraph.
2. The Python ASG parses it. All 36 statement classes in
   `cobol_asg/cobol_statements.py` carry `span: SourceSpan | None`.
3. It is correct at runtime. For the probe program:
   `MoveStatement span=SourceSpan(line_start=7, col_start=11, line_end=7, col_end=21)`,
   matching the fixture exactly.
4. Lowering never reads it. `grep -rn '\.span' interpreter/cobol/`
   returns zero hits across all 42 modules. Nothing converts
   `SourceSpan` into `SourceLocation`.

## Scope

All three tiers of position data, including a bridge change:

- Procedure-division statements (spans already exist).
- Paragraphs and sections (Java already emits; Python keeps the data).
- Data-division fields (requires a new bridge change and a JAR rebuild).

The consumer is both human-facing navigation and runtime diagnostics.
Diagnostics set the precision bar: a wrong line in a stack trace is
worse than no line, so attribution must be exact rather than
approximate.

## Approach

Thread the span **explicitly** as a keyword argument through every
emitting call, mirroring the `node=` parameter the 15 tree-sitter
frontends already use (`frontends/context.py:210-222`,
`frontends/_base.py:215-225`).

An ambient span stack on `EmitContext`, pushed and popped by
`dispatch_statement`, was considered and rejected. It would have cost
roughly three edits instead of six hundred, but it makes attribution a
property of the caller rather than of the emit site: reading
`lower_arithmetic.py` in isolation would not tell you what line its
instructions carry. Explicit threading is mechanical, greppable, and
verifiable by a static lint. The work is bulk, not difficulty.

## Design

### 1. One span shape everywhere

`SourceSpan` moves from `cobol_asg/cobol_statements.py:29-37` to
`cobol_asg/source_span.py`. It is no longer a statement concept: it is
shared by statements, paragraphs and fields.

`cobol_asg` imports nothing from `interpreter` (verified: zero hits).
That one-way dependency is preserved. The `SourceSpan` to
`SourceLocation` conversion therefore lives on the `interpreter` side,
in `interpreter/cobol/source_spans.py`. `cobol_asg` never learns about
IR types.

**`CobolParagraph`** (`asg_types.py:209-214`) replaces its four
`int | None` fields with a single `span: SourceSpan | None`. The four
fields have no consumers anywhere outside the class's own `from_dict`
and `to_dict`, so this is a free unification with no migration risk.
`to_dict` continues to emit the flat `line_start`/`col_start`/
`line_end`/`col_end` keys, leaving the JSON wire format unchanged.

**`CobolField`** (`asg_types.py:58`) gains `span: SourceSpan | None =
None`, declared before the `type_descriptor: field(init=False)` line so
that `__post_init__` is unaffected.

**`FieldLayout`** (`data_layout.py:68-97`) gains `span: SourceSpan |
None = None`. `lower_data_division` iterates `FieldLayout`, not
`CobolField`, and `FieldLayout` today holds no back-reference to the
field it came from, so the span must be copied across at construction.
Its six construction sites divide as follows.

| Site | Source | Span |
|---|---|---|
| `data_layout.py:605` | elementary leaf, from `cobol_field` | `cobol_field.span` |
| `data_layout.py:688` | RENAMES entry, from `renames_field` | `renames_field.span` |
| `data_layout.py:310` | synthesized group storage, from `grp` | `grp.span` |
| `data_layout.py:483` | synthesized group storage, from `grp` | `grp.span` |
| `emit_context.py:528` | OCCURS element, derived from parent `fl` | `fl.span` |
| `data_layout.py:770` | index items | `None` |

The two group sites build from `grp`, which is a **`DataLayout`**, not a
`CobolField`. So `DataLayout` (`data_layout.py:120-142`) needs a
`span: SourceSpan | None = None` field of its own. It is a one-line
addition: the only construction site that corresponds to real source is
`data_layout.py:586`, which already has `cobol_field` in scope. The
remaining `DataLayout` constructions — root layouts
(`data_layout.py:720,734`), the index layout (`:778`), and the empty
defaults in `cobol_frontend.py:80` and `sectioned_layout.py:42-48` —
are containers with no single source line and keep `None`.

Only index items are genuinely spanless; OCCURS elements inherit their
parent field's span, which is correct because a subscripted access and
its declaration share a source line.

### 2. Bridge changes

Extract the inline position code at `StatementSerializer.java:159-162`
into a shared `addSpan(JsonObject, ParserRuleContext)` helper, then call
it from `DataFieldSerializer.serializeGroup()` (`:73`),
`serializeRename()` (`:172`) and the condition-name path. Rebuild the
JAR.

ANTLR reports 1-based lines and 0-based columns
(`getLine()`/`getCharPositionInLine()`), which matches `SourceLocation`'s
tree-sitter convention. The conversion is a direct field mapping, and
the fidelity test below exists to catch any off-by-one.

### 3. Threading

`EmitContext.emit_inst` (`emit_context.py:196-200`) gains a
keyword-only `span: SourceSpan | None = None` and follows the precedent
in `frontends/context.py:210-222` exactly: a `source_location` already
present on the instruction wins; otherwise resolve from `span`;
otherwise `NO_SOURCE_LOCATION`.

The 21 `EmitContext` methods that emit on a caller's behalf gain the
same keyword-only parameter and forward it.

`inline_ir(ir, params, *, span)` (`emit_context.py:306-345`) stamps each
instruction as it remaps it. Every instruction built by
`ir_encoders.py` funnels through `inline_ir`, so all 80 raw
`instructions.append` calls in that module need **no changes**. This
also settles attribution for synthesised encode and decode bodies: an
inlined `enc_zoned_WS_B` body inherits the span of the statement that
triggered it, which is both causally correct and what makes the
memory-effect sidecar useful.

Call sites divide into three mechanical classes:

| Class | Count | Work |
|---|---|---|
| `emit_inst` with `stmt`/`fl` already in scope | 221 | append `span=stmt.span` |
| `emit_inst` in private helpers | ~115 | add `span` to the helper, pass from one hop up |
| via `const_to_reg` (179) and `resolve_field_ref` (71) | ~250 | same, threaded from their callers |

`const_to_reg` is the bulk of the tedium and cannot be skipped: it
emits a `CONST` on every call, so leaving it unthreaded would leave a
large fraction of COBOL IR unlocated.

### 4. Deliberately spanless

`lower_program_init` (10 emit calls), `lower_ws_from_singleton` (3) and
`_lower_asg` (3) emit the program prologue and singleton plumbing,
which corresponds to no COBOL line. They pass no span and remain
`<unknown>`. This is the correct result, not a gap, and is recorded in
the static lint's allowlist so the intent stays visible.

### 5. Verification

Explicit threading is only as good as the next person's discipline, so
the invariant is enforced by tests, in the style of the existing
`tests/unit/cobol/test_region_funnel_invariant.py`.

- **Coverage invariant.** Lower a representative program; assert every
  instruction between the procedure-division entry label and the
  trailing `__after_*` label carries a known `source_location`. The
  probe program is 0 of 97 today; the test asserts 100%, with the
  prologue range explicitly excluded.
- **Fidelity.** Assert specific instructions map to the right line: a
  `MOVE` on line 7, and the encode body it expands into, all report
  `7:11-7:21`. This catches an off-by-one in the ANTLR-to-`SourceLocation`
  conversion, which a non-zero check would miss.
- **Nesting.** For `IF` on line 6 containing `MOVE` on line 7, assert
  the `IF`'s own branch scaffolding reports 6 while the body reports 7.
  This is where a `span=stmt.span` pasted into the wrong frame shows up.
- **Static lint.** An AST test asserting that no `emit_inst` call in
  `interpreter/cobol/lower_*.py` omits `span=`, with the allowlist from
  section 4. This makes the approach self-enforcing rather than a
  one-time sweep that decays.

## Order of work

1. Java `addSpan`, JAR rebuild, `CobolField.span` and
   `CobolParagraph.span`, verified by a bridge-output test. No lowering
   changes.
2. `SourceSpan` to `SourceLocation` conversion, `emit_inst` plumbing,
   `DataLayout.span` and `FieldLayout.span`.
3. Thread the 221 in-scope sites, per file, starting with
   `lower_arithmetic.py`'s 91 as the hardest.
4. Thread the ~115 helper sites and the `const_to_reg` /
   `resolve_field_ref` fan-out.
5. Enable the static lint and coverage invariant. They fail until
   steps 3 and 4 are complete, so they are the definition of done.

Steps 3 and 4 are mechanical and follow the normal TDD workflow. Steps
1 and 2 carry the design content.

## Out of scope

- Any TUI change. The TUI cannot open COBOL at all today
  (`viz/pipeline.py:85` requires a tree-sitter parser, and
  `get_frontend(Language.COBOL)` raises). Locating the IR is a
  prerequisite for that work, not part of it.
- Attributing prologue instructions to the `PROGRAM-ID` line.
- Column-level sub-statement precision. Spans are statement-level and
  field-level; an operand within a statement is not separately located.
