# COBOL Source Spans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every COBOL-derived IR instruction carry the source line it came from, so the TUI can highlight COBOL source, VM diagnostics can name a line, and the memory-effect sidecar stops recording `<unknown>`.

**Architecture:** The position data already exists end-to-end — the ProLeap bridge emits line/column per statement, and all 36 Python statement classes carry a `SourceSpan` — but COBOL lowering never reads it (`grep -rn '\.span' interpreter/cobol/` returns zero hits). This plan threads the span **explicitly** as a keyword argument through `EmitContext.emit_inst` and the methods that emit on a caller's behalf, mirroring the `node=` parameter the 15 tree-sitter frontends already use. A static lint test makes the threading self-enforcing.

**Tech Stack:** Python 3.13, `uv`, pytest, frozen dataclasses, Pydantic (`SourceLocation`), Java 17 + Maven (ProLeap bridge), Gson.

**Spec:** `docs/superpowers/specs/2026-09-16-cobol-source-spans-design.md`

## Global Constraints

- Run tests with **`make test`**. Bare `uv run python -m pytest` does NOT export `PROLEAP_BRIDGE_JAR`, and every bridge-dependent test then ERRORs at fixture setup with `KeyError: 'PROLEAP_BRIDGE_JAR'` (`tests/integration/cobol_helpers.py:90`). The Makefile exports it and builds the JAR if missing:
  ```bash
  make test                                   # full suite
  make test PYTEST_ARGS="tests/unit/cobol -q" # scoped
  ```
  Never `uv run pytest` (no `-m`). The project uses **uv, not Poetry** — any `poetry run` you see is stale.
- **Cap pytest workers: export `PYTEST_ADDOPTS="-n 2"` before any full-suite run or `git commit`.** `pyproject.toml:52` sets `-n auto`, which spawns one xdist worker per core (10 here); under sandbox memory limits the full suite gets OOM-killed mid-run. Task 2's pre-commit hook was killed twice this way before succeeding on the third attempt. Verified: `PYTEST_ADDOPTS` overrides the ini setting. `-n 4` was still OOM-killed in Task 3; `-n 2` completes reliably. Use `-n 2`. Use:
  ```bash
  PYTEST_ADDOPTS="-n 2" make test
  PYTEST_ADDOPTS="-n 2" git commit -m "..."   # the pre-commit hook runs make test
  ```
  A killed hook is not a test failure — but do not treat a real failure as an OOM kill either. Check the output.
- **Verified clean baseline on this branch: 15333 passed, 66 skipped, 17 xfailed, 0 failed.** Compare against that, not a remembered number. (An earlier controller run reported "13904 passed" — that figure was truncated by `-x` aborting at the `PROLEAP_BRIDGE_JAR` error. It is wrong; do not use it.)
- **Do not clean or revert the working tree.** Stage and commit only the files your task names. A `git checkout -- .`, `git stash`, or `git clean` can destroy controller edits or another task's work in this shared worktree.
- Format with `uv run python -m black .` before every commit.
- After changing any Java source under `proleap-bridge/`, rebuild with `make jar-force`. The JAR is not rebuilt automatically when sources change — only when it is missing.
- **Every new test function needs a `@covers(...)` decorator.** Infrastructure/invariant tests use `@covers(NotLanguageFeature.INFRASTRUCTURE)` from `tests.covers`. Feature tests use the relevant `CobolFeature` member. A test without `@covers` breaks `scripts/feature_coverage_audit.py`.
- `git commit` triggers a pre-commit hook that runs the full suite (several minutes). **Always** use `run_in_background: true` or a timeout of at least 600000 ms. Never the default 2-minute Bash timeout.
- `cobol_asg` must never import from `interpreter`. This is a one-way dependency (currently zero violations) enforced by `make lint` (import-linter contracts). Conversions from ASG types to IR types live on the `interpreter` side.
- Integration tests go in `tests/integration/`, unit tests in `tests/unit/`.
- Never rename a test to hide a gap, and never remove enum members to game coverage numbers.

## Naming reference (used across tasks)

These exact names are used by later tasks. Do not vary them.

| Name | Location | Signature |
|---|---|---|
| `SourceSpan` | `cobol_asg/source_span.py` | frozen dataclass: `line_start: int, col_start: int, line_end: int, col_end: int` |
| `SourceSpan.from_dict` | `cobol_asg/source_span.py` | `(data: dict) -> SourceSpan \| None` |
| `SourceSpan.write_into` | `cobol_asg/source_span.py` | `(self, result: dict) -> None` |
| `to_source_location` | `interpreter/cobol/source_spans.py` | `(span: SourceSpan \| None) -> SourceLocation` |
| `EmitContext.emit_inst` | `interpreter/cobol/emit_context.py` | `(self, inst, *, span: SourceSpan \| None = None) -> InstructionBase` |

`SourceLocation` (`interpreter/ir.py:81-100`) is a Pydantic `BaseModel` with fields `start_line`, `start_col`, `end_line`, `end_col`. Note the **field names are transposed** relative to `SourceSpan` (`line_start` vs `start_line`) — this is the single most likely place to introduce a silent bug. `NO_SOURCE_LOCATION` is at `interpreter/ir.py:103`.

## Known fidelity limitation (do not try to "fix" it)

ANTLR's `getStop().getCharPositionInLine()` returns the **start column of the last token**, not the end of that token. For `MOVE 7 TO WS-B.` on line 7, the bridge reports `col_end=21`, which is where `WS-B` begins, not where it ends. This is pre-existing behaviour of the spans that already ship. This plan preserves it as-is and pins it with exact-value assertions. Changing it would require `getStop().getStopIndex()` arithmetic and is out of scope.

---

### Task 1: Extract `SourceSpan` into its own module

`SourceSpan` currently lives in `cobol_asg/cobol_statements.py:29-37` and is treated as a statement concept. It is about to be shared by statements, paragraphs and fields, so it moves. The move is also the right moment to kill duplication: the file currently repeats an 8-line span-parse block **36 times** and a 4-line span-serialize block **36 times**, once per statement class.

**Files:**
- Create: `cobol_asg/source_span.py`
- Modify: `cobol_asg/cobol_statements.py` (remove definition at `:29-37`, import instead; replace 36 parse blocks and 36 serialize blocks)
- Test: `tests/unit/cobol/test_source_span.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `SourceSpan` (frozen dataclass, fields `line_start`, `col_start`, `line_end`, `col_end`), `SourceSpan.from_dict(data) -> SourceSpan | None`, `SourceSpan.write_into(result) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/cobol/test_source_span.py`:

```python
"""SourceSpan parses from and serialises to the bridge's flat JSON keys."""

