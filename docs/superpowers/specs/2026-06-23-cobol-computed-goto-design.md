# COBOL `GO TO … DEPENDING ON` (computed GOTO) — Design

**Date:** 2026-06-23
**Issue:** red-dragon-b787
**Status:** Design (awaiting review)

## Problem

`GO TO p1 p2 … pN DEPENDING ON idx` (the computed/indexed GOTO) is silently
dropped. The bridge's `serializeGoTo` (StatementSerializer.java) only reads
`stmt.getSimple()` and emits `{"type":"GOTO","operands":[]}` for the depending
form, so both the target list and the index are lost. At runtime the statement
becomes a no-op fall-through instead of branching to the `idx`-th paragraph.

ProLeap **already parses** the construct fully — the gap is purely in
serialization + lowering, not the grammar:

- `GoToStatement.getGoToType()` → `{ SIMPLE, DEPENDING_ON }`
- `GoToStatement.getDependingOnPhrase()` → `getProcedureCalls()` (the N targets)
  and `getDependingOnCall()` (the single index).

## Goals

- Lower computed GOTO so the `idx`-th (1-based) target is branched to, with
  out-of-range (`idx ≤ 0` or `idx > N`) falling through to the next statement.
- Represent the three `GO TO` forms with a data model in which invalid states
  are unrepresentable.
- Capture procedure-name section qualification structurally (forward-looking),
  and resolve the index through the normal field-reference path so it supports
  qualification and subscripting.

## Non-goals

- **Qualified-procedure-name resolution.** `ProcedureRef.section` is captured but
  lowering still resolves to the flat `para_{paragraph}` label, exactly as
  `PERFORM` / simple `GO TO` / `ALTER` do today. Resolving `PARA IN SECT` to a
  unique label is deferred (see Future Work).
- **Altered `GO TO.`** behavior. The empty form is modeled honestly as a variant
  but its runtime behavior is left exactly as-is (it is only partially wired to
  `ALTER` today).
- **Reference modification on the index.** `RefModOperand` carries `ref_mod_*`
  but a substring of an integer index is not meaningful; left unused.

## COBOL semantics

```
GO TO procedure-name-1 [procedure-name-2 …] DEPENDING ON identifier-1
```

- Multiple targets are legal **only** with `DEPENDING ON`; `GO TO P1 P2` without
  it is not valid COBOL. ProLeap enforces this: `Simple` has exactly one target,
  `DependingOnPhrase` has the list **plus** exactly one index.
- The index is **1-based**: `idx=k` transfers to the `k`-th target.
- Out-of-range `idx` (`≤ 0` or `> N`) is a silent no-op — control falls through.

The three forms are mutually exclusive, and the depending targets/index always
co-occur (both live in `DependingOnPhrase`):

| Form | targets | index |
|---|---|---|
| `GO TO P1` (simple) | 1 | 0 |
| `GO TO P1 … Pn DEPENDING ON X` (computed) | N (≥1) | exactly 1 |
| `GO TO.` (altered, target set by `ALTER`) | 0 | 0 |

## Data model

`GO TO` is a sum type of three variants. Modeling it as a discriminated union
(rather than nullable fields or null-object sentinels) makes every invalid
combination — "targets without an index", "two indices", "simple + computed" —
structurally impossible.

```python
@dataclass(frozen=True)
class ProcedureRef:
    """A COBOL procedure-name: a paragraph, optionally qualified by a section.
    A bare name (paragraph or section) has section="". Procedure-names are never
    subscripted, ref-modded, or expressions, so the surface is deliberately small."""
    paragraph: str
    section: str = ""

@dataclass(frozen=True)
class SimpleGoto:
    target: ProcedureRef

@dataclass(frozen=True)
class ComputedGoto:
    targets: tuple[ProcedureRef, ...]   # N ≥ 1 jump targets
    index: RefModOperand                # the single selecting identifier (structured)

@dataclass(frozen=True)
class AlteredGoto:
    """`GO TO.` with no operand — target supplied by ALTER at runtime."""
    pass

@dataclass(frozen=True)
class GotoStatement:
    form: SimpleGoto | ComputedGoto | AlteredGoto
```