from cobol_asg.source_span import SourceSpan
from tests.covers import NotLanguageFeature, covers


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_dict_reads_the_four_flat_keys():
    span = SourceSpan.from_dict(
        {"line_start": 7, "col_start": 11, "line_end": 7, "col_end": 21}
    )
    assert span == SourceSpan(
        line_start=7, col_start=11, line_end=7, col_end=21
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_dict_returns_none_when_position_is_absent():
    """A bridge object with no ctx emits no position keys at all."""
    assert SourceSpan.from_dict({"type": "MOVE"}) is None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_from_dict_ignores_unrelated_keys():
    span = SourceSpan.from_dict(
        {"type": "MOVE", "line_start": 1, "col_start": 2,
         "line_end": 3, "col_end": 4}
    )
    assert span == SourceSpan(line_start=1, col_start=2, line_end=3, col_end=4)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_write_into_round_trips_through_from_dict():
    original = SourceSpan(line_start=7, col_start=11, line_end=9, col_end=4)
    result: dict = {}
    original.write_into(result)
    assert result == {
        "line_start": 7, "col_start": 11, "line_end": 9, "col_end": 4
    }
    assert SourceSpan.from_dict(result) == original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cobol_asg.source_span'`

- [ ] **Step 3: Create the module**

Create `cobol_asg/source_span.py`:

```python
# pyright: standard
"""Source position of a COBOL construct in the original source file.

Shared by statements, paragraphs and data-division fields. Lines are
1-based and columns 0-based, matching ANTLR's ``getLine()`` and
``getCharPositionInLine()`` — and, deliberately, the tree-sitter
convention used by ``interpreter.ir.SourceLocation``, so the conversion
in ``interpreter/cobol/source_spans.py`` is a straight field mapping.

Note that ``col_end`` is the START column of the construct's last token,
not the end of that token. That is what ANTLR's ``getStop()`` reports and
what the bridge has always emitted.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpan:
    """Source position of a COBOL construct in the original source file."""

    line_start: int
    col_start: int
    line_end: int
    col_end: int

    @classmethod
    def from_dict(cls, data: dict) -> SourceSpan | None:
        """Read a span from a bridge JSON object, or None if it carries no position.

        The bridge omits all four keys together when the underlying ANTLR
        context is absent, so testing one key is sufficient and matches the
        pre-existing per-statement parse blocks this replaces.
        """
        if "line_start" not in data:
            return None
        return cls(
            data["line_start"],
            data["col_start"],
            data["line_end"],
            data["col_end"],
        )

    def write_into(self, result: dict) -> None:
        """Write this span's four flat keys into a bridge JSON object."""
        result["line_start"] = self.line_start
        result["col_start"] = self.col_start
        result["line_end"] = self.line_end
        result["col_end"] = self.col_end
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Re-point `cobol_statements.py` at the new module**

Delete the `SourceSpan` dataclass at `cobol_asg/cobol_statements.py:29-37` (keep the `# ── Source position ──` comment banner off; it belongs to the new module now) and add to the import block at the top:

```python
from cobol_asg.source_span import SourceSpan
```

Keep the name importable from `cobol_statements` — other modules may already import it from there, and re-exporting costs nothing.

- [ ] **Step 6: Collapse the 36 duplicated parse blocks**

In every `from_dict` in `cobol_asg/cobol_statements.py`, replace this shape:

```python
            span=(
                SourceSpan(
                    data["line_start"],
                    data["col_start"],
                    data["line_end"],
                    data["col_end"],
                )
                if "line_start" in data
                else None
            ),
```

with:

```python
            span=SourceSpan.from_dict(data),
```

There are exactly 36. Verify with `grep -c 'SourceSpan.from_dict(data)' cobol_asg/cobol_statements.py` → must print `36`, and `grep -c '"line_start" in data' cobol_asg/cobol_statements.py` → must print `0`.

- [ ] **Step 7: Collapse the 36 duplicated serialize blocks**

In every `to_dict`, replace this shape:

```python
        if self.span is not None:
            result["line_start"] = self.span.line_start
            result["col_start"] = self.span.col_start
            result["line_end"] = self.span.line_end
            result["col_end"] = self.span.col_end
```

with:

```python
        if self.span is not None:
            self.span.write_into(result)
```

Verify with `grep -c 'self.span.write_into(result)' cobol_asg/cobol_statements.py` → must print `36`.

- [ ] **Step 8: Verify nothing changed behaviourally**

This task is a pure refactor — the JSON wire format is byte-identical. Run the COBOL suite:

Run: `uv run python -m pytest tests/unit/cobol tests/unit/test_cobol_parser.py tests/unit/test_cobol_statements.py tests/unit/test_cobol_e2e.py -q`
Expected: PASS, same count as before your changes. If any test fails, you have mistyped one of the 72 replacements — do not "fix" the test.

- [ ] **Step 9: Format, lint and commit**

```bash
uv run python -m black .
uv run lint-imports
git add cobol_asg/source_span.py cobol_asg/cobol_statements.py tests/unit/cobol/test_source_span.py
git commit -m "refactor(cobol-asg): extract SourceSpan to its own module

SourceSpan is about to be shared by paragraphs and data fields, so it is
no longer a statement concept. Adds from_dict/write_into, collapsing 36
duplicated parse blocks and 36 duplicated serialise blocks.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `CobolParagraph` carries a `SourceSpan`

`CobolParagraph` (`cobol_asg/asg_types.py:209-214`) holds four loose `int | None` fields — the same data as `SourceSpan`, in a second shape. Those four fields have **no consumers anywhere** outside the class's own `from_dict`/`to_dict`, so this is a free unification. The Java side already emits paragraph positions (`AsgSerializer.java:390-393`), so no bridge change is needed here.

**Files:**
- Modify: `cobol_asg/asg_types.py:209-240`
- Test: `tests/unit/cobol/test_source_span.py` (append)

**Interfaces:**
- Consumes: `SourceSpan`, `SourceSpan.from_dict`, `SourceSpan.write_into` from Task 1.
- Produces: `CobolParagraph.span: SourceSpan | None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/cobol/test_source_span.py`:

```python
from cobol_asg.asg_types import CobolParagraph


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_paragraph_carries_a_span():
    para = CobolParagraph.from_dict(
        {"name": "MAIN-PARA", "line_start": 12, "col_start": 7,
         "line_end": 18, "col_end": 11}
    )
    assert para.span == SourceSpan(
        line_start=12, col_start=7, line_end=18, col_end=11
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_paragraph_without_position_has_no_span():
    assert CobolParagraph.from_dict({"name": "MAIN-PARA"}).span is None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_paragraph_to_dict_keeps_the_flat_wire_format():
    """The JSON contract with the Java bridge must not change."""
    para = CobolParagraph.from_dict(
        {"name": "MAIN-PARA", "line_start": 12, "col_start": 7,
         "line_end": 18, "col_end": 11}
    )
    assert para.to_dict() == {
        "name": "MAIN-PARA", "line_start": 12, "col_start": 7,
        "line_end": 18, "col_end": 11,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span.py -k paragraph -v`
Expected: FAIL — `AttributeError: 'CobolParagraph' object has no attribute 'span'`

- [ ] **Step 3: Replace the four fields with a span**

In `cobol_asg/asg_types.py`, add `from cobol_asg.source_span import SourceSpan` to the imports, then change `CobolParagraph`:

```python
@dataclass(frozen=True)
class CobolParagraph:
    """A COBOL paragraph — a named block of statements."""

    name: str
    statements: list[CobolStatementType] = field(default_factory=list)
    span: SourceSpan | None = None

    @classmethod
    def from_dict(cls, data: dict) -> CobolParagraph:
        return cls(
            name=data["name"],
            statements=[parse_statement(s) for s in data.get("statements", [])],
            span=SourceSpan.from_dict(data),
        )

    def to_dict(self) -> dict:
        result: dict = {"name": self.name}
        if self.span is not None:
            self.span.write_into(result)
        if self.statements:
            result["statements"] = [s.to_dict() for s in self.statements]
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Verify no stale consumers**

Run: `grep -rn "\.line_start\|\.col_start\|\.line_end\|\.col_end" --include="*.py" interpreter/ cobol_asg/ tests/ | grep -v "span\."`
Expected: no hits outside `cobol_asg/source_span.py`. If there are hits, they are consumers this plan missed — update them to go through `.span` before continuing.

- [ ] **Step 6: Commit**

```bash
uv run python -m black .
git add cobol_asg/asg_types.py tests/unit/cobol/test_source_span.py
git commit -m "refactor(cobol-asg): CobolParagraph carries a SourceSpan

Replaces four loose int|None fields with the shared span type. The JSON
wire format is unchanged.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Bridge emits positions for data-division fields

`DataFieldSerializer` emits no position data at all today, so `01 WS-B PIC 9(4) VALUE 0.` cannot be traced to a line. This task adds it in Java and receives it in Python.

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java:159-162` (extract helper)
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/DataFieldSerializer.java` (`serializeGroup` at `:73`, `serializeRename` at `:172`)
- Modify: `cobol_asg/asg_types.py` (`CobolField` at `:58`)
- Test: `tests/unit/cobol/test_source_span.py` (append)

**Interfaces:**
- Consumes: `SourceSpan.from_dict` from Task 1.
- Produces: `CobolField.span: SourceSpan | None`; bridge JSON for data fields now carries `line_start`/`col_start`/`line_end`/`col_end`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/cobol/test_source_span.py`:

```python
from cobol_asg.cobol_parser import make_cobol_parser

PROBE_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           MOVE 7 TO WS-B.
           DISPLAY WS-B.
           STOP RUN.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_bridge_emits_a_span_for_a_data_division_field():
    """01 WS-B is declared on line 5 of PROBE_SOURCE."""
    asg = make_cobol_parser().parse(PROBE_SOURCE)
    (field,) = [f for f in asg.data_fields if f.name == "WS-B"]
    assert field.span is not None
    assert field.span.line_start == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span.py -k data_division -v`
Expected: FAIL — `AttributeError: 'CobolField' object has no attribute 'span'`

- [ ] **Step 3: Add the shared Java helper**

In `StatementSerializer.java`, add this package-visible static method, and replace the four inline `addProperty` calls at `:159-162` with a call to it:

```java
    /**
     * Adds the four flat position keys for a parser context, or nothing when
     * the context is absent. Shared with DataFieldSerializer so every
     * positioned object in the ASG uses one spelling.
     */
    static void addSpan(JsonObject obj, org.antlr.v4.runtime.ParserRuleContext ctx) {
        if (ctx == null || ctx.getStart() == null || ctx.getStop() == null) {
            return;
        }
        obj.addProperty("line_start", ctx.getStart().getLine());
        obj.addProperty("col_start",  ctx.getStart().getCharPositionInLine());
        obj.addProperty("line_end",   ctx.getStop().getLine());
        obj.addProperty("col_end",    ctx.getStop().getCharPositionInLine());
    }
```

The call site in `serializeStatements` becomes:

```java
            if (obj != null) {
                addSpan(obj, stmt.getCtx());
                arr.add(obj);
            }
```

Note the added `getStop() == null` guard — the original code did not have it, and `serializeGroup` will now call this on contexts that may be incomplete.

- [ ] **Step 4: Call it from the data-field paths**

In `DataFieldSerializer.serializeGroup` (after `obj.addProperty("offset", offset);` at `:79`):

```java
        StatementSerializer.addSpan(obj, group.getCtx());
```

In `DataFieldSerializer.serializeRename` (after `obj.addProperty("offset", 0);` at `:175`):

```java
        StatementSerializer.addSpan(obj, rename.getCtx());
```

- [ ] **Step 5: Rebuild the JAR**

Run: `make jar-force`
Expected: Maven completes without error. This step is mandatory — the JAR is not rebuilt when Java sources change, only when it is missing.

- [ ] **Step 6: Receive the span in `CobolField`**

In `cobol_asg/asg_types.py`, add to `CobolField` — **before** the `type_descriptor: CobolTypeDescriptor = field(init=False)` line, so `__post_init__` is unaffected:

```python
    span: SourceSpan | None = None
```

And in whichever `from_dict`/construction path builds `CobolField` from bridge JSON, pass `span=SourceSpan.from_dict(data)`. Find it with `grep -n "CobolField(" cobol_asg/asg_types.py`.

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span.py -v`
Expected: PASS (8 tests)

- [ ] **Step 8: Run the full COBOL suite**

Run: `uv run python -m pytest tests/unit/cobol tests/unit/test_cobol_e2e.py tests/integration -q -k cobol`
Expected: PASS. A new JSON key is additive, so nothing should break; if something does, it is a test asserting exact dict equality on bridge output — update that test's expectation, it is a genuine contract change.

- [ ] **Step 9: Commit**

```bash
uv run python -m black .
git add proleap-bridge/src cobol_asg/asg_types.py tests/unit/cobol/test_source_span.py
git commit -m "feat(cobol-bridge): emit source positions for data-division fields

Extracts addSpan() from StatementSerializer and calls it from the group
and RENAMES paths, so 01/05/66 entries can be traced to a source line.
CobolField receives it as a SourceSpan.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Spans reach `DataLayout` and `FieldLayout`

`lower_data_division` iterates `FieldLayout`, not `CobolField`, and `FieldLayout` holds no back-reference to the field it came from. Two of its construction sites build from `grp`, which is a `DataLayout` — so `DataLayout` needs a span of its own to pass along.

**Files:**
- Modify: `interpreter/cobol/data_layout.py` (`DataLayout` at `:120-142`, `FieldLayout` at `:68-97`, construction sites at `:310`, `:483`, `:586`, `:605`, `:688`)
- Modify: `interpreter/cobol/emit_context.py:528` (OCCURS element)
- Test: `tests/unit/cobol/test_source_span.py` (append)

**Interfaces:**
- Consumes: `CobolField.span` from Task 3.
- Produces: `FieldLayout.span: SourceSpan | None`, `DataLayout.span: SourceSpan | None`.

Span assignment per construction site — copy this table exactly:

| Site | Source | Span value |
|---|---|---|
| `data_layout.py:605` | elementary leaf, from `cobol_field` | `span=cobol_field.span` |
| `data_layout.py:688` | RENAMES entry, from `renames_field` | `span=renames_field.span` |
| `data_layout.py:310` | synthesized group storage, from `grp` | `span=grp.span` |
| `data_layout.py:483` | synthesized group storage, from `grp` | `span=grp.span` |
| `emit_context.py:528` | OCCURS element, from parent `fl` | `span=fl.span` |
| `data_layout.py:770` | index items | leave unset (`None`) |
| `data_layout.py:586` | `DataLayout` for a group, from `cobol_field` | `span=cobol_field.span` |
| `data_layout.py:720`, `:734`, `:778` | root and index layouts | leave unset (`None`) |
| `cobol_frontend.py:80`, `sectioned_layout.py:42-48` | empty defaults | leave unset (`None`) |

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/cobol/test_source_span.py`:

```python
from interpreter.cobol.data_layout import build_data_layout


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_field_layout_carries_the_declaring_line():
    """WS-B's FieldLayout knows it was declared on line 5."""
    asg = make_cobol_parser().parse(PROBE_SOURCE)
    layout = build_data_layout(asg.data_fields)
    fl = layout.fields["WS-B"]
    assert fl.span is not None
    assert fl.span.line_start == 5


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_index_items_are_deliberately_spanless():
    """Compiler-allocated index items correspond to no source text.

    OCCURS ... INDEXED BY IX is the only declaration IX ever gets, so the
    layout must actually contain an index item for this to assert anything.
    """
    from interpreter.cobol.data_layout import build_index_layout

    indexed_source = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. INDEXED.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-TABLE.
          05 WS-ROW PIC X(4) OCCURS 3 TIMES INDEXED BY IX.
       PROCEDURE DIVISION.
           STOP RUN.
"""
    asg = make_cobol_parser().parse(indexed_source)
    index_layout = build_index_layout(asg.data_fields)
    assert index_layout.fields, "expected an index item for IX"
    assert all(fl.span is None for fl in index_layout.fields.values())
```

Signatures verified: `build_data_layout(fields: list[CobolField]) -> DataLayout` (`data_layout.py:698`) and `build_index_layout(*sections: list[CobolField]) -> DataLayout` (`data_layout.py:750`) — note the latter is variadic, so pass the field list as one positional section.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span.py -k field_layout -v`
Expected: FAIL — `AttributeError: 'FieldLayout' object has no attribute 'span'`

- [ ] **Step 3: Add the fields**

In `interpreter/cobol/data_layout.py`, add `from cobol_asg.source_span import SourceSpan` to the imports, then add to **both** dataclasses as the last field (so existing positional construction is unaffected):

```python
    span: SourceSpan | None = None
```

`FieldLayout` — after `renames_thru: str = ""` (`:97`).
`DataLayout` — after `element_size: int = 0` (`:142`), before any `field(default_factory=...)` entries if ordering complains.

Document the intent on `FieldLayout`:

```python
    span: SourceSpan | None = None
    """Where this field was declared, or None for compiler-allocated items.

    OCCURS elements inherit their parent's span: a subscripted access and
    its declaration share a source line. Index items have none — they
    correspond to no source text.
    """
```

- [ ] **Step 4: Populate the construction sites**

Apply the table above. Nine sites total; five take a span, four are deliberately left `None`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span.py -v`
Expected: PASS (10 tests)

- [ ] **Step 6: Run the COBOL suite and commit**

```bash
uv run python -m pytest tests/unit/cobol tests/unit/test_cobol_e2e.py -q
uv run python -m black .
git add interpreter/cobol/data_layout.py interpreter/cobol/emit_context.py tests/unit/cobol/test_source_span.py
git commit -m "feat(cobol): carry declaration spans through DataLayout and FieldLayout

Lowering iterates FieldLayout, not CobolField, so the declaring line has
to be copied across at layout construction. OCCURS elements inherit the
parent field's span; index items stay spanless.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `emit_inst` accepts and applies a span

This is the mechanism. After this task the plumbing works end to end, but almost nothing passes a span yet.

**Files:**
- Create: `interpreter/cobol/source_spans.py`
- Modify: `interpreter/cobol/emit_context.py:196-200`
- Test: `tests/unit/cobol/test_source_span.py` (append)

**Interfaces:**
- Consumes: `SourceSpan` from Task 1.
- Produces: `to_source_location(span) -> SourceLocation`; `EmitContext.emit_inst(inst, *, span=None)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/cobol/test_source_span.py`:

```python
from cobol_asg.source_span import SourceSpan as _Span
from interpreter.cobol.source_spans import to_source_location
from interpreter.ir import NO_SOURCE_LOCATION, SourceLocation


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_conversion_maps_transposed_field_names():
    """SourceSpan says line_start; SourceLocation says start_line."""
    loc = to_source_location(
        _Span(line_start=7, col_start=11, line_end=9, col_end=4)
    )
    assert loc == SourceLocation(
        start_line=7, start_col=11, end_line=9, end_col=4
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_conversion_of_none_is_the_unknown_location():
    assert to_source_location(None) == NO_SOURCE_LOCATION
    assert to_source_location(None).is_unknown()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span.py -k conversion -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.cobol.source_spans'`

- [ ] **Step 3: Write the conversion**

Create `interpreter/cobol/source_spans.py`:

```python
# pyright: standard
"""Conversion from the COBOL ASG's SourceSpan to the IR's SourceLocation.

This lives on the interpreter side on purpose: ``cobol_asg`` imports
nothing from ``interpreter`` and that one-way dependency is enforced by
import-linter. The ASG never learns about IR types.

The two types agree on convention — 1-based lines, 0-based columns — but
transpose their field names (``line_start`` vs ``start_line``), which is
the only thing this module exists to get right.
"""

from __future__ import annotations

from cobol_asg.source_span import SourceSpan
from interpreter.ir import NO_SOURCE_LOCATION, SourceLocation


def to_source_location(span: SourceSpan | None) -> SourceLocation:
    """Convert a COBOL span to an IR source location.

    A ``None`` span becomes ``NO_SOURCE_LOCATION`` rather than raising:
    plenty of emitted instructions (the program prologue, compiler-
    allocated index items) legitimately correspond to no source text.
    """
    if span is None:
        return NO_SOURCE_LOCATION
    return SourceLocation(
        start_line=span.line_start,
        start_col=span.col_start,
        end_line=span.line_end,
        end_col=span.col_end,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span.py -k conversion -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Write the failing test for `emit_inst`**

Append to `tests/unit/cobol/test_source_span.py`:

```python
from interpreter.instructions import Const
from interpreter.register import Register


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_emit_inst_stamps_the_span(cobol_emit_context):
    ctx = cobol_emit_context
    ctx.emit_inst(
        Const.int_(Register("%r0"), 1),
        span=_Span(line_start=7, col_start=11, line_end=7, col_end=21),
    )
    assert ctx.instructions[-1].source_location == SourceLocation(
        start_line=7, start_col=11, end_line=7, end_col=21
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_emit_inst_without_a_span_is_unknown(cobol_emit_context):
    ctx = cobol_emit_context
    ctx.emit_inst(Const.int_(Register("%r0"), 1))
    assert ctx.instructions[-1].source_location.is_unknown()


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_an_explicit_location_on_the_instruction_wins(cobol_emit_context):
    """Matches frontends/context.py:219-222 — explicit beats resolved."""
    ctx = cobol_emit_context
    explicit = SourceLocation(start_line=1, start_col=2, end_line=3, end_col=4)
    ctx.emit_inst(
        Const.int_(Register("%r0"), 1, source_location=explicit),
        span=_Span(line_start=7, col_start=11, line_end=7, col_end=21),
    )
    assert ctx.instructions[-1].source_location == explicit
```

You need a `cobol_emit_context` fixture, and **`tests/unit/cobol/conftest.py` does not exist yet** — create it. Build the `EmitContext` the same way `tests/unit/test_cobol_emit_context_registers.py` already does (read that file first and copy its construction; `EmitContext.__init__` takes a dispatch callback and an `InstructionIdSource`, so it is not a bare `EmitContext()`).

The emitted buffer is reached through the `instructions` property (`emit_context.py:162-164`, returning `self._instructions`) — `ctx.instructions` is correct, use it.

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span.py -k emit_inst -v`
Expected: FAIL — `TypeError: emit_inst() got an unexpected keyword argument 'span'`

- [ ] **Step 7: Implement**

Replace `EmitContext.emit_inst` at `interpreter/cobol/emit_context.py:196-200`:

```python
    def emit_inst(
        self, inst: InstructionBase, *, span: SourceSpan | None = None
    ) -> InstructionBase:
        """Emit a typed instruction directly, assigning it a stable id.

        ``span`` is the COBOL construct this instruction was lowered from.
        Precedence matches the tree-sitter frontends' ``node=`` parameter
        (``frontends/context.py:219-222``): a source location already on
        the instruction wins, then ``span``, then unknown.
        """
        inst = dataclasses.replace(inst, id=self._inst_ids.mint())
        if inst.source_location.is_unknown() and span is not None:
            inst = dataclasses.replace(
                inst, source_location=to_source_location(span)
            )
        self._instructions.append(inst)
        return inst
```

Add the imports:

```python
from cobol_asg.source_span import SourceSpan
from interpreter.cobol.source_spans import to_source_location
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span.py -v`
Expected: PASS (15 tests)

- [ ] **Step 9: Verify no regression and commit**

The parameter is optional, so no existing caller changes behaviour.

```bash
uv run python -m pytest tests/unit/cobol tests/unit/test_cobol_e2e.py -q
uv run python -m black .
uv run lint-imports
git add interpreter/cobol/source_spans.py interpreter/cobol/emit_context.py tests/unit/cobol/
git commit -m "feat(cobol): emit_inst accepts a source span

Adds the SourceSpan to SourceLocation conversion and an optional span=
keyword on emit_inst, following the precedence the tree-sitter frontends
use for node=. No caller passes one yet.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `EmitContext`'s emitting methods forward a span

21 `EmitContext` methods emit on their caller's behalf. Each gains a keyword-only `span` and forwards it to every `emit_inst` it makes. `inline_ir` is the important one: every instruction built by `ir_encoders.py` funnels through it, so stamping there covers all 80 raw appends in that module with zero changes to it.

**Files:**
- Modify: `interpreter/cobol/emit_context.py` (35 internal `emit_inst` calls, 27 `const_to_reg` calls, 3 `resolve_field_ref` calls)
- Test: `tests/unit/cobol/test_source_span.py` (append)

**Interfaces:**
- Consumes: `emit_inst(inst, *, span)` from Task 5.
- Produces: every public emitting method on `EmitContext` accepts keyword-only `span: SourceSpan | None = None`.

The methods, from `grep -n "def " interpreter/cobol/emit_context.py`:
`const_to_reg`, `resolve_field_ref`, `resolve_field_ref_from`, `inline_ir`, `_emit_load_region`, `_emit_write_region`, `_materialise_offset`, `emit_encode_value`, `_emit_hex_literal_bytes`, `emit_fill_raw_byte`, `_emit_ebcdic_spaces`, `emit_encode_alphanumeric`, `emit_encode_float`, `emit_encode_numeric`, `emit_field_encode`, `emit_decode_field`, `emit_decode_zoned_display`, `emit_read_region_raw`, `emit_write_region_raw`, `emit_to_string`, `_emit_blank_when_zero_wrap`, `emit_encode_from_string`, `emit_numeric_encode_from_string`, `emit_encode_and_write`, `emit_file_status_update`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/cobol/test_source_span.py`:

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_const_to_reg_stamps_the_span(cobol_emit_context):
    ctx = cobol_emit_context
    span = _Span(line_start=7, col_start=11, line_end=7, col_end=21)
    ctx.const_to_reg("42", span=span)
    assert ctx.instructions[-1].source_location.start_line == 7


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inline_ir_stamps_every_instruction_it_inlines(cobol_emit_context):
    """The ir_encoders builders emit into detached lists with no span of
    their own; inline_ir is where they acquire one."""
    ctx = cobol_emit_context
    span = _Span(line_start=7, col_start=11, line_end=7, col_end=21)
    before = len(ctx.instructions)
    ctx.emit_encode_numeric("WS_B", "42", _zoned_td(4), span=span)
    emitted = ctx.instructions[before:]
    assert len(emitted) > 5, "expected an inlined encoder body"
    assert all(i.source_location.start_line == 7 for i in emitted)
```

`_zoned_td(4)` is a helper you write in the test file returning a `CobolTypeDescriptor` for `PIC 9(4)` DISPLAY. Build it the way `tests/unit/test_cobol_types.py` does — run `grep -n "CobolTypeDescriptor(" tests/unit/test_cobol_types.py | head -3` and copy the real constructor call.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span.py -k "const_to_reg or inline_ir" -v`
Expected: FAIL — `TypeError: const_to_reg() got an unexpected keyword argument 'span'`

- [ ] **Step 3: Thread the span through every method**

For each of the 25 methods listed above: add `*, span: SourceSpan | None = None` to the signature (if it already has keyword-only args, add `span` alongside them), and pass `span=span` to every `emit_inst`, `const_to_reg`, `resolve_field_ref` and `inline_ir` call inside it.

`inline_ir` needs its stamping inside the loop at `:322-345`:

```python
    def inline_ir(
        self,
        ir_instructions: Sequence[InstructionBase],
        param_regs: dict[str, Register],
        *,
        span: SourceSpan | None = None,
    ) -> Register:
```

and its `self.emit_inst(remapped)` at `:345` becomes `self.emit_inst(remapped, span=span)`.

Its internal `self.const_to_reg(resolved_str)` at `:332` becomes `self.const_to_reg(resolved_str, span=span)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span.py -v`
Expected: PASS (17 tests)

- [ ] **Step 5: Run the COBOL suite and commit**

Every added parameter is optional, so no existing caller changes behaviour.

```bash
uv run python -m pytest tests/unit/cobol tests/unit/test_cobol_e2e.py -q
uv run python -m black .
git add interpreter/cobol/emit_context.py tests/unit/cobol/test_source_span.py
git commit -m "feat(cobol): EmitContext emitting methods forward a span

All 25 methods that emit on a caller's behalf now take keyword-only
span= and forward it. inline_ir stamps as it remaps, which covers every
instruction built by ir_encoders.py without touching that module.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Thread source spans through `lower_arithmetic.py`

Fully thread one module — its `emit_inst` calls, its `const_to_reg` calls and its `resolve_field_ref` calls — so that reviewing one file is a self-contained gate. This module has **91 `emit_inst`, 47 `const_to_reg`, 32 `resolve_field_ref` = 170 call sites**. It is the largest module, and the one most likely to surface a threading shape the others reuse.

**Files:**
- Modify: `interpreter/cobol/lower_arithmetic.py`
- Test: no new test file. Verified by the scripts in Steps 3 and 4 below; the permanent invariant tests arrive in Task 14.

**Interfaces:**
- Consumes: `EmitContext.emit_inst(inst, *, span: SourceSpan | None = None)` from Task 5, and the 25 forwarding `EmitContext` methods from Task 6.
- Produces: no new names. Existing private helpers in the file gain a keyword-only `span: SourceSpan | None = None` parameter.

**For each task, the procedure is:**

**Files:**
- Modify: the file(s) in the row
- Test: `tests/unit/cobol/test_source_span_coverage.py` (created in Task 14; until then, verify by the ad-hoc probe in Step 4)

**Interfaces:**
- Consumes: `emit_inst(inst, *, span)` and the 25 forwarding methods from Tasks 5 and 6.
- Produces: no new names. Existing private helpers in the file gain a keyword-only `span: SourceSpan | None = None` parameter.

- [ ] **Step 1: Find the entry points**

Run: `grep -n "^def \|^    def " interpreter/cobol/lower_arithmetic.py`

Public `lower_*` functions receive a statement (`stmt`) — that is the span source, `stmt.span`. Private `_emit_*`/`_lower_*` helpers generally do not; they need a keyword-only `span: SourceSpan | None = None` added to their signature, passed by their caller.

- [ ] **Step 2: Thread from the outside in**

In each public `lower_*(ctx, stmt, materialised)`, bind the span once at the top:

```python
    span = stmt.span
```

then add `span=span` to every `ctx.emit_inst(...)`, `ctx.const_to_reg(...)`, `ctx.resolve_field_ref(...)` and private-helper call in that function. Add `*, span: SourceSpan | None = None` to each private helper and repeat inside it.

Add the import: `from cobol_asg.source_span import SourceSpan`.

- [ ] **Step 3: Verify the file is fully threaded**

Run this, substituting the file:

```bash
uv run python - <<'PYEOF'
import ast, pathlib, sys

FILES = [
    "interpreter/cobol/lower_arithmetic.py",
]
missing = []
seen = 0
for name in FILES:
    path = pathlib.Path(name)
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"emit_inst", "const_to_reg", "resolve_field_ref"}):
            seen += 1
            if not any(k.arg == "span" for k in node.keywords):
                missing.append(f"  {path.name}:{node.lineno}  .{node.func.attr}()")
print(f"emitting calls seen: {seen}")
print(f"unthreaded calls: {len(missing)}")
print("\n".join(missing))
# A zero count for BOTH numbers means the check found nothing to check --
# treat that as a failure, not a pass.
sys.exit(1 if missing or seen == 0 else 0)
PYEOF
```

Expected: `unthreaded calls: 0` with a non-zero `emitting calls seen`, exit 0. A `seen` of 0 means the check matched nothing and is failing open — investigate rather than proceeding.

- [ ] **Step 4: Verify spans actually land in the IR**

```bash
uv run python - <<'PYEOF'
from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend

SRC = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(4) VALUE 5.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           MOVE 7 TO WS-B.
           ADD WS-A TO WS-B.
           DISPLAY WS-B.
           STOP RUN.
"""
parser = make_cobol_parser()
ir = CobolFrontend(parser).lower(SRC)
known = [i for i in ir if not i.source_location.is_unknown()]
print(f"{len(known)}/{len(ir)} instructions located")
PYEOF
```

Expected: the located count is strictly higher than before this task. It will not reach 100% until Task 13 is done.

- [ ] **Step 5: Run the COBOL suite**

Run: `uv run python -m pytest tests/unit/cobol tests/unit/test_cobol_e2e.py tests/integration -q -k cobol`
Expected: PASS. Adding a source location never changes execution semantics — a failure here means you passed the wrong variable (for example a loop variable shadowing `stmt`), not that a test is wrong.

- [ ] **Step 6: Commit**

```bash
uv run python -m black .
git add interpreter/cobol/lower_arithmetic.py
git commit -m "feat(cobol): thread source spans through lower_arithmetic.py

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Thread source spans through `lower_io.py`

Fully thread one module — its `emit_inst` calls, its `const_to_reg` calls and its `resolve_field_ref` calls — so that reviewing one file is a self-contained gate. This module has **54 `emit_inst`, 25 `const_to_reg`, 4 `resolve_field_ref` = 83 call sites**. It is file I/O verbs; several private helpers (`_emit_conditional_use_perform`, `_emit_invalid_key_branch`, `emit_use_trigger`) need a span parameter added.

**Files:**
- Modify: `interpreter/cobol/lower_io.py`
- Test: no new test file. Verified by the scripts in Steps 3 and 4 below; the permanent invariant tests arrive in Task 14.

**Interfaces:**
- Consumes: `EmitContext.emit_inst(inst, *, span: SourceSpan | None = None)` from Task 5, and the 25 forwarding `EmitContext` methods from Task 6.
- Produces: no new names. Existing private helpers in the file gain a keyword-only `span: SourceSpan | None = None` parameter.

**For each task, the procedure is:**

**Files:**
- Modify: the file(s) in the row
- Test: `tests/unit/cobol/test_source_span_coverage.py` (created in Task 14; until then, verify by the ad-hoc probe in Step 4)

**Interfaces:**
- Consumes: `emit_inst(inst, *, span)` and the 25 forwarding methods from Tasks 5 and 6.
- Produces: no new names. Existing private helpers in the file gain a keyword-only `span: SourceSpan | None = None` parameter.

- [ ] **Step 1: Find the entry points**

Run: `grep -n "^def \|^    def " interpreter/cobol/lower_io.py`

Public `lower_*` functions receive a statement (`stmt`) — that is the span source, `stmt.span`. Private `_emit_*`/`_lower_*` helpers generally do not; they need a keyword-only `span: SourceSpan | None = None` added to their signature, passed by their caller.

- [ ] **Step 2: Thread from the outside in**

In each public `lower_*(ctx, stmt, materialised)`, bind the span once at the top:

```python
    span = stmt.span
```

then add `span=span` to every `ctx.emit_inst(...)`, `ctx.const_to_reg(...)`, `ctx.resolve_field_ref(...)` and private-helper call in that function. Add `*, span: SourceSpan | None = None` to each private helper and repeat inside it.

Add the import: `from cobol_asg.source_span import SourceSpan`.

- [ ] **Step 3: Verify the file is fully threaded**

Run this, substituting the file:

```bash
uv run python - <<'PYEOF'
import ast, pathlib, sys

FILES = [
    "interpreter/cobol/lower_io.py",
]
missing = []
seen = 0
for name in FILES:
    path = pathlib.Path(name)
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"emit_inst", "const_to_reg", "resolve_field_ref"}):
            seen += 1
            if not any(k.arg == "span" for k in node.keywords):
                missing.append(f"  {path.name}:{node.lineno}  .{node.func.attr}()")
print(f"emitting calls seen: {seen}")
print(f"unthreaded calls: {len(missing)}")
print("\n".join(missing))
# A zero count for BOTH numbers means the check found nothing to check --
# treat that as a failure, not a pass.
sys.exit(1 if missing or seen == 0 else 0)
PYEOF
```

Expected: `unthreaded calls: 0` with a non-zero `emitting calls seen`, exit 0. A `seen` of 0 means the check matched nothing and is failing open — investigate rather than proceeding.

- [ ] **Step 4: Verify spans actually land in the IR**

```bash
uv run python - <<'PYEOF'
from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend

SRC = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(4) VALUE 5.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           MOVE 7 TO WS-B.
           ADD WS-A TO WS-B.
           DISPLAY WS-B.
           STOP RUN.
"""
parser = make_cobol_parser()
ir = CobolFrontend(parser).lower(SRC)
known = [i for i in ir if not i.source_location.is_unknown()]
print(f"{len(known)}/{len(ir)} instructions located")
PYEOF
```

Expected: the located count is strictly higher than before this task. It will not reach 100% until Task 13 is done.

- [ ] **Step 5: Run the COBOL suite**

Run: `uv run python -m pytest tests/unit/cobol tests/unit/test_cobol_e2e.py tests/integration -q -k cobol`
Expected: PASS. Adding a source location never changes execution semantics — a failure here means you passed the wrong variable (for example a loop variable shadowing `stmt`), not that a test is wrong.

- [ ] **Step 6: Commit**

```bash
uv run python -m black .
git add interpreter/cobol/lower_io.py
git commit -m "feat(cobol): thread source spans through lower_io.py

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Thread source spans through `lower_string_inspect.py`

Fully thread one module — its `emit_inst` calls, its `const_to_reg` calls and its `resolve_field_ref` calls — so that reviewing one file is a self-contained gate. This module has **32 `emit_inst`, 35 `const_to_reg`, 14 `resolve_field_ref` = 81 call sites**. It is STRING/UNSTRING/INSPECT; note it is `const_to_reg`-heavy (35 calls) relative to its size.

**Files:**
- Modify: `interpreter/cobol/lower_string_inspect.py`
- Test: no new test file. Verified by the scripts in Steps 3 and 4 below; the permanent invariant tests arrive in Task 14.

**Interfaces:**
- Consumes: `EmitContext.emit_inst(inst, *, span: SourceSpan | None = None)` from Task 5, and the 25 forwarding `EmitContext` methods from Task 6.
- Produces: no new names. Existing private helpers in the file gain a keyword-only `span: SourceSpan | None = None` parameter.

**For each task, the procedure is:**

**Files:**
- Modify: the file(s) in the row
- Test: `tests/unit/cobol/test_source_span_coverage.py` (created in Task 14; until then, verify by the ad-hoc probe in Step 4)

**Interfaces:**
- Consumes: `emit_inst(inst, *, span)` and the 25 forwarding methods from Tasks 5 and 6.
- Produces: no new names. Existing private helpers in the file gain a keyword-only `span: SourceSpan | None = None` parameter.

- [ ] **Step 1: Find the entry points**

Run: `grep -n "^def \|^    def " interpreter/cobol/lower_string_inspect.py`

Public `lower_*` functions receive a statement (`stmt`) — that is the span source, `stmt.span`. Private `_emit_*`/`_lower_*` helpers generally do not; they need a keyword-only `span: SourceSpan | None = None` added to their signature, passed by their caller.

- [ ] **Step 2: Thread from the outside in**

In each public `lower_*(ctx, stmt, materialised)`, bind the span once at the top:

```python
    span = stmt.span
```

then add `span=span` to every `ctx.emit_inst(...)`, `ctx.const_to_reg(...)`, `ctx.resolve_field_ref(...)` and private-helper call in that function. Add `*, span: SourceSpan | None = None` to each private helper and repeat inside it.

Add the import: `from cobol_asg.source_span import SourceSpan`.

- [ ] **Step 3: Verify the file is fully threaded**

Run this, substituting the file:

```bash
uv run python - <<'PYEOF'
import ast, pathlib, sys

FILES = [
    "interpreter/cobol/lower_string_inspect.py",
]
missing = []
seen = 0
for name in FILES:
    path = pathlib.Path(name)
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"emit_inst", "const_to_reg", "resolve_field_ref"}):
            seen += 1
            if not any(k.arg == "span" for k in node.keywords):
                missing.append(f"  {path.name}:{node.lineno}  .{node.func.attr}()")
print(f"emitting calls seen: {seen}")
print(f"unthreaded calls: {len(missing)}")
print("\n".join(missing))
# A zero count for BOTH numbers means the check found nothing to check --
# treat that as a failure, not a pass.
sys.exit(1 if missing or seen == 0 else 0)
PYEOF
```

Expected: `unthreaded calls: 0` with a non-zero `emitting calls seen`, exit 0. A `seen` of 0 means the check matched nothing and is failing open — investigate rather than proceeding.

- [ ] **Step 4: Verify spans actually land in the IR**

```bash
uv run python - <<'PYEOF'
from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend

SRC = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(4) VALUE 5.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           MOVE 7 TO WS-B.
           ADD WS-A TO WS-B.
           DISPLAY WS-B.
           STOP RUN.
"""
parser = make_cobol_parser()
ir = CobolFrontend(parser).lower(SRC)
known = [i for i in ir if not i.source_location.is_unknown()]
print(f"{len(known)}/{len(ir)} instructions located")
PYEOF
```

Expected: the located count is strictly higher than before this task. It will not reach 100% until Task 13 is done.

- [ ] **Step 5: Run the COBOL suite**

Run: `uv run python -m pytest tests/unit/cobol tests/unit/test_cobol_e2e.py tests/integration -q -k cobol`
Expected: PASS. Adding a source location never changes execution semantics — a failure here means you passed the wrong variable (for example a loop variable shadowing `stmt`), not that a test is wrong.

- [ ] **Step 6: Commit**

```bash
uv run python -m black .
git add interpreter/cobol/lower_string_inspect.py
git commit -m "feat(cobol): thread source spans through lower_string_inspect.py

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Thread source spans through `condition_lowering.py`

Fully thread one module — its `emit_inst` calls, its `const_to_reg` calls and its `resolve_field_ref` calls — so that reviewing one file is a self-contained gate. This module has **26 `emit_inst`, 29 `const_to_reg`, 14 `resolve_field_ref` = 69 call sites**. It is condition and 88-level lowering; `_lower_expr_dict` and `_lower_condition_str` are recursive, so the span threads down through the recursion.

**Cross-module call sites you also own.** `lower_expr_node` (defined in this module) is called from `interpreter/cobol/emit_context.py` inside `resolve_field_ref` to lower subscript expressions — two call sites, `lower_expr_node(self, subscripts[0], materialised)` and `lower_expr_node(self, sub_node, materialised)`. Task 6 correctly left them alone because `lower_expr_node` had no `span` parameter yet. When you add `span` to `lower_expr_node`, you **must** update both call sites in `emit_context.py` to pass `span=span` (the enclosing `resolve_field_ref` already has `span` in scope). Task 14's static lint only inspects `.emit_inst` / `.const_to_reg` / `.resolve_field_ref` attribute calls, so it will NOT catch a missed plain-function call here — you are the only safeguard. Search the whole `interpreter/cobol/` tree for other callers of any function whose signature you change in this task, and update all of them.

**Files:**
- Modify: `interpreter/cobol/condition_lowering.py`
- Modify: `interpreter/cobol/emit_context.py` (the two `lower_expr_node` call sites in `resolve_field_ref` only)
- Test: no new test file. Verified by the scripts in Steps 3 and 4 below; the permanent invariant tests arrive in Task 14.

**Interfaces:**
- Consumes: `EmitContext.emit_inst(inst, *, span: SourceSpan | None = None)` from Task 5, and the 25 forwarding `EmitContext` methods from Task 6.
- Produces: no new names. Existing private helpers in the file gain a keyword-only `span: SourceSpan | None = None` parameter.

**For each task, the procedure is:**

**Files:**
- Modify: the file(s) in the row
- Test: `tests/unit/cobol/test_source_span_coverage.py` (created in Task 14; until then, verify by the ad-hoc probe in Step 4)

**Interfaces:**
- Consumes: `emit_inst(inst, *, span)` and the 25 forwarding methods from Tasks 5 and 6.
- Produces: no new names. Existing private helpers in the file gain a keyword-only `span: SourceSpan | None = None` parameter.

- [ ] **Step 1: Find the entry points**

Run: `grep -n "^def \|^    def " interpreter/cobol/condition_lowering.py`

Public `lower_*` functions receive a statement (`stmt`) — that is the span source, `stmt.span`. Private `_emit_*`/`_lower_*` helpers generally do not; they need a keyword-only `span: SourceSpan | None = None` added to their signature, passed by their caller.

- [ ] **Step 2: Thread from the outside in**

In each public `lower_*(ctx, stmt, materialised)`, bind the span once at the top:

```python
    span = stmt.span
```

then add `span=span` to every `ctx.emit_inst(...)`, `ctx.const_to_reg(...)`, `ctx.resolve_field_ref(...)` and private-helper call in that function. Add `*, span: SourceSpan | None = None` to each private helper and repeat inside it.

Add the import: `from cobol_asg.source_span import SourceSpan`.

- [ ] **Step 3: Verify the file is fully threaded**

Run this, substituting the file:

```bash
uv run python - <<'PYEOF'
import ast, pathlib, sys

FILES = [
    "interpreter/cobol/condition_lowering.py",
]
missing = []
seen = 0
for name in FILES:
    path = pathlib.Path(name)
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"emit_inst", "const_to_reg", "resolve_field_ref"}):
            seen += 1
            if not any(k.arg == "span" for k in node.keywords):
                missing.append(f"  {path.name}:{node.lineno}  .{node.func.attr}()")
print(f"emitting calls seen: {seen}")
print(f"unthreaded calls: {len(missing)}")
print("\n".join(missing))
# A zero count for BOTH numbers means the check found nothing to check --
# treat that as a failure, not a pass.
sys.exit(1 if missing or seen == 0 else 0)
PYEOF
```

Expected: `unthreaded calls: 0` with a non-zero `emitting calls seen`, exit 0. A `seen` of 0 means the check matched nothing and is failing open — investigate rather than proceeding.

- [ ] **Step 4: Verify spans actually land in the IR**

```bash
uv run python - <<'PYEOF'
from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend

SRC = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(4) VALUE 5.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           MOVE 7 TO WS-B.
           ADD WS-A TO WS-B.
           DISPLAY WS-B.
           STOP RUN.
"""
parser = make_cobol_parser()
ir = CobolFrontend(parser).lower(SRC)
known = [i for i in ir if not i.source_location.is_unknown()]
print(f"{len(known)}/{len(ir)} instructions located")
PYEOF
```

Expected: the located count is strictly higher than before this task. It will not reach 100% until Task 13 is done.

- [ ] **Step 5: Run the COBOL suite**

Run: `uv run python -m pytest tests/unit/cobol tests/unit/test_cobol_e2e.py tests/integration -q -k cobol`
Expected: PASS. Adding a source location never changes execution semantics — a failure here means you passed the wrong variable (for example a loop variable shadowing `stmt`), not that a test is wrong.

- [ ] **Step 6: Commit**

```bash
uv run python -m black .
git add interpreter/cobol/condition_lowering.py
git commit -m "feat(cobol): thread source spans through condition_lowering.py

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Thread source spans through `lower_perform.py`

Fully thread one module — its `emit_inst` calls, its `const_to_reg` calls and its `resolve_field_ref` calls — so that reviewing one file is a self-contained gate. This module has **43 `emit_inst`, 7 `const_to_reg`, 5 `resolve_field_ref` = 55 call sites**. It is PERFORM in all its forms; `_emit_test_before_level` and `_emit_test_after_varying` are the helpers needing a span parameter.

**Files:**
- Modify: `interpreter/cobol/lower_perform.py`
- Test: no new test file. Verified by the scripts in Steps 3 and 4 below; the permanent invariant tests arrive in Task 14.

**Interfaces:**
- Consumes: `EmitContext.emit_inst(inst, *, span: SourceSpan | None = None)` from Task 5, and the 25 forwarding `EmitContext` methods from Task 6.
- Produces: no new names. Existing private helpers in the file gain a keyword-only `span: SourceSpan | None = None` parameter.

**For each task, the procedure is:**

**Files:**
- Modify: the file(s) in the row
- Test: `tests/unit/cobol/test_source_span_coverage.py` (created in Task 14; until then, verify by the ad-hoc probe in Step 4)

**Interfaces:**
- Consumes: `emit_inst(inst, *, span)` and the 25 forwarding methods from Tasks 5 and 6.
- Produces: no new names. Existing private helpers in the file gain a keyword-only `span: SourceSpan | None = None` parameter.

- [ ] **Step 1: Find the entry points**

Run: `grep -n "^def \|^    def " interpreter/cobol/lower_perform.py`

Public `lower_*` functions receive a statement (`stmt`) — that is the span source, `stmt.span`. Private `_emit_*`/`_lower_*` helpers generally do not; they need a keyword-only `span: SourceSpan | None = None` added to their signature, passed by their caller.

- [ ] **Step 2: Thread from the outside in**

In each public `lower_*(ctx, stmt, materialised)`, bind the span once at the top:

```python
    span = stmt.span
```

then add `span=span` to every `ctx.emit_inst(...)`, `ctx.const_to_reg(...)`, `ctx.resolve_field_ref(...)` and private-helper call in that function. Add `*, span: SourceSpan | None = None` to each private helper and repeat inside it.

Add the import: `from cobol_asg.source_span import SourceSpan`.

- [ ] **Step 3: Verify the file is fully threaded**

Run this, substituting the file:

```bash
uv run python - <<'PYEOF'
import ast, pathlib, sys

FILES = [
    "interpreter/cobol/lower_perform.py",
]
missing = []
seen = 0
for name in FILES:
    path = pathlib.Path(name)
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"emit_inst", "const_to_reg", "resolve_field_ref"}):
            seen += 1
            if not any(k.arg == "span" for k in node.keywords):
                missing.append(f"  {path.name}:{node.lineno}  .{node.func.attr}()")
print(f"emitting calls seen: {seen}")
print(f"unthreaded calls: {len(missing)}")
print("\n".join(missing))
# A zero count for BOTH numbers means the check found nothing to check --
# treat that as a failure, not a pass.
sys.exit(1 if missing or seen == 0 else 0)
PYEOF
```

Expected: `unthreaded calls: 0` with a non-zero `emitting calls seen`, exit 0. A `seen` of 0 means the check matched nothing and is failing open — investigate rather than proceeding.

- [ ] **Step 4: Verify spans actually land in the IR**

```bash
uv run python - <<'PYEOF'
from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend

SRC = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(4) VALUE 5.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           MOVE 7 TO WS-B.
           ADD WS-A TO WS-B.
           DISPLAY WS-B.
           STOP RUN.
"""
parser = make_cobol_parser()
ir = CobolFrontend(parser).lower(SRC)
known = [i for i in ir if not i.source_location.is_unknown()]
print(f"{len(known)}/{len(ir)} instructions located")
PYEOF
```

Expected: the located count is strictly higher than before this task. It will not reach 100% until Task 13 is done.

- [ ] **Step 5: Run the COBOL suite**

Run: `uv run python -m pytest tests/unit/cobol tests/unit/test_cobol_e2e.py tests/integration -q -k cobol`
Expected: PASS. Adding a source location never changes execution semantics — a failure here means you passed the wrong variable (for example a loop variable shadowing `stmt`), not that a test is wrong.

- [ ] **Step 6: Commit**

```bash
uv run python -m black .
git add interpreter/cobol/lower_perform.py
git commit -m "feat(cobol): thread source spans through lower_perform.py

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Thread source spans through `lower_search.py`

Fully thread one module — its `emit_inst` calls, its `const_to_reg` calls and its `resolve_field_ref` calls — so that reviewing one file is a self-contained gate. This module has **19 `emit_inst`, 4 `const_to_reg`, 3 `resolve_field_ref` = 26 call sites**. It is SEARCH and SEARCH ALL.

**Files:**
- Modify: `interpreter/cobol/lower_search.py`
- Test: no new test file. Verified by the scripts in Steps 3 and 4 below; the permanent invariant tests arrive in Task 14.

**Interfaces:**
- Consumes: `EmitContext.emit_inst(inst, *, span: SourceSpan | None = None)` from Task 5, and the 25 forwarding `EmitContext` methods from Task 6.
- Produces: no new names. Existing private helpers in the file gain a keyword-only `span: SourceSpan | None = None` parameter.

**For each task, the procedure is:**

**Files:**
- Modify: the file(s) in the row
- Test: `tests/unit/cobol/test_source_span_coverage.py` (created in Task 14; until then, verify by the ad-hoc probe in Step 4)

**Interfaces:**
- Consumes: `emit_inst(inst, *, span)` and the 25 forwarding methods from Tasks 5 and 6.
- Produces: no new names. Existing private helpers in the file gain a keyword-only `span: SourceSpan | None = None` parameter.

- [ ] **Step 1: Find the entry points**

Run: `grep -n "^def \|^    def " interpreter/cobol/lower_search.py`

Public `lower_*` functions receive a statement (`stmt`) — that is the span source, `stmt.span`. Private `_emit_*`/`_lower_*` helpers generally do not; they need a keyword-only `span: SourceSpan | None = None` added to their signature, passed by their caller.

- [ ] **Step 2: Thread from the outside in**

In each public `lower_*(ctx, stmt, materialised)`, bind the span once at the top:

```python
    span = stmt.span
```

then add `span=span` to every `ctx.emit_inst(...)`, `ctx.const_to_reg(...)`, `ctx.resolve_field_ref(...)` and private-helper call in that function. Add `*, span: SourceSpan | None = None` to each private helper and repeat inside it.

Add the import: `from cobol_asg.source_span import SourceSpan`.

- [ ] **Step 3: Verify the file is fully threaded**

Run this, substituting the file:

```bash
uv run python - <<'PYEOF'
import ast, pathlib, sys

FILES = [
    "interpreter/cobol/lower_search.py",
]
missing = []
seen = 0
for name in FILES:
    path = pathlib.Path(name)
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"emit_inst", "const_to_reg", "resolve_field_ref"}):
            seen += 1
            if not any(k.arg == "span" for k in node.keywords):
                missing.append(f"  {path.name}:{node.lineno}  .{node.func.attr}()")