Why this shape:

- **`index: RefModOperand` (singular, non-optional within `ComputedGoto`)** makes
  "exactly one index" a type-level guarantee. `RefModOperand` is the existing
  structured operand (`name` + `qualifiers` + `subscripts: tuple[ExprNode, ...]`
  + ref-mod) used by MOVE/arithmetic, so a qualified, subscripted index like
  `WS-SEL OF WS-CTL (ROW-IX (I), COL-IX + 1)` is captured with no new types.
- **`ProcedureRef`** carries only what a procedure-name can be. The two union
  arms have genuinely different shapes — this is not cosmetic symmetry.
- **No nullable fields, no empty-sentinel.** Each variant holds exactly its own
  data; `lower_goto` dispatches on `stmt.form` with `isinstance`, the same idiom
  the statement layer already uses for `CobolStatementType`.
- **`statement_dispatch.py` is unchanged** — it still matches
  `isinstance(stmt, GotoStatement)`; the variant lives inside.

### Maximally-general example

```cobol
GO TO  PARA-1 IN SECT-A
       MENU-RTN
       PARA-3 OF SECT-C
    DEPENDING ON WS-SEL OF WS-CTL (ROW-IX (I), COL-IX + 1).
```

```python
ComputedGoto(
    targets=(
        ProcedureRef(paragraph="PARA-1",  section="SECT-A"),
        ProcedureRef(paragraph="MENU-RTN", section=""),
        ProcedureRef(paragraph="PARA-3",  section="SECT-C"),
    ),
    index=RefModOperand(
        name="WS-SEL",
        qualifiers=("WS-CTL",),
        subscripts=(<ExprNode: ROW-IX (I)>, <ExprNode: COL-IX + 1>),
    ),
)
```

## Bridge serialization

`serializeGoTo` discriminates on `getGoToType()` plus a null-call check:

- `DEPENDING_ON` → **computed**
- `SIMPLE` and `getSimple().getProcedureCall() != null` → **simple**
- otherwise (`SIMPLE`, null call) → **altered**

JSON shape (explicit `form` discriminator, 1:1 with the variants):

```json
{ "type": "GOTO", "form": "simple",
  "target": { "paragraph": "REAL-PARA", "section": "" } }

{ "type": "GOTO", "form": "computed",
  "targets": [
    { "paragraph": "PARA-1",   "section": "SECT-A" },
    { "paragraph": "MENU-RTN", "section": "" },
    { "paragraph": "PARA-3",   "section": "SECT-C" }
  ],
  "index": { "name": "WS-SEL", "qualifiers": ["WS-CTL"], "subscripts": [ … ] } }

{ "type": "GOTO", "form": "altered" }
```

- **`index` reuses the existing `serializeRef` shape** (`name`/`qualifiers`/
  `subscripts`/`ref_mod_*`), so `RefModOperand.from_dict` consumes it unchanged.
- **`target`/`targets` use a new `serializeProcedureRef(Call)`** →
  `{paragraph, section}`, where `paragraph = extractCallName(call)` and `section`
  is the procedure-name's `IN`/`OF` qualifier (`""` if unqualified). The exact
  qualifier accessor on a procedure `Call` is verified at build time.
- `GotoStatement.from_dict` switches on `form` to build the correct variant.

This replaces the old `{"operands":[name]}` shape. Bridge and Python ship
together (JAR rebuild), no external consumers, so a clean break is acceptable;
`from_dict`/`to_dict` and the two unit tests that touch the old shape are updated
(see Tests).

## Lowering

`lower_goto` dispatches on `stmt.form`:

- **`SimpleGoto`** → `Branch(CodeLabel(f"para_{target.paragraph}"))` (unchanged
  behavior).
- **`AlteredGoto`** → existing empty-`GO TO.` behavior, unchanged.
- **`ComputedGoto`** → chained `BranchIf` table (the `lower_evaluate` idiom; no
  new IR opcode):