print(f"emitting calls seen: {seen}")
print(f"unthreaded calls: {len(missing)}")
print("\n".join(missing))
# A zero count for BOTH numbers means the check found nothing to check --
# treat that as a failure, not a pass.
sys.exit(1 if missing or seen == 0 else 0)
PYEOF
```

Expected: `unthreaded calls: 0` with a non-zero `emitting calls seen`, exit 0. A `seen` of 0 means the check matched nothing and is failing open — investigate rather than proceeding.

- [ ] **Step 4: Verify spans actually land in the IR**

```bash
uv run python - <<'PYEOF'
from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend

SRC = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(4) VALUE 5.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           MOVE 7 TO WS-B.
           ADD WS-A TO WS-B.
           DISPLAY WS-B.
           STOP RUN.
"""
parser = make_cobol_parser()
ir = CobolFrontend(parser).lower(SRC)
known = [i for i in ir if not i.source_location.is_unknown()]
print(f"{len(known)}/{len(ir)} instructions located")
PYEOF
```

Expected: the located count is strictly higher than before this task. It will not reach 100% until Task 13 is done.

- [ ] **Step 5: Run the COBOL suite**

Run: `uv run python -m pytest tests/unit/cobol tests/unit/test_cobol_e2e.py tests/integration -q -k cobol`
Expected: PASS. Adding a source location never changes execution semantics — a failure here means you passed the wrong variable (for example a loop variable shadowing `stmt`), not that a test is wrong.

- [ ] **Step 6: Commit**

```bash
uv run python -m black .
git add interpreter/cobol/lower_search.py
git commit -m "feat(cobol): thread source spans through lower_search.py

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Thread source spans through `lower_call.py`

Fully thread one module — its `emit_inst` calls, its `const_to_reg` calls and its `resolve_field_ref` calls — so that reviewing one file is a self-contained gate. This module has **15 `emit_inst`, 6 `const_to_reg`, 3 `resolve_field_ref` = 24 call sites**. It is the four small remaining modules, batched because each is a handful of call sites.

**Scope amended mid-execution (two additions — read before the generic procedure below).**

**A. Section spans need a bridge change first.** The spec assumed the bridge already emits positions for both paragraphs and sections. It does for paragraphs (`AsgSerializer.java` paragraph serializer, and `CobolParagraph.span` from Task 2), but NOT for sections: the section serializer (`AsgSerializer.java`, the loop building `sectionObj`, around line 270) never calls `addSpan`, and `CobolSection` (`cobol_asg/asg_types.py`) has no `span` field. Without this, every `section_<name>` label stays unlocated. Do this as a SEPARATE first commit:
1. Write a failing test in `tests/unit/cobol/test_source_span.py` (imports at top) parsing a program with a named `SECTION` containing a paragraph, asserting the `CobolSection` has a span whose `line_start` is the SECTION header's line.
2. In `AsgSerializer.java`, call `StatementSerializer.addSpan(sectionObj, section.getCtx())` when building `sectionObj`.
3. Add `span: SourceSpan | None = None` to `CobolSection`, parse it with `SourceSpan.from_dict(data)` in `from_dict`, and write it back with `self.span.write_into(result)` in `to_dict` — exactly the `CobolParagraph` pattern from Task 2, including the round-trip.
4. `make jar-force` (mandatory — `make jar` will not rebuild), `cd proleap-bridge && mvn test -q`, then the focused test must pass. This commit adds 1 test.

**B. Threading `lower_procedure.py`.** Labels and continuations belong to the construct they open: in `lower_section`, pass `span=section.span`; in `lower_paragraph`, pass `span=para.span`. `lower_statement(...)` calls dispatch real statements and get no span (rule 3). `lower_procedure_division` emits nothing itself.

**C. Region-level data-division instructions are deliberately spanless — mark them, don't invent a line.**
- `lower_data_division`: the per-field VALUE encode passes `span=fl.span` (as the generic procedure shows). The `Const` holding `layout.total_bytes` and the `AllocRegion` describe the whole region, not any one declaration: pass `span=None` explicitly at those two calls, each with a trailing comment `# region-level: no single declaration`. The explicit keyword satisfies Task 14's lint and documents the intent at the call site.
- `lower_sectioned_data_division`: every instruction it emits is region binding plumbing (`LoadVar` of `__ws_region`, `__params_region`, the program singleton). It corresponds to no source line as a whole, so do NOT thread it: it is added to Task 14's `SPANLESS_FUNCTIONS` allowlist instead. Leave its calls unchanged.

**D. `lower_call.py`.** `lower_call`, `lower_alter`, `lower_entry` each bind `span = stmt.span`. `lower_call` also calls `ctx._emit_load_region` / `ctx._emit_write_region` (2 each) — both accept `span`; pass it.

**E. `field_resolution.py`** has no emitting calls (its `resolve_field_ref` is a module-level function, not an `EmitContext` method). Nothing to thread — confirm and say so.

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/AsgSerializer.java` (section `addSpan` only)
- Modify: `cobol_asg/asg_types.py` (`CobolSection.span` only)
- Modify: `tests/unit/cobol/test_source_span.py` (one section-span test)
- Modify: `interpreter/cobol/lower_call.py`
- Modify: `interpreter/cobol/lower_procedure.py`
- Modify: `interpreter/cobol/lower_data_division.py`
- Modify: `interpreter/cobol/field_resolution.py`
- Test: no new test file. Verified by the scripts in Steps 3 and 4 below; the permanent invariant tests arrive in Task 14.

**Interfaces:**
- Consumes: `EmitContext.emit_inst(inst, *, span: SourceSpan | None = None)` from Task 5, and the 25 forwarding `EmitContext` methods from Task 6.
- Produces: no new names. Existing private helpers in the file gain a keyword-only `span: SourceSpan | None = None` parameter.

**`lower_data_division.py` is special:** its spans come from `FieldLayout.span` (Task 4), not from a statement. In `lower_data_division()` the per-field loop becomes:

```python
    for fl in fields_with_values:
        ctx.emit_field_encode(
            region_reg, fl, fl.value,
            extent=whole_field_extent(fl, region),
            span=fl.span,
        )
```

The `AllocRegion` and its size `Const` at the top of that function describe the region as a whole, not any one field, and take no span.

**For each task, the procedure is:**

**Files:**
- Modify: the file(s) in the row
- Test: `tests/unit/cobol/test_source_span_coverage.py` (created in Task 14; until then, verify by the ad-hoc probe in Step 4)

**Interfaces:**
- Consumes: `emit_inst(inst, *, span)` and the 25 forwarding methods from Tasks 5 and 6.
- Produces: no new names. Existing private helpers in the file gain a keyword-only `span: SourceSpan | None = None` parameter.

- [ ] **Step 1: Find the entry points**

Run: `grep -n "^def \|^    def " interpreter/cobol/lower_call.py interpreter/cobol/lower_procedure.py interpreter/cobol/lower_data_division.py interpreter/cobol/field_resolution.py`

Public `lower_*` functions receive a statement (`stmt`) — that is the span source, `stmt.span`. Private `_emit_*`/`_lower_*` helpers generally do not; they need a keyword-only `span: SourceSpan | None = None` added to their signature, passed by their caller.

- [ ] **Step 2: Thread from the outside in**

In each public `lower_*(ctx, stmt, materialised)`, bind the span once at the top:

```python
    span = stmt.span
```

then add `span=span` to every `ctx.emit_inst(...)`, `ctx.const_to_reg(...)`, `ctx.resolve_field_ref(...)` and private-helper call in that function. Add `*, span: SourceSpan | None = None` to each private helper and repeat inside it.

Add the import: `from cobol_asg.source_span import SourceSpan`.

- [ ] **Step 3: Verify the file is fully threaded**

Run this, substituting the file:

```bash
uv run python - <<'PYEOF'
import ast, pathlib, sys

FILES = [
    "interpreter/cobol/lower_call.py",
    "interpreter/cobol/lower_procedure.py",
    "interpreter/cobol/lower_data_division.py",
    "interpreter/cobol/field_resolution.py",
]
missing = []
seen = 0
for name in FILES:
    path = pathlib.Path(name)
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"emit_inst", "const_to_reg", "resolve_field_ref"}):
            seen += 1
            if not any(k.arg == "span" for k in node.keywords):
                missing.append(f"  {path.name}:{node.lineno}  .{node.func.attr}()")
print(f"emitting calls seen: {seen}")
print(f"unthreaded calls: {len(missing)}")
print("\n".join(missing))
# A zero count for BOTH numbers means the check found nothing to check --
# treat that as a failure, not a pass.
sys.exit(1 if missing or seen == 0 else 0)
PYEOF
```

Expected: `unthreaded calls: 0` with a non-zero `emitting calls seen`, exit 0. A `seen` of 0 means the check matched nothing and is failing open — investigate rather than proceeding.

- [ ] **Step 4: Verify spans actually land in the IR**

```bash
uv run python - <<'PYEOF'
from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend

SRC = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(4) VALUE 5.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           MOVE 7 TO WS-B.
           ADD WS-A TO WS-B.
           DISPLAY WS-B.
           STOP RUN.
"""
parser = make_cobol_parser()
ir = CobolFrontend(parser).lower(SRC)
known = [i for i in ir if not i.source_location.is_unknown()]
print(f"{len(known)}/{len(ir)} instructions located")
PYEOF
```

Expected: the located count is strictly higher than before this task. It will not reach 100% until Task 13 is done.

- [ ] **Step 5: Run the COBOL suite**

Run: `uv run python -m pytest tests/unit/cobol tests/unit/test_cobol_e2e.py tests/integration -q -k cobol`
Expected: PASS. Adding a source location never changes execution semantics — a failure here means you passed the wrong variable (for example a loop variable shadowing `stmt`), not that a test is wrong.

- [ ] **Step 6: Commit**

```bash
uv run python -m black .
git add interpreter/cobol/lower_call.py interpreter/cobol/lower_procedure.py interpreter/cobol/lower_data_division.py interpreter/cobol/field_resolution.py
git commit -m "feat(cobol): thread source spans through the remaining lowering modules

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 15: Bridge emits spans for IF THEN/ELSE branch statements

**Execution order: run this BEFORE Task 11.** It was added mid-execution after Task 10's review found that statements inside `IF` branches reach Python with `span=None`, which Task 14's nesting test depends on.

**The defect.** `addSpan` is applied in exactly one place: `StatementSerializer.serializeStatements(List<Statement>)`. Every container of child statements (EVALUATE WHEN, inline PERFORM, ON SIZE ERROR, AT END, INVALID KEY, SEARCH WHEN) routes its children through that method, so their children get spans. The `IF` serializer does not: its THEN and ELSE branches loop and call the single-statement `serializeStatement(...)` directly (`StatementSerializer.java`, the loops over `thenBlock.getStatements()` and `elseBlock.getStatements()`, around lines 647 and 661), bypassing `addSpan`. Verified: for `IF WS-A > 0 / MOVE 7 TO WS-B / END-IF`, the `IfStatement` has a span but its child `MoveStatement` has `span=None`, while an `ADD` inside an inline `PERFORM` has a correct span. Those two loops are the only direct child-`serializeStatement` loops in the file.

**Files:**
- Modify: `proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java` (the IF THEN/ELSE child loops only)
- Test: `tests/unit/cobol/test_source_span.py` (append)

**Interfaces:**
- Consumes: `StatementSerializer.serializeStatements(List<Statement>)` and `addSpan` (Task 3).
- Produces: `IfStatement.children[i].span` and `IfStatement.else_children[i].span` are populated.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/cobol/test_source_span.py` (imports at the top of the file):

```python
IF_BRANCH_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. IFBRANCH.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(4) VALUE 5.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           IF WS-A > 0
               MOVE 7 TO WS-B
           ELSE
               MOVE 9 TO WS-B
           END-IF.
           STOP RUN.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_if_branch_statements_carry_their_own_spans():
    """THEN-branch MOVE is on line 9, ELSE-branch MOVE on line 11."""
    asg = make_cobol_parser().parse(IF_BRANCH_SOURCE)
    if_stmt = asg.statements[0]
    assert if_stmt.span is not None and if_stmt.span.line_start == 8
    (then_move,) = if_stmt.children
    (else_move,) = if_stmt.else_children
    assert then_move.span is not None and then_move.span.line_start == 9
    assert else_move.span is not None and else_move.span.line_start == 11