```
idx_reg = resolve_field_ref(index.name, materialised, index.qualifiers,
                            subscripts=index.subscripts) → emit_decode_field(...)
for k, target in enumerate(targets, start=1):       # 1-based
    k_reg     = const_to_reg(k)
    cmp_reg   = Binop("==", idx_reg, k_reg)
    match_lbl = fresh_label("goto_dep_match")
    next_lbl  = fresh_label("goto_dep_next")
    BranchIf(cmp_reg, (match_lbl, next_lbl))
    Label(match_lbl)
    Branch(CodeLabel(f"para_{target.paragraph}"))
    Label(next_lbl)
# after the final next_lbl, control falls through → next statement
```

Out-of-range handling is free: if no `k` matches, control reaches the last
`next_lbl` and continues. No bounds check, no error.

The index is decoded **once**. Section qualification on a target is recorded in
`ProcedureRef.section` but lowering uses `para_{paragraph}` (flat), consistent
with all existing procedure-name resolution.

## Tests

**Unit (dataclass round-trips, `from_dict`/`to_dict`):**
- `SimpleGoto` with and without `section`.
- `ComputedGoto` with a plain index and with a structured index (`qualifiers` +
  `subscripts`) — proves the `RefModOperand` arm round-trips.
- `AlteredGoto`.

**Bridge (real bridge, `test_bridge_structured_subscripts.py` idiom):**
- Feed a computed `GO TO … DEPENDING ON`; assert `form:"computed"`, ordered
  `targets`, and a structured `index`.

**Integration via `run()`** — each target writes a distinct value; a sentinel
after the `GO TO` detects fall-through:

```cobol
01 WS-IDX PIC 9 VALUE n.
01 WS-R   PIC 9 VALUE 0.
MAIN.
    GO TO P1 P2 P3 DEPENDING ON WS-IDX.
    MOVE 9 TO WS-R.            *> fall-through sentinel
    STOP RUN.
P1. MOVE 1 TO WS-R. STOP RUN.
P2. MOVE 2 TO WS-R. STOP RUN.
P3. MOVE 3 TO WS-R. STOP RUN.
```

| Case | `WS-IDX` | Expect `WS-R` |
|---|---|---|
| first target | 1 | 1 |
| middle target | 2 | 2 |
| last target | 3 | 3 |
| out-of-range high | 4 | 9 (fell through) |
| out-of-range zero | 0 | 9 (fell through) |

Plus:
- **Structured index** — `DEPENDING ON` a qualified (`SEL-IX OF CTL-GRP`) and a
  subscripted index, proving resolution through the `RefModOperand` path.
- **Section/paragraph resolution** — targets that live inside sections
  (`GO TO PARA-A OF SECT-1 …`), asserting the jump lands; plus a focused
  no-regression check that simple `GO TO`/`PERFORM` resolution is unchanged.

`@covers(CobolFeature.GOTO_DEPENDING_ON)` on the integration tests.

## Touch list

- `proleap-bridge/.../StatementSerializer.java` — `serializeGoTo` 3-way branch +
  new `serializeProcedureRef`. Rebuild the shaded JAR.
- `interpreter/cobol/cobol_statements.py` — `ProcedureRef`, `SimpleGoto`,
  `ComputedGoto`, `AlteredGoto`, `GotoStatement.form`; `from_dict`/`to_dict`.
- `interpreter/cobol/lower_arithmetic.py` — `lower_goto` variant dispatch +
  computed branch table.
- `interpreter/cobol/features.py` — `CobolFeature.GOTO_DEPENDING_ON`.
- Tests as above; update `test_cobol_statements.py` and `test_cobol_frontend.py`
  for the new `GotoStatement` shape.

## Future work

A section/paragraph symbol cache built in a pre-pass, used to **statically
resolve** a qualified `PARA IN SECT` (and disambiguate duplicate bare names) to a
unique label during lowering. `ProcedureRef.section` is the structural enabler —
it carries the qualifier forward instead of discarding it at parse time, so the
future pass has something to resolve against. This applies uniformly to
`PERFORM`, simple `GO TO`, `ALTER`, and computed `GO TO`.