```

If `IfStatement` names its branch lists differently, read `cobol_asg/cobol_statements.py` and use the real attribute names.

- [ ] **Step 2: Run it and watch it fail**

Run: `PYTEST_ADDOPTS="-n 2" make test PYTEST_ARGS="tests/unit/cobol/test_source_span.py -k if_branch -q"`
Expected: FAIL on `then_move.span is not None`.

- [ ] **Step 3: Route IF branches through serializeStatements**

Replace each of the two child loops with the list method, preserving the existing "only add the key when non-empty" behaviour:

```java
        JsonArray children = new JsonArray();
        Then thenBlock = stmt.getThen();
        if (thenBlock != null && thenBlock.getStatements() != null) {
            children = serializeStatements(thenBlock.getStatements());
        }
        if (children.size() > 0) {
            obj.add("children", children);
        }

        JsonArray elseChildren = new JsonArray();
        Else elseBlock = stmt.getElse();
        if (elseBlock != null && elseBlock.getStatements() != null) {
            elseChildren = serializeStatements(elseBlock.getStatements());
        }
        if (elseChildren.size() > 0) {
            obj.add("else_children", elseChildren);
        }
```

`serializeStatements` already skips `null` results exactly as the removed loops did, so the only behavioural change is that each child gains its span keys.

- [ ] **Step 4: Rebuild the JAR — mandatory**

Run: `make jar-force`. Plain `make jar` will NOT rebuild when sources change.

- [ ] **Step 5: Run the Java tests and the Python test**

```bash
cd proleap-bridge && mvn test -q; cd ..
PYTEST_ADDOPTS="-n 2" make test PYTEST_ARGS="tests/unit/cobol/test_source_span.py -q"
```

Expected: Java tests all pass; the new test passes.

- [ ] **Step 6: Full suite and commit**

The suite gains 1 test. Because nested IF-branch statements now carry spans, a test that encoded the old "no location" behaviour could fail — if so, stop and report it; do not edit it.

```bash
uv run python -m black .
git add proleap-bridge/src/main/java/org/reddragon/bridge/StatementSerializer.java tests/unit/cobol/test_source_span.py
PYTEST_ADDOPTS="-n 2" git commit -m "fix(cobol-bridge): emit spans for IF THEN/ELSE branch statements

The IF serializer looped over its branch statements calling the
single-statement serializeStatement directly, bypassing addSpan, which is
only applied in serializeStatements. Every statement nested in an IF
branch reached Python with span=None. Route both branches through
serializeStatements like every other child-statement container."
```

---

### Task 14: Lock the invariant down

Explicit threading decays unless something enforces it. This task adds the four tests from the spec. They are written last because they fail until Tasks 7-13 are complete — they are the definition of done.

**Files:**
- Create: `tests/unit/cobol/test_source_span_coverage.py`
- Test: itself

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Write the static lint test**

Create `tests/unit/cobol/test_source_span_coverage.py`:

```python
"""Every COBOL instruction must be traceable to the source line it came from.

The silent failure mode this guards: a lowering path that emits without a
span does not error — it produces an instruction the TUI cannot highlight,
a diagnostic that cannot name a line, and a memory effect recorded against
``<unknown>``. That is invisible until someone goes looking, which is
exactly how COBOL IR ended up with 0 of 313 instructions located.
"""

import ast
from pathlib import Path

from cobol_asg.cobol_parser import make_cobol_parser
from interpreter.cobol.cobol_frontend import CobolFrontend
from tests.covers import NotLanguageFeature, covers

REPO_ROOT = Path(__file__).resolve().parents[3]
LOWERING_DIR = REPO_ROOT / "interpreter" / "cobol"

EMITTERS = {"emit_inst", "const_to_reg", "resolve_field_ref"}

# An explicit list, not a lower_*.py glob. condition_lowering.py holds 69
# emitting calls and does not match that glob, so a glob would silently
# exempt an entire threaded module -- the same class of silent hole this
# whole invariant exists to close.
#
# cobol_frontend.py is deliberately absent: its emitting calls assemble the
# program itself rather than lower any COBOL construct, and _lower_asg is
# already named in SPANLESS_FUNCTIONS.
THREADED_MODULES = (
    "lower_arithmetic.py",
    "lower_io.py",
    "lower_string_inspect.py",
    "condition_lowering.py",
    "lower_perform.py",
    "lower_search.py",
    "lower_call.py",
    "lower_procedure.py",
    "lower_data_division.py",
    "lower_program_init.py",
    "emit_context.py",
)

# Functions that emit the program prologue and singleton plumbing. These
# correspond to no COBOL line, so they pass no span and their instructions
# stay <unknown>. That is the correct answer, not a gap.
SPANLESS_FUNCTIONS = {
    "lower_program_init",
    "lower_ws_from_singleton",
    "_lower_asg",
    # Region binding plumbing: LoadVar of __ws_region / __params_region / the
    # program singleton. Describes whole regions, not any source declaration.
    "lower_sectioned_data_division",
}


def _unthreaded_calls() -> list[str]:
    offenders: list[str] = []
    for name in THREADED_MODULES:
        path = LOWERING_DIR / name
        tree = ast.parse(path.read_text())
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef):
                continue
            if func.name in SPANLESS_FUNCTIONS:
                continue
            for node in ast.walk(func):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in EMITTERS
                    and not any(k.arg == "span" for k in node.keywords)
                ):
                    offenders.append(
                        f"{path.name}:{node.lineno} in {func.name}(): "
                        f".{node.func.attr}() has no span="
                    )
    return offenders


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_lowering_emit_passes_a_span():
    offenders = _unthreaded_calls()
    assert offenders == [], (
        "Emitting calls with no span= produce IR that cannot be traced to "
        "COBOL source:\n  " + "\n  ".join(offenders)
    )


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_the_lint_can_actually_see_emitting_calls():
    """Guards against the invariant passing vacuously.

    If EMITTERS or the glob ever stops matching reality, the lint above
    passes by finding nothing at all. This asserts it is still looking at
    a real, populated set of call sites.
    """
    total = 0
    for name in THREADED_MODULES:
        path = LOWERING_DIR / name
        assert path.exists(), f"THREADED_MODULES names a missing file: {name}"
        tree = ast.parse(path.read_text())
        total += sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in EMITTERS
        )
    assert total > 200, f"expected the lowering modules to emit; saw {total}"
```

- [ ] **Step 1b: Lint span-accepting plain-function calls too**

The lint above only inspects the three `EmitContext` attribute emitters. Lowering modules also call each other's **plain functions** (`lower_expr_node`, `_lower_expr_dict`, `lower_function_operand`, `eval_ref_mod_expr`, ...). Once a function accepts `span`, any call to it that omits `span=` silently drops attribution — and nothing above sees it. Append:

```python
def _span_accepting_functions() -> set[str]:
    """Names of every function in the threaded modules that takes `span`."""
    names: set[str] = set()
    for name in THREADED_MODULES:
        tree = ast.parse((LOWERING_DIR / name).read_text())
        for func in ast.walk(tree):
            if isinstance(func, ast.FunctionDef) and any(
                a.arg == "span" for a in func.args.args + func.args.kwonlyargs
            ):
                names.add(func.name)
    return names


def _callee_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_call_to_a_span_accepting_function_passes_a_span():
    accepting = _span_accepting_functions()
    offenders: list[str] = []
    for name in THREADED_MODULES:
        path = LOWERING_DIR / name
        tree = ast.parse(path.read_text())
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef) or func.name in SPANLESS_FUNCTIONS:
                continue
            for node in ast.walk(func):
                if (
                    isinstance(node, ast.Call)
                    and _callee_name(node) in accepting
                    and not any(k.arg == "span" for k in node.keywords)
                ):
                    offenders.append(
                        f"{path.name}:{node.lineno} in {func.name}(): "
                        f"{_callee_name(node)}() accepts span but is called without it"
                    )
    assert offenders == [], "Span dropped across a call:\n  " + "\n  ".join(offenders)


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_span_accepting_function_set_is_populated():
    """Guards the lint above against passing vacuously."""
    accepting = _span_accepting_functions()
    assert {"emit_inst", "const_to_reg", "resolve_field_ref", "lower_expr_node"} <= accepting
```

This subsumes the attribute-only lint for everything that has been threaded, and catches the cross-module class it misses.

- [ ] **Step 2: Run it**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span_coverage.py -v`
Expected: PASS if Tasks 7-13 are complete. If it FAILS, it is listing genuinely unthreaded call sites — go fix them, do not add them to `SPANLESS_FUNCTIONS`. That allowlist is only for the three prologue functions named in the spec.

- [ ] **Step 3: Write the coverage invariant**

Append:

```python
# Distinct from test_source_span.py's PROBE_SOURCE: this one declares
# WS-A as well, so the MOVE lands on line 8 rather than line 7.
ARITH_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PROBE.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(4) VALUE 5.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           MOVE 7 TO WS-B.
           ADD WS-A TO WS-B.
           DISPLAY WS-B.
           STOP RUN.
"""


def _probe_ir():
    parser = make_cobol_parser()
    return CobolFrontend(parser).lower(ARITH_SOURCE)


def _procedure_body(ir):
    """Instructions between the program's entry label and its exit label.

    The prologue before it is the singleton/init plumbing, which is
    deliberately spanless (see SPANLESS_FUNCTIONS).
    """
    start = next(
        i for i, inst in enumerate(ir)
        if inst.opcode.name == "LABEL" and str(inst.label) == "func_probe_0"
    )
    end = next(
        i for i, inst in enumerate(ir)
        if inst.opcode.name == "LABEL" and str(inst.label) == "__after_probe_0"
    )
    return ir[start + 1 : end]


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_every_procedure_division_instruction_is_located():
    body = _procedure_body(_probe_ir())
    assert body, "probe produced no procedure body"
    unlocated = [
        f"{i.opcode.name} at index {n}"
        for n, i in enumerate(body)
        if i.source_location.is_unknown()
    ]
    assert unlocated == [], (
        f"{len(unlocated)} of {len(body)} procedure-division instructions "
        f"have no source location:\n  " + "\n  ".join(unlocated[:20])
    )
```

If the label names differ from `func_probe_0` / `__after_probe_0`, print them first with the Step 4 probe from Tasks 7-13 and use the real ones.

- [ ] **Step 4: Run it**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span_coverage.py -k located -v`
Expected: PASS. Before this work it would have reported `97 of 97`.

- [ ] **Step 5: Write the fidelity and nesting tests**

Append:

```python
@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_instructions_report_the_exact_declaring_position():
    """Pins the exact span, not merely 'something non-zero'.

    MOVE 7 TO WS-B is on line 8 of ARITH_SOURCE, starting at column 11.
    col_end is 21 — the START column of WS-B, the statement's last token,
    which is what ANTLR's getStop() reports. A non-zero check would let an
    off-by-one in the conversion through silently.
    """
    body = _procedure_body(_probe_ir())
    line_8 = [i for i in body if i.source_location.start_line == 8]
    assert line_8, "no instruction attributed to the MOVE on line 8"
    for inst in line_8:
        assert inst.source_location.start_col == 11
        assert inst.source_location.end_line == 8
        assert inst.source_location.end_col == 21


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_inlined_encoder_bodies_inherit_the_triggering_statement():
    """A MOVE expands into a whole inlined encode body; all of it belongs
    to the MOVE's line, which is what makes the memory-effect sidecar
    useful instead of <unknown>."""
    body = _procedure_body(_probe_ir())
    line_8 = [i for i in body if i.source_location.start_line == 8]
    assert len(line_8) > 5, (
        "expected the MOVE's inlined encoder body to be attributed to it; "
        f"only {len(line_8)} instructions carry line 8"
    )


NESTED_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. NESTED.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-A PIC 9(4) VALUE 5.
       01 WS-B PIC 9(4) VALUE 0.
       PROCEDURE DIVISION.
           IF WS-A > 0
               MOVE 7 TO WS-B
           END-IF.
           STOP RUN.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_nested_statements_report_their_own_lines():
    """The IF is on line 8 and its body MOVE on line 9. Both must appear.

    This is where a span=stmt.span pasted into the wrong frame shows up:
    if lower_if passes its own span down to the body, line 9 vanishes; if
    it passes the body's span to its branch scaffolding, line 8 vanishes.
    """
    parser = make_cobol_parser()
    ir = CobolFrontend(parser).lower(NESTED_SOURCE)
    lines = {
        i.source_location.start_line
        for i in ir
        if not i.source_location.is_unknown()
    }
    assert 8 in lines, "the IF's own scaffolding is not attributed to line 8"
    assert 9 in lines, "the body MOVE is not attributed to line 9"
```

- [ ] **Step 5b: Cover subscripted access**

Neither probe above contains a subscripted reference, so the path through `resolve_field_ref` → `lower_expr_node` (subscript lowering) is otherwise untested — and the static lint cannot see it either, because `lower_expr_node` is a plain function call rather than an `EmitContext` attribute call. Append:

```python
SUBSCRIPT_SOURCE = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SUBSCR.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-TABLE.
          05 WS-ROW PIC 9(4) OCCURS 3 TIMES.
       01 WS-I PIC 9(4) VALUE 2.
       PROCEDURE DIVISION.
           MOVE 7 TO WS-ROW(WS-I).
           STOP RUN.
"""


@covers(NotLanguageFeature.INFRASTRUCTURE)
def test_subscripted_access_instructions_are_located():
    """Subscript lowering goes through lower_expr_node, a plain function the
    static lint cannot inspect. The MOVE on line 9 must own every instruction
    it produces, including the subscript arithmetic."""
    parser = make_cobol_parser()
    ir = CobolFrontend(parser).lower(SUBSCRIPT_SOURCE)
    start = next(i for i, inst in enumerate(ir)
                 if inst.opcode.name == "LABEL" and str(inst.label) == "func_subscr_0")
    end = next(i for i, inst in enumerate(ir)
               if inst.opcode.name == "LABEL" and str(inst.label) == "__after_subscr_0")
    body = ir[start + 1 : end]
    assert any(i.opcode.name == "BINOP" for i in body), (
        "expected subscript offset arithmetic in the body; the probe is not "
        "exercising subscript lowering"
    )
    unlocated = [f"{i.opcode.name} at {n}" for n, i in enumerate(body)
                 if i.source_location.is_unknown()]
    assert unlocated == [], f"unlocated subscript instructions: {unlocated}"
```

If the label names differ, print them first and use the real ones.

- [ ] **Step 6: Run the whole new file**

Run: `uv run python -m pytest tests/unit/cobol/test_source_span_coverage.py -v`
Expected: PASS (9 tests)

- [ ] **Step 7: Run the full suite**

Run: `uv run python -m pytest -q` (or `make test`)
Expected: PASS. Use `run_in_background: true` — this takes several minutes.

- [ ] **Step 8: Commit**

```bash
uv run python -m black .
git add tests/unit/cobol/test_source_span_coverage.py
git commit -m "test(cobol): lock down source-span coverage

Static lint asserting no lowering emit omits span=, plus coverage,
fidelity and nesting tests over a probe program. Procedure-division
instructions went from 0 of 97 located to 97 of 97.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Verification checklist

After Task 14, all of these must hold:

- [ ] `uv run python -m pytest tests/unit/cobol/test_source_span.py tests/unit/cobol/test_source_span_coverage.py -v` — all green
- [ ] `uv run python -m pytest -q` — full suite green, no count regression
- [ ] `uv run lint-imports` — `cobol_asg` still imports nothing from `interpreter`
- [ ] `uv run python -m black --check .` — clean
- [ ] `grep -rn '\.span' interpreter/cobol/ | wc -l` — was 0 before this work, now in the hundreds
- [ ] The probe from Task 7 Step 4 reports every procedure-division instruction located
- [ ] `uv run python scripts/feature_coverage_audit.py` — still 0 uncovered for all 15 languages

## Out of scope

- Any TUI change. The TUI cannot open COBOL at all today (`viz/pipeline.py:85` requires a tree-sitter parser; `get_frontend(Language.COBOL)` raises `ValueError`). Locating the IR is a prerequisite for that work, not part of it.
- Attributing prologue instructions to the `PROGRAM-ID` line.
- Sub-statement precision. An operand within a statement is not separately located.
- Fixing ANTLR's `col_end` convention (see "Known fidelity limitation").
