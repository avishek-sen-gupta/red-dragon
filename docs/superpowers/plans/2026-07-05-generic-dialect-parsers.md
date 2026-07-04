# Generic Dialect Parsers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace RedDragon's CICS-specific `cics_text_parser` seam with a generic `DialectParser`
array (symmetric with the existing lowering-time `RedDragonExtensionLoweringStrategy` array), so
RedDragon's statement-construction phase — like its lowering phase already does — has zero CICS/SQL
knowledge. Relocates `ExecCicsStatement`/`CicsOperand` to Cicada and `ExecSqlStatement` to Squall.

**Architecture:** New `interpreter/cobol/dialect_parser.py` (`DialectParser` protocol +
`NullDialectParser`). `cobol_statements.py`'s `parse_statement()` falls back to a
`_dialect_parsers: ContextVar[Sequence[DialectParser]]` (set by `CobolFrontend.lower()`, same
`try/finally` shape as the contextvar it replaces) whenever a statement `"type"` isn't in its own
core `_DISPATCH_TABLE`. Cicada/Squall each own their relocated statement type + a trivial
`DialectParser` implementation. `red-dragon-forge`'s `CoprocessorSpec` gets a
`dialect_parser: DialectParser = NullDialectParser()` field (no `Optional`, matching the
`NullDbConnector` precedent).

**Tech Stack:** Python 3.11+ (RedDragon/Cicada), Python 3.13 (Squall/red-dragon-forge venvs), pytest,
ANTLR-generated ProLeap bridge (unaffected — this is a pure Python-side change).

**Repos touched, in order:** `red-dragon` (canonical, primary) → `cicada` (canonical) → `squall`
(canonical) → `red-dragon-forge` (propagates all three pins + its own adapter updates).

## Global Constraints

- Clean break, no compatibility shim: `cics_text_parser=` is removed everywhere in the same
  coordinated change, not deprecated-and-kept (per the approved design, §2.3).
- `CicsOperand` relocates to Cicada alongside `ExecCicsStatement` (per the design's invariant #1 —
  "RedDragon's `cobol_statements.py` contains no CICS- or SQL-specific type names... after this
  change" — `CicsOperand` falls under that literally, even though the design doc's prose didn't name
  it explicitly). **Note for the human:** this specific sub-decision was asked about mid-session and
  went unanswered for a long wait; proceeding with the recommended (only invariant-consistent) choice
  rather than blocking further — easy to revert task CI-1 alone if this call is wrong.
- No `Optional`/`None` for `dialect_parser` anywhere in `CoprocessorSpec` or its adapters —
  `NullDialectParser` is the uniform default (design invariant #3).
- Parsing (statement construction) and lowering (IR emission) stay two independently pluggable
  extension points — a `DialectParser` never triggers lowering, and vice versa (design invariant #2).
- Fallback dispatch only: a `stmt_type` already recognized by RedDragon's own `_DISPATCH_TABLE` is
  never offered to a dialect parser (design §2.2) — no known use case needs a dialect to override
  core COBOL statement construction.
- After each repo's own tasks, that repo's full test suite must pass before the next repo's tasks
  begin (design §6).
- RedDragon has **four** physical checkouts to keep in sync at the end: canonical `~/code/red-dragon`,
  plus vendored copies at `red-dragon-forge/vendor/red-dragon`,
  `red-dragon-forge/vendor/cicada/vendor/red-dragon`, and
  `red-dragon-forge/vendor/squall/vendor/red-dragon` (design §6).
- A separate, concurrent "no-None-default cleanup" effort in RedDragon (plan:
  `docs/superpowers/plans/2026-07-04-no-none-default-cleanup.md`) already explicitly defers
  `cics_text_parser` to this plan (design §6a) — if any of that plan's *other* tasks have landed in
  `cobol_frontend.py`/`cobol_compile.py` by the time you start, re-read those files fresh before
  writing your diff; don't trust the line numbers captured here.

---

## File Structure

```
red-dragon/
  interpreter/cobol/dialect_parser.py       # NEW — DialectParser protocol + NullDialectParser
  interpreter/cobol/cobol_statements.py     # MODIFIED — remove Exec*/_cics_text_parser, add _dialect_parsers
  interpreter/cobol/cobol_frontend.py       # MODIFIED — cics_text_parser= -> dialect_parsers=
  interpreter/frontend.py                   # MODIFIED — get_frontend() same rename
  interpreter/project/cobol_compile.py      # MODIFIED — compile_cobol/compile_cobol_module same rename
  interpreter/project/cobol_connections.py  # MODIFIED — extract_cobol_connections same rename
  interpreter/cobol/exec_cics_strategy.py   # DELETED — dead code, forced by ExecCicsStatement removal
  tests/unit/cobol/dialect_parser_fixtures.py       # NEW — RedDragon-owned fake dialect for its own seam tests
  tests/unit/test_exec_sql_seam.py                  # RENAMED -> test_dialect_parser_seam.py, rewritten
  tests/integration/test_exec_sql_seam.py            # RENAMED -> test_dialect_parser_seam.py, rewritten
  tests/unit/cobol/test_exec_cics_comment_strip.py  # DELETED — behavior + coverage relocate to Cicada
  tests/unit/test_get_frontend_defaults.py          # MODIFIED — obsolete assertion replaced
  tests/unit/project/test_cobol_connections_defaults.py  # MODIFIED — same

cicada/
  cics/statements.py       # NEW — ExecCicsStatement, CicsOperand, CicsDialectParser (relocated)
  cics/strategy.py          # MODIFIED — handles() import; drop vestigial re-export
  cics/bootstrap.py         # MODIFIED — dialect_parsers=[CicsDialectParser()]
  tests/unit/cics/test_cics_dialect_parser.py  # NEW — relocated comment-strip coverage
  tests/integration/cics/*.py (9 files)  # MODIFIED — same mechanical call-site change as bootstrap.py

squall/
  squall/statements.py      # NEW — ExecSqlStatement, SqlDialectParser (relocated)
  squall/strategy.py         # MODIFIED — handles() import
  tests/integration/squall_cobol_helpers.py  # MODIFIED — dialect_parsers=[SqlDialectParser()]
  tests/unit/test_strategy.py                # MODIFIED — import path

red-dragon-forge/
  red_dragon_forge/coprocessor.py   # MODIFIED — dialect_parser field
  red_dragon_forge/compile.py       # MODIFIED — simplified collection, no assertion
  red_dragon_forge/adapters/cics.py # MODIFIED — dialect_parser=CicsDialectParser()
  red_dragon_forge/adapters/sql.py  # MODIFIED — dialect_parser=SqlDialectParser()
```

---

### Task RD-1: `DialectParser`/`NullDialectParser` protocol

**Files:**
- Create: `interpreter/cobol/dialect_parser.py`
- Test: `tests/unit/cobol/test_dialect_parser.py`

**Interfaces:**
- Produces: `DialectParser` (Protocol: `applies(data: dict) -> bool`, `parse(data: dict) -> Any`),
  `NullDialectParser` (frozen dataclass, `applies` always `False`).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cobol/test_dialect_parser.py
import pytest

from interpreter.cobol.dialect_parser import DialectParser, NullDialectParser


def test_null_dialect_parser_never_applies():
    parser = NullDialectParser()
    assert parser.applies({"type": "ANYTHING"}) is False
    assert parser.applies({}) is False


def test_null_dialect_parser_parse_raises_if_ever_called():
    parser = NullDialectParser()
    with pytest.raises(AssertionError):
        parser.parse({"type": "ANYTHING"})


def test_null_dialect_parser_satisfies_protocol():
    assert isinstance(NullDialectParser(), DialectParser)


def test_conforming_class_satisfies_protocol():
    class _Conforming:
        def applies(self, data: dict) -> bool:
            return data.get("type") == "FAKE"

        def parse(self, data: dict):
            return data

    assert isinstance(_Conforming(), DialectParser)


def test_missing_parse_is_not_instance():
    class _MissingParse:
        def applies(self, data: dict) -> bool:
            return True

    assert not isinstance(_MissingParse(), DialectParser)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/cobol/test_dialect_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'interpreter.cobol.dialect_parser'`

- [ ] **Step 3: Write `interpreter/cobol/dialect_parser.py`**

```python
# pyright: standard
"""DialectParser — the injectable seam for CONSTRUCTING coprocessor-extension
statements (EXEC CICS, EXEC SQL, EXEC DLI) from raw ProLeap bridge JSON.

Symmetric with RedDragonExtensionLoweringStrategy (interpreter/cobol/
red_dragon_extension_strategy.py), but at statement-construction time rather
than lowering time. The two extension points are independently pluggable — a
consumer may register a DialectParser without any lowering strategy at all
(e.g. a future AST-only analysis pass), and vice versa. The frontend holds an
array of these; an empty array means every statement type must already be
recognized by RedDragon's own core dispatch table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DialectParser(Protocol):
    """One injectable parser for a coprocessor-extension statement's raw JSON."""

    def applies(self, data: dict) -> bool:
        """True if this parser owns *data* (e.g. data.get("type") == "EXEC_CICS")."""
        ...

    def parse(self, data: dict) -> Any:
        """Construct and return the typed statement object for *data*. The
        returned object must implement to_dict() (matching every other
        CobolStatementType member) but RedDragon does not otherwise constrain
        its shape."""
        ...


@dataclass(frozen=True)
class NullDialectParser:
    """Null object: never claims a statement. The default so nothing needs an
    Optional/None dialect_parser anywhere in a consumer's own data model."""

    def applies(self, data: dict) -> bool:
        return False

    def parse(self, data: dict) -> Any:
        raise AssertionError(
            "NullDialectParser.parse() should never be called — applies() always returns False"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/cobol/test_dialect_parser.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add interpreter/cobol/dialect_parser.py tests/unit/cobol/test_dialect_parser.py
git commit -m "Add DialectParser/NullDialectParser — generic statement-construction seam"
```

---

### Task RD-2: `cobol_statements.py` — remove CICS/SQL, add generic fallback dispatch

**Files:**
- Modify: `interpreter/cobol/cobol_statements.py`
- Create: `tests/unit/cobol/dialect_parser_fixtures.py`
- Create (rename from `tests/unit/test_exec_sql_seam.py`): `tests/unit/test_dialect_parser_seam.py`

**Interfaces:**
- Consumes: `DialectParser` (Task RD-1).
- Produces: `_dialect_parsers: ContextVar[Sequence[DialectParser]]` (default `()`), consumed by Task
  RD-4's `CobolFrontend.lower()`/`lower_from_ast_dict()`.

**Why a fixtures file, not squall's real `ExecSqlStatement`:** `tests/unit/test_exec_sql_seam.py`
today imports `ExecSqlStatement` directly from `interpreter.cobol.cobol_statements` — a RedDragon
type — to prove RedDragon's own generic seam (extension_strategies dispatch, frontend wiring) with
zero dependency on Squall. Once `ExecSqlStatement` relocates to Squall (Task SQ-1), RedDragon's own
test suite must not import it (RedDragon never depends on Cicada/Squall) — it needs its own minimal
fake type instead.

- [ ] **Step 1: Write the failing test — the fixtures module, then the rewritten seam test**

```python
# tests/unit/cobol/dialect_parser_fixtures.py
"""RedDragon-owned fake dialect + parser for the frontend's own seam tests.

These prove the GENERIC extension_strategies/dialect_parsers machinery works
without depending on Cicada or Squall — RedDragon must never import either.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FakeExtensionStatement:
    """A minimal opaque coprocessor-extension statement, for testing only."""

    text: str

    def to_dict(self) -> dict:
        return {"type": "FAKE_EXTENSION", "fake_text": self.text}


class FakeDialectParser:
    def applies(self, data: dict) -> bool:
        return data.get("type") == "FAKE_EXTENSION"

    def parse(self, data: dict) -> Any:
        return FakeExtensionStatement(text=data.get("fake_text", ""))
```

```python
# tests/unit/test_dialect_parser_seam.py
"""RedDragon extension seam — node, protocol, dispatch, frontend wiring.

Proves the GENERIC extension_strategies + dialect_parsers machinery using
RedDragon's own fake dialect (tests/unit/cobol/dialect_parser_fixtures.py) —
never Cicada's or Squall's real types. Renamed from test_exec_sql_seam.py
(which used to import Squall's ExecSqlStatement directly; that type has
relocated to Squall and RedDragon must not depend on it)."""

from interpreter.cobol.cobol_statements import parse_statement, _dialect_parsers
from tests.unit.cobol.dialect_parser_fixtures import (
    FakeDialectParser,
    FakeExtensionStatement,
)


class TestDialectParserFallbackDispatch:
    def test_parse_statement_dispatches_to_applying_parser(self):
        token = _dialect_parsers.set([FakeDialectParser()])
        try:
            stmt = parse_statement({"type": "FAKE_EXTENSION", "fake_text": "hello"})
        finally:
            _dialect_parsers.reset(token)
        assert isinstance(stmt, FakeExtensionStatement)
        assert stmt.text == "hello"

    def test_no_dialect_parser_applies_raises_value_error(self):
        token = _dialect_parsers.set([FakeDialectParser()])
        try:
            with pytest.raises(ValueError, match="Unknown COBOL statement type"):
                parse_statement({"type": "SOMETHING_ELSE"})
        finally:
            _dialect_parsers.reset(token)

    def test_empty_dialect_parsers_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown COBOL statement type"):
            parse_statement({"type": "FAKE_EXTENSION", "fake_text": "x"})

    def test_recognized_core_type_never_offered_to_dialect_parsers(self):
        """A core type (MOVE) is dispatched by _DISPATCH_TABLE directly, never
        second-guessed against a dialect parser that would also claim it."""

        class _AlwaysApplies:
            def applies(self, data: dict) -> bool:
                return True

            def parse(self, data: dict):
                raise AssertionError("should never be called for a recognized core type")

        token = _dialect_parsers.set([_AlwaysApplies()])
        try:
            stmt = parse_statement(
                {"type": "MOVE", "source": {"kind": "lit", "value": "1"}, "targets": []}
            )
        finally:
            _dialect_parsers.reset(token)
        assert stmt.__class__.__name__ == "MoveStatement"


import pytest  # noqa: E402 — see note below

# ── Extension-strategy lowering protocol tests (unchanged from the old file,
#    moved here verbatim since this file already covers "the seam" broadly) ──

from interpreter.cobol.red_dragon_extension_strategy import (
    RedDragonExtensionLoweringStrategy,
)


class _ConformingStrategy:
    def handles(self, stmt):
        return True

    def preprocess_program_dict(self, data):
        return data

    def on_procedure_entry(self, ctx, materialised): ...
    def lower(self, ctx, stmt, materialised): ...


class _MissingHandles:
    def preprocess_program_dict(self, data):
        return data

    def on_procedure_entry(self, ctx, materialised): ...
    def lower(self, ctx, stmt, materialised): ...


class TestExtensionStrategyProtocol:
    def test_conforming_class_is_instance(self):
        assert isinstance(_ConformingStrategy(), RedDragonExtensionLoweringStrategy)

    def test_missing_handles_is_not_instance(self):
        assert not isinstance(_MissingHandles(), RedDragonExtensionLoweringStrategy)


from interpreter.cobol.emit_context import EmitContext
from interpreter.cobol.statement_dispatch import dispatch_statement


class _SpyStrategy:
    def __init__(self, kind):
        self._kind = kind
        self.lowered = []
        self.entered = 0
        self.preprocessed = 0

    def handles(self, stmt):
        return isinstance(stmt, self._kind)

    def preprocess_program_dict(self, data):
        self.preprocessed += 1
        return data

    def on_procedure_entry(self, ctx, materialised):
        self.entered += 1

    def lower(self, ctx, stmt, materialised):
        self.lowered.append(stmt)


class TestEmitContextExtensionArray:
    def test_default_is_empty(self):
        ctx = EmitContext(dispatch_fn=dispatch_statement)
        assert tuple(ctx.extension_strategies) == ()

    def test_injected_array_is_exposed(self):
        spy = _SpyStrategy(FakeExtensionStatement)
        ctx = EmitContext(dispatch_fn=dispatch_statement, extension_strategies=[spy])
        assert list(ctx.extension_strategies) == [spy]


class TestArrayDispatch:
    def test_routes_to_strategy_that_handles(self):
        spy = _SpyStrategy(FakeExtensionStatement)
        ctx = EmitContext(dispatch_fn=dispatch_statement, extension_strategies=[spy])
        stmt = FakeExtensionStatement(text="SELECT 1 INTO :X FROM T")
        dispatch_statement(ctx, stmt, materialised=None)
        assert spy.lowered == [stmt]

    def test_first_handler_wins_and_others_skipped(self):
        class _AlwaysHandles:
            def __init__(self):
                self.lowered = []

            def handles(self, stmt):
                return True

            def preprocess_program_dict(self, data):
                return data

            def on_procedure_entry(self, ctx, materialised): ...

            def lower(self, ctx, stmt, materialised):
                self.lowered.append(stmt)

        first, second = _AlwaysHandles(), _AlwaysHandles()
        ctx = EmitContext(
            dispatch_fn=dispatch_statement, extension_strategies=[first, second]
        )
        stmt = FakeExtensionStatement(text="DELETE FROM T")
        dispatch_statement(ctx, stmt, materialised=None)
        assert first.lowered == [stmt]
        assert second.lowered == []

    def test_empty_array_no_handler_warns(self, caplog):
        import logging

        ctx = EmitContext(dispatch_fn=dispatch_statement, extension_strategies=[])
        stmt = FakeExtensionStatement(text="SELECT 1")
        with caplog.at_level(logging.WARNING):
            dispatch_statement(ctx, stmt, materialised=None)
        assert "Unhandled" in caplog.text


from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.asg_types import CobolASG
from interpreter.cobol.cobol_parser import CobolParser


class _PreprocessRecordingParser(CobolParser):
    def parse(self, source: bytes, preprocessor=None) -> CobolASG:
        if preprocessor is not None:
            preprocessor({"type": "PROGRAM", "program_id": "T"})
        return CobolASG()


class TestFrontendExtensionArray:
    def test_all_strategies_preprocess_in_order(self):
        order = []

        class _OrderSpy:
            def __init__(self, tag):
                self._tag = tag

            def handles(self, stmt):
                return False

            def preprocess_program_dict(self, data):
                order.append(self._tag)
                return data

            def on_procedure_entry(self, ctx, materialised): ...
            def lower(self, ctx, stmt, materialised): ...

        a, b = _OrderSpy("a"), _OrderSpy("b")
        frontend = CobolFrontend(
            _PreprocessRecordingParser(), extension_strategies=[a, b]
        )
        frontend.lower(b"")
        assert order == ["a", "b"]

    def test_default_array_is_empty(self):
        frontend = CobolFrontend(_PreprocessRecordingParser())
        assert tuple(frontend._extension_strategies) == ()
```

Delete the old `tests/unit/test_exec_sql_seam.py` (its content is now
`tests/unit/test_dialect_parser_seam.py`, rewritten).

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/test_dialect_parser_seam.py -v`
Expected: FAIL — `ImportError: cannot import name '_dialect_parsers' from 'interpreter.cobol.cobol_statements'`

- [ ] **Step 3: Edit `interpreter/cobol/cobol_statements.py`**

Replace the CICS-text-parser injection block (currently lines 25-31) with the generic version:

```python
# BEFORE (lines 25-31):
# ── CICS text parser injection ────────────────────────────────────
# Set by CobolFrontend.lower() for the duration of each parse call.
# Cicada injects parse_exec_cics_text from cics.cics_visitor via CobolFrontend.
CicsTextParserFn = Callable[[str], "tuple[str, dict[str, CicsOperand | None]]"]
_cics_text_parser: ContextVar[CicsTextParserFn | None] = ContextVar(
    "_cics_text_parser", default=None
)

# AFTER:
# ── Dialect parser injection ──────────────────────────────────────
# Set by CobolFrontend.lower() for the duration of each parse call. Cicada
# and Squall each inject their own DialectParser (interpreter.cobol.
# dialect_parser) via CobolFrontend — see parse_statement()'s fallback below.
from interpreter.cobol.dialect_parser import DialectParser  # noqa: E402
from typing import Sequence  # noqa: E402

_dialect_parsers: ContextVar[Sequence[DialectParser]] = ContextVar(
    "_dialect_parsers", default=()
)
```

(Move both new imports to the top of the file with the other imports in the real edit — shown split
here only to line up with the "before" block being replaced. `Callable` may become unused after this
edit; check and remove it from the `typing` import line if so — `PerformVaryingSpec`'s
`varying_from: "str | dict"` doesn't need it, but grep the whole file for other `Callable` usages
before removing.)

Delete the `CicsOperand` dataclass (currently lines 34-49) and the `ExecCicsStatement` class
(currently lines ~1306-1337) and the `ExecSqlStatement` class (currently lines ~1341-1355) —
all three relocate to Cicada (`CicsOperand`, `ExecCicsStatement`) and Squall (`ExecSqlStatement`) in
later tasks.

In the `CobolStatementType` union (currently lines ~124-125), remove the two lines:
```python
    "ExecCicsStatement",
    "ExecSqlStatement",
```

In `_DISPATCH_TABLE` (currently lines ~1504-1505), remove the two lines:
```python
    "EXEC_CICS": ExecCicsStatement,
    "EXEC_SQL": ExecSqlStatement,
```

Replace `parse_statement` (currently the last function in the file):

```python
# BEFORE:
def parse_statement(data: dict) -> CobolStatementType:
    """Dispatch on data['type'] to construct the appropriate typed statement."""
    stmt_type = data.get("type", "")
    cls = _DISPATCH_TABLE.get(stmt_type)
    if cls is None:
        raise ValueError(f"Unknown COBOL statement type: {stmt_type!r}")
    return cls.from_dict(data)

# AFTER:
def parse_statement(data: dict) -> CobolStatementType:
    """Dispatch on data['type'] to construct the appropriate typed statement.

    A type recognized by _DISPATCH_TABLE is never second-guessed against a
    dialect parser. A type NOT in _DISPATCH_TABLE falls back to the injected
    dialect parsers (interpreter.cobol.dialect_parser), in order — the first
    whose applies(data) is True gets parse(data) called.
    """
    stmt_type = data.get("type", "")
    cls = _DISPATCH_TABLE.get(stmt_type)
    if cls is not None:
        return cls.from_dict(data)
    for dialect_parser in _dialect_parsers.get():
        if dialect_parser.applies(data):
            return dialect_parser.parse(data)
    raise ValueError(f"Unknown COBOL statement type: {stmt_type!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/test_dialect_parser_seam.py tests/unit/cobol/test_dialect_parser.py -v`
Expected: all passed (this task's tests don't yet cover `CobolFrontend.lower()`'s contextvar
set/reset for `_dialect_parsers` — `TestFrontendExtensionArray` in the rewritten file still passes
because it never touches CICS/SQL types; Task RD-4 wires the contextvar into
`CobolFrontend.lower()` itself).

- [ ] **Step 5: Commit**

```bash
git add interpreter/cobol/cobol_statements.py tests/unit/cobol/dialect_parser_fixtures.py \
        tests/unit/test_dialect_parser_seam.py
git rm tests/unit/test_exec_sql_seam.py
git commit -m "cobol_statements.py: remove ExecCicsStatement/ExecSqlStatement/CicsOperand, add generic dialect-parser fallback"
```

---

### Task RD-3: Rewrite the integration seam test

**Files:**
- Modify (rename from `tests/integration/test_exec_sql_seam.py`): `tests/integration/test_dialect_parser_seam.py`

**Interfaces:**
- Consumes: `FakeDialectParser`/`FakeExtensionStatement` (Task RD-2's fixtures — reuse the same
  module, don't duplicate).

This proves the REAL ProLeap bridge JAR flows an unrecognized statement type through the generic
`dialect_parsers` fallback end-to-end. The bridge still serializes `EXEC SQL` blocks tagged
`"type": "EXEC_SQL"` (a Java-side concern, untouched by this Python-side migration) — this test just
proves that ANY unrecognized type, using `EXEC SQL`'s own real bridge output as a convenient
already-working example, reaches an injected `DialectParser` correctly. It does not construct
Squall's `ExecSqlStatement` — it uses RedDragon's own `FakeExtensionStatement`.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_dialect_parser_seam.py
"""Integration: a real EXEC SQL program flows through the JAR bridge into an
injected DialectParser (proves the full construction-time seam, generically —
RedDragon's own fake dialect, not Squall's real ExecSqlStatement)."""

from __future__ import annotations

from interpreter.cobol.cobol_frontend import CobolFrontend
from interpreter.cobol.cobol_parser import ProLeapCobolParser
from interpreter.cobol.subprocess_runner import RealSubprocessRunner
from tests.integration.cobol_helpers import bridge_jar, to_fixed
from tests.unit.cobol.dialect_parser_fixtures import FakeExtensionStatement

_PROGRAM = to_fixed(
    [
        "IDENTIFICATION DIVISION.",
        "PROGRAM-ID. SQLT.",
        "DATA DIVISION.",
        "WORKING-STORAGE SECTION.",
        "77 WS-ID PIC 9(4) VALUE 0.",
        "PROCEDURE DIVISION.",
        "    EXEC SQL",
        "        SELECT 1 INTO :WS-ID FROM SYSIBM.SYSDUMMY1",
        "    END-EXEC.",
        "    STOP RUN.",
    ]
).encode("utf-8")


class _FakeExecSqlDialectParser:
    """Claims the bridge's real "EXEC_SQL" tag but returns RedDragon's own fake
    type — proves the generic mechanism without depending on Squall."""

    def applies(self, data: dict) -> bool:
        return data.get("type") == "EXEC_SQL"

    def parse(self, data: dict):
        return FakeExtensionStatement(text=data.get("exec_sql_text", ""))


class _SqlSpy:
    def __init__(self):
        self.lowered = []

    def handles(self, stmt):
        return isinstance(stmt, FakeExtensionStatement)

    def preprocess_program_dict(self, data):
        return data

    def on_procedure_entry(self, ctx, materialised): ...

    def lower(self, ctx, stmt, materialised):
        self.lowered.append(stmt)


def _build_real_parser(bridge_jar: str) -> ProLeapCobolParser:
    return ProLeapCobolParser(RealSubprocessRunner(), bridge_jar)


def test_real_exec_sql_reaches_fake_dialect_parser(bridge_jar):
    spy = _SqlSpy()
    parser = _build_real_parser(bridge_jar)
    frontend = CobolFrontend(
        parser,
        extension_strategies=[spy],
        dialect_parsers=[_FakeExecSqlDialectParser()],
    )
    frontend.lower(_PROGRAM)
    assert (
        len(spy.lowered) == 1
    ), f"Expected 1 FakeExtensionStatement, got {len(spy.lowered)}: {spy.lowered}"
    assert isinstance(spy.lowered[0], FakeExtensionStatement)
    assert "SELECT" in spy.lowered[0].text
    assert "SYSDUMMY1" in spy.lowered[0].text


def test_real_exec_sql_with_no_dialect_parser_raises(bridge_jar):
    import pytest

    parser = _build_real_parser(bridge_jar)
    frontend = CobolFrontend(parser, extension_strategies=[])
    with pytest.raises(ValueError, match="Unknown COBOL statement type: 'EXEC_SQL'"):
        frontend.lower(_PROGRAM)
```

Delete the old `tests/integration/test_exec_sql_seam.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `PROLEAP_BRIDGE_JAR=<path> poetry run pytest tests/integration/test_dialect_parser_seam.py -v`
Expected: FAIL — `TypeError: CobolFrontend.__init__() got an unexpected keyword argument 'dialect_parsers'`
(Task RD-4 hasn't run yet.)

- [ ] **Step 3: No implementation here — this task's GREEN depends on Task RD-4**

This test is written now (fixing the file structure/coverage in one pass) but only turns green once
Task RD-4 adds `dialect_parsers=` to `CobolFrontend.__init__`. Commit this file now anyway (it's
correct, just red until RD-4); do not skip ahead and implement RD-4's code from inside this task.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_dialect_parser_seam.py
git rm tests/integration/test_exec_sql_seam.py
git commit -m "Rewrite integration seam test to prove the generic mechanism, not ExecSqlStatement (RED until RD-4)"
```

---

### Task RD-4: `CobolFrontend`/`get_frontend`/`compile_cobol`/`extract_cobol_connections` — rename the parameter

**Files:**
- Modify: `interpreter/cobol/cobol_frontend.py`
- Modify: `interpreter/frontend.py`
- Modify: `interpreter/project/cobol_compile.py`
- Modify: `interpreter/project/cobol_connections.py`
- Modify: `tests/unit/test_get_frontend_defaults.py`
- Modify: `tests/unit/project/test_cobol_connections_defaults.py`

**Interfaces:**
- Consumes: `DialectParser` (Task RD-1), `_dialect_parsers` (Task RD-2).
- Produces: `CobolFrontend.__init__(..., dialect_parsers: Sequence[DialectParser] = ())`;
  `compile_cobol(..., dialect_parsers: Sequence[Any] = ())`;
  `compile_cobol_module(..., dialect_parsers: Sequence[Any] = ())`;
  `extract_cobol_connections(..., dialect_parsers: Sequence[Any] = ())`;
  `get_frontend(..., dialect_parsers: Sequence[Any] = ())`.

**Re-read `interpreter/cobol/cobol_frontend.py`, `interpreter/frontend.py`,
`interpreter/project/cobol_compile.py` fresh before editing** — the concurrent no-None-default
cleanup plan touches these same files and may have landed by now (Global Constraints).

This task also makes Task RD-3's integration test go green.

- [ ] **Step 1: Edit `interpreter/cobol/cobol_frontend.py`**

Import line (currently line 46):
```python
# BEFORE:
from interpreter.cobol.cobol_statements import CicsTextParserFn, _cics_text_parser
# AFTER:
from interpreter.cobol.cobol_statements import _dialect_parsers
from interpreter.cobol.dialect_parser import DialectParser
```

`__init__` (currently lines 66-84):
```python
# BEFORE:
    def __init__(
        self,
        cobol_parser: CobolParser,
        observer: FrontendObserver = NullFrontendObserver(),
        extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
        cics_text_parser: (
            CicsTextParserFn | None
        ) = None,  # must be set for CICS programs
    ):
        self._parser = cobol_parser
        self._observer = observer
        self._extension_strategies = tuple(extension_strategies)
        self._cics_text_parser = cics_text_parser
        self._layout = DataLayout()
        self._ctx = EmitContext(
            dispatch_fn=dispatch_statement,
            observer=observer,
            extension_strategies=self._extension_strategies,
        )

# AFTER:
    def __init__(
        self,
        cobol_parser: CobolParser,
        observer: FrontendObserver = NullFrontendObserver(),
        extension_strategies: Sequence[RedDragonExtensionLoweringStrategy] = (),
        dialect_parsers: Sequence[DialectParser] = (),
    ):
        self._parser = cobol_parser
        self._observer = observer
        self._extension_strategies = tuple(extension_strategies)
        self._dialect_parsers = tuple(dialect_parsers)
        self._layout = DataLayout()
        self._ctx = EmitContext(
            dispatch_fn=dispatch_statement,
            observer=observer,
            extension_strategies=self._extension_strategies,
        )
```

`lower()` and `lower_from_ast_dict()` (currently lines 175-209):
```python
# BEFORE (lower(), lines 188/192):
        token = _cics_text_parser.set(self._cics_text_parser)
        try:
            asg = self._parser.parse(source, preprocessor=_chained_preprocess)
        finally:
            _cics_text_parser.reset(token)
# AFTER:
        token = _dialect_parsers.set(self._dialect_parsers)
        try:
            asg = self._parser.parse(source, preprocessor=_chained_preprocess)
        finally:
            _dialect_parsers.reset(token)
```

```python
# BEFORE (lower_from_ast_dict(), lines 202/208):
        token = _cics_text_parser.set(self._cics_text_parser)
        try:
            for strat in self._extension_strategies:
                data = strat.preprocess_program_dict(data)
            asg = CobolASG.from_dict(data)
        finally:
            _cics_text_parser.reset(token)
# AFTER:
        token = _dialect_parsers.set(self._dialect_parsers)
        try:
            for strat in self._extension_strategies:
                data = strat.preprocess_program_dict(data)
            asg = CobolASG.from_dict(data)
        finally:
            _dialect_parsers.reset(token)
```

- [ ] **Step 2: Edit `interpreter/project/cobol_compile.py`**

Module docstring (line 9): `cics_text_parser) abstractly` → `dialect_parsers) abstractly`.

`compile_cobol_module` signature + forwarding (currently lines 72-92):
```python
# BEFORE:
def compile_cobol_module(
    source: bytes,
    *,
    parser: Any,
    copybook_dirs: list[Path] = [],
    extension_strategies: Sequence[Any] = (),
    cics_text_parser: Any = None,
    observer: FrontendObserver = NullFrontendObserver(),
    path: Path = Path("__main__.cbl"),
    ast_path: Path,
) -> tuple[Any, ModuleUnit]:
    """Lower one COBOL source into a (frontend, ModuleUnit). The shared core."""
    frontend: Any = get_frontend(
        Language.COBOL,
        frontend_type=constants.FRONTEND_COBOL,
        observer=observer,
        copybook_dirs=copybook_dirs,
        cobol_parser=parser,
        extension_strategies=extension_strategies,
        cics_text_parser=cics_text_parser,
    )
# AFTER:
def compile_cobol_module(
    source: bytes,
    *,
    parser: Any,
    copybook_dirs: list[Path] = [],
    extension_strategies: Sequence[Any] = (),
    dialect_parsers: Sequence[Any] = (),
    observer: FrontendObserver = NullFrontendObserver(),
    path: Path = Path("__main__.cbl"),
    ast_path: Path,
) -> tuple[Any, ModuleUnit]:
    """Lower one COBOL source into a (frontend, ModuleUnit). The shared core."""
    frontend: Any = get_frontend(
        Language.COBOL,
        frontend_type=constants.FRONTEND_COBOL,
        observer=observer,
        copybook_dirs=copybook_dirs,
        cobol_parser=parser,
        extension_strategies=extension_strategies,
        dialect_parsers=dialect_parsers,
    )
```

`compile_cobol` signature (currently lines 109-121): same rename,
`cics_text_parser: Any = None` → `dialect_parsers: Sequence[Any] = ()`.

All FOUR forwarding call sites inside `compile_cobol` that currently read
`cics_text_parser=cics_text_parser,` (currently lines 176, 191, 214, inside the three
`compile_cobol_module(...)` calls) become `dialect_parsers=dialect_parsers,`.

- [ ] **Step 3: Edit `interpreter/frontend.py`**

Signature (currently line 83): `cics_text_parser: Any = None,` → `dialect_parsers: Sequence[Any] = (),`.

Docstring (currently the `cics_text_parser: Optional CICS text parser fn. COBOL only.` line):
`dialect_parsers: Sequence of DialectParser instances (Cicada/Squall inject their own). COBOL only.`

Forwarding call site (currently lines 129-134):
```python
# BEFORE:
        return CobolFrontend(
            resolved_parser,
            observer=observer,
            extension_strategies=list(extension_strategies),
            cics_text_parser=cics_text_parser,
        )
# AFTER:
        return CobolFrontend(
            resolved_parser,
            observer=observer,
            extension_strategies=list(extension_strategies),
            dialect_parsers=list(dialect_parsers),
        )
```

- [ ] **Step 4: Edit `interpreter/project/cobol_connections.py`**

Signature (currently line 63): `cics_text_parser: Any = None,` → `dialect_parsers: Sequence[Any] = (),`.
Forwarding call site (currently line 83): `cics_text_parser=cics_text_parser,` → `dialect_parsers=dialect_parsers,`.

- [ ] **Step 5: Update the two obsolete test assertions**

```python
# tests/unit/test_get_frontend_defaults.py — BEFORE:
    assert sig.parameters["copybook_dirs"].default == []
    # Deferred to red-dragon-79iv — untouched in this plan
    assert sig.parameters["cics_text_parser"].default is None
    assert sig.parameters["cobol_parser"].default is None
    assert sig.parameters["llm_client"].default is None

# AFTER:
    assert sig.parameters["copybook_dirs"].default == []
    assert sig.parameters["dialect_parsers"].default == ()
    # Deferred to red-dragon-79iv — untouched in this plan
    assert sig.parameters["cobol_parser"].default is None
    assert sig.parameters["llm_client"].default is None
```

```python
# tests/unit/project/test_cobol_connections_defaults.py — BEFORE:
    assert sig.parameters["extra_subprogram_sources"].default == {}
    # cics_text_parser stays untouched — deferred alongside DialectParser migration
    assert sig.parameters["cics_text_parser"].default is None

# AFTER:
    assert sig.parameters["extra_subprogram_sources"].default == {}
    assert sig.parameters["dialect_parsers"].default == ()
```

- [ ] **Step 6: Run the seam tests to verify Task RD-3 is now green too**

Run: `poetry run pytest tests/unit/test_dialect_parser_seam.py tests/integration/test_dialect_parser_seam.py tests/unit/test_get_frontend_defaults.py tests/unit/project/test_cobol_connections_defaults.py -v`
Expected: all passed.

- [ ] **Step 7: Commit**

```bash
git add interpreter/cobol/cobol_frontend.py interpreter/frontend.py \
        interpreter/project/cobol_compile.py interpreter/project/cobol_connections.py \
        tests/unit/test_get_frontend_defaults.py tests/unit/project/test_cobol_connections_defaults.py
git commit -m "Rename cics_text_parser= to dialect_parsers= across CobolFrontend/get_frontend/compile_cobol/extract_cobol_connections"
```

---

### Task RD-5: Delete dead CICS-strategy compatibility shim

**Files:**
- Delete: `interpreter/cobol/exec_cics_strategy.py`
- Delete: `tests/unit/cobol/test_exec_cics_comment_strip.py`

**Interfaces:** none (pure removal).

`exec_cics_strategy.py`'s own docstring already says: "RedDragon's own frontend no longer uses this
module... will be removed once cicada migrates to RedDragonExtensionLoweringStrategy." Cicada's
`CicsLoweringStrategy` already implements `RedDragonExtensionLoweringStrategy` directly — the only
remaining consumer is Cicada's own `cics/strategy.py` re-exporting `CatchAllLoweringStrategy`/
`ExecCicsStrategy` for no verified reason (confirmed via `grep` — nothing else in Cicada imports
them). Its `TYPE_CHECKING`-only `from interpreter.cobol.cobol_statements import ExecCicsStatement`
would dangle after Task RD-2 removed that name anyway, forcing the issue now. Task CI-2 removes
Cicada's re-export in the same coordinated change.

`test_exec_cics_comment_strip.py` tests `*>` inline-comment stripping that lived inside
`ExecCicsStatement.from_dict()` — that logic relocates into Cicada's `CicsDialectParser.parse()`
(Task CI-1), where equivalent coverage is added.

- [ ] **Step 1: Delete both files**

```bash
git rm interpreter/cobol/exec_cics_strategy.py tests/unit/cobol/test_exec_cics_comment_strip.py
```

- [ ] **Step 2: Confirm nothing else in RedDragon imports the deleted module**

```bash
grep -rn "exec_cics_strategy" interpreter/ tests/ | grep -v ".pyc"
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git commit -m "Delete dead exec_cics_strategy.py compat shim and its comment-strip test (relocates to Cicada)"
```

---

### Task RD-6: Full RedDragon test suite

**Files:** none (verification only).

- [ ] **Step 1: Run the full suite**

```bash
poetry run pytest tests/ -x -q
```

Expected: all pass. If anything fails, it's almost certainly a missed `cics_text_parser=` call site
outside the ones this plan named — search again (`grep -rn "cics_text_parser" interpreter/ tests/`)
before assuming the plan's list was exhaustive; fix and re-run rather than special-casing the
failure.

- [ ] **Step 2: Confirm the removed names are truly gone**

```bash
grep -rn "ExecCicsStatement\|ExecSqlStatement\|CicsOperand\|cics_text_parser\|CicsTextParserFn" interpreter/ | grep -v ".pyc"
```

Expected: no output.

- [ ] **Step 3: No commit needed** (verification only — if fixes were required, commit those per
  the step above's own guidance, then re-run this task's Step 1 clean).

---

### Task CI-1: Cicada — relocate `ExecCicsStatement`/`CicsOperand`, add `CicsDialectParser`

**Files:**
- Create: `cics/statements.py`
- Create: `tests/unit/cics/test_cics_dialect_parser.py`

**Interfaces:**
- Consumes: `parse_exec_cics_text` (existing, `cics/cics_visitor.py:446`), `ExprNode` (RedDragon,
  `interpreter.cobol.cobol_expression`).
- Produces: `ExecCicsStatement` (verb: str, options: dict[str, CicsOperand | None]), `CicsOperand`
  (unchanged shape), `CicsDialectParser` (applies/parse).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/cics/test_cics_dialect_parser.py
"""Unit tests for CicsDialectParser — relocated from RedDragon's
test_exec_cics_comment_strip.py (red-dragon-kn0n); now exercises the real
dialect-parser mechanism instead of the removed _cics_text_parser contextvar."""

from __future__ import annotations

from cics.statements import CicsDialectParser, CicsOperand, ExecCicsStatement


class TestCicsDialectParserApplies:
    def test_applies_to_exec_cics_type(self):
        assert CicsDialectParser().applies({"type": "EXEC_CICS"}) is True

    def test_does_not_apply_to_other_types(self):
        assert CicsDialectParser().applies({"type": "EXEC_SQL"}) is False
        assert CicsDialectParser().applies({}) is False


class TestCicsDialectParserCommentStrip:
    def test_inline_comment_stripped_before_parser(self):
        """*> inline comment is stripped from exec_cics_text before parsing."""
        stmt = CicsDialectParser().parse(
            {"exec_cics_text": "RETURN TRANSID (WS-TRANID) *> some comment", "type": "EXEC_CICS"}
        )
        assert stmt.verb == "RETURN"

    def test_multiline_comment_stripped(self):
        """*> comment on its own line is stripped; remaining lines are joined."""
        stmt = CicsDialectParser().parse(
            {
                "exec_cics_text": (
                    "RETURN TRANSID (WS-TRANID)\n*> LENGTH(LENGTH OF X)\nCOMMARE (Y)"
                ),
                "type": "EXEC_CICS",
            }
        )
        assert stmt.verb == "RETURN"

    def test_cotrn02c_pattern_no_valueerror(self):
        """Reproduces the exact COTRN02C exec_cics_text that raised ValueError (kn0n)."""
        # No exception = pass
        CicsDialectParser().parse(
            {
                "exec_cics_text": (
                    "RETURN TRANSID (WS-TRANID) COMMAREA (CARDDEMO-COMMAREA)"
                    " *>  LENGTH(LENGTH OF CARDDEMO-COMMAREA)"
                ),
                "type": "EXEC_CICS",
            }
        )


class TestExecCicsStatementRelocatedShape:
    def test_from_dict_via_dialect_parser_returns_exec_cics_statement(self):
        stmt = CicsDialectParser().parse(
            {"exec_cics_text": "SEND MAP ('TRNADD')", "type": "EXEC_CICS"}
        )
        assert isinstance(stmt, ExecCicsStatement)
        assert stmt.verb == "SEND"

    def test_cics_operand_shape_unchanged(self):
        operand = CicsOperand(text="X", is_literal=True)
        assert operand.text == "X"
        assert operand.is_literal is True
        assert operand.subscripts == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/cics/test_cics_dialect_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'cics.statements'`

- [ ] **Step 3: Write `cics/statements.py`**

```python
"""CICS-owned COBOL statement types, relocated from RedDragon (red-dragon
commit b54471dc's DialectParser migration) — RedDragon itself now has zero
CICS-specific type names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from interpreter.cobol.cobol_expression import ExprNode
from cics.cics_visitor import parse_exec_cics_text


@dataclass(frozen=True)
class CicsOperand:
    """A parsed EXEC CICS option value.

    is_literal=True  -> a quoted string literal (text is the inner content, no quotes).
    is_literal=False -> a bare operand: data-name, subscripted/reference-modified ref,
                        or numeric literal (text preserved verbatim).

    ``subscripts`` carries each index as a structured ExprNode: a bare data-name
    becomes a FieldRefNode, an unsigned integer becomes a LiteralNode.
    Arithmetic CICS subscripts raise ValueError at parse time.
    """

    text: str
    is_literal: bool
    subscripts: tuple[ExprNode, ...] = ()
    ref_mod_start: ExprNode | None = None
    ref_mod_length: ExprNode | None = None


@dataclass(frozen=True)
class ExecCicsStatement:
    """EXEC CICS verb-with-options block."""

    verb: str
    options: dict[str, "CicsOperand | None"]

    def to_dict(self) -> dict:
        # Serialised for informational round-trip only (see RedDragon's
        # to_dict() convention) — parity, not exercised by the AST cache path.
        serialised: dict[str, Any] = {}
        for key, operand in self.options.items():
            if operand is None:
                serialised[key] = None
            else:
                serialised[key] = {
                    "text": operand.text,
                    "is_literal": operand.is_literal,
                }
        return {"type": "EXEC_CICS", "verb": self.verb, "options": serialised}


class CicsDialectParser:
    """Constructs ExecCicsStatement from raw EXEC CICS bridge JSON."""

    def applies(self, data: dict) -> bool:
        return data.get("type") == "EXEC_CICS"

    def parse(self, data: dict) -> ExecCicsStatement:
        text = re.sub(
            r"\*>.*", "", data.get("exec_cics_text", ""), flags=re.MULTILINE
        ).strip()
        verb, options = parse_exec_cics_text(text)
        return ExecCicsStatement(verb=verb, options=options)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/cics/test_cics_dialect_parser.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add cics/statements.py tests/unit/cics/test_cics_dialect_parser.py
git commit -m "Add cics/statements.py — relocated ExecCicsStatement/CicsOperand + CicsDialectParser"
```

---

### Task CI-2: Cicada — update `CicsLoweringStrategy.handles()`, drop vestigial re-export

**Files:**
- Modify: `cics/strategy.py`

**Interfaces:**
- Consumes: `ExecCicsStatement` (Task CI-1, `cics/statements.py`).

- [ ] **Step 1: Edit `cics/strategy.py`**

Import (currently line 41):
```python
# BEFORE:
from interpreter.cobol.cobol_statements import ExecCicsStatement
# AFTER:
from cics.statements import ExecCicsStatement
```

`handles()` (currently lines 561-562) is unchanged (`isinstance(stmt, ExecCicsStatement)` — only the
import source changed).

TYPE_CHECKING-only import (currently line 49, inside an `if TYPE_CHECKING:` block importing
`CicsOperand` for a type hint) — same import-source rename:
```python
# BEFORE:
    from interpreter.cobol.cobol_statements import CicsOperand
# AFTER:
    from cics.statements import CicsOperand
```

Drop the vestigial re-export (currently near the top of the file, module docstring + import lines
~1-15 per this plan's earlier research):
```python
# BEFORE:
"""ExecCicsStrategy protocol and null-object implementation.

The protocol and no-op now live in interpreter.cobol.exec_cics_strategy;
re-exported here for backward compatibility.
"""
...
from interpreter.cobol.exec_cics_strategy import (  # noqa: F401
    CatchAllLoweringStrategy,
    ExecCicsStrategy,
)
```
Remove both the docstring paragraph referencing `exec_cics_strategy` and the import block entirely
— confirmed via `grep` (Task RD-5's research) that nothing in Cicada imports
`CatchAllLoweringStrategy`/`ExecCicsStrategy` from `cics.strategy` either.

- [ ] **Step 2: Run cicada's strategy unit tests**

```bash
uv run --no-sync python -m pytest tests/unit/cics/ -x -q
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add cics/strategy.py
git commit -m "cics/strategy.py: import ExecCicsStatement/CicsOperand from cics.statements; drop dead exec_cics_strategy re-export"
```

---

### Task CI-3: Cicada — update all 11 `cics_text_parser=` call sites

**Files:**
- Modify: `cics/bootstrap.py`
- Modify: `tests/integration/cics/test_resp_writeback.py`
- Modify: `tests/integration/cics/test_assign_formattime.py`
- Modify: `tests/integration/cics/test_commarea_roundtrip.py` (2 call sites)
- Modify: `tests/integration/cics/test_parse_strategy.py` (2 call sites)
- Modify: `tests/integration/cics/test_vsam_browse.py`
- Modify: `tests/integration/cics/test_vsam_roundtrip.py` (2 call sites)

**Interfaces:**
- Consumes: `CicsDialectParser` (Task CI-1).

Every one of these 11 call sites has the exact same shape — find `cics_text_parser=parse_exec_cics_text,`
and replace with `dialect_parsers=[CicsDialectParser()],`, then fix that file's import (remove
`from cics.cics_visitor import parse_exec_cics_text` if this was its only use in the file — check
each file, since some may use `parse_exec_cics_text` for another purpose too; add
`from cics.statements import CicsDialectParser`).

- [ ] **Step 1: `cics/bootstrap.py`**

```python
# BEFORE (inside compile_cics_program, currently lines 62-63, 82):
    from interpreter.project.cobol_compile import compile_cobol
    from cics.cics_visitor import parse_exec_cics_text
    from cics.preprocessor import apply_cics_prepass
    ...
    _frontend, linked = compile_cobol(
        source,  # already CICS-prepassed by the caller
        parser=parser,
        extension_strategies=[strategy],
        cics_text_parser=parse_exec_cics_text,
        program_source_dir=_program_source_dir,
        extra_subprogram_sources=_extra_subprogram_sources,
        source_transform=apply_cics_prepass,
    )
# AFTER:
    from interpreter.project.cobol_compile import compile_cobol
    from cics.statements import CicsDialectParser
    from cics.preprocessor import apply_cics_prepass
    ...
    _frontend, linked = compile_cobol(
        source,  # already CICS-prepassed by the caller
        parser=parser,
        extension_strategies=[strategy],
        dialect_parsers=[CicsDialectParser()],
        program_source_dir=_program_source_dir,
        extra_subprogram_sources=_extra_subprogram_sources,
        source_transform=apply_cics_prepass,
    )
```

- [ ] **Step 2: Apply the identical transformation to each remaining file**

For each of `tests/integration/cics/test_resp_writeback.py`,
`tests/integration/cics/test_assign_formattime.py`,
`tests/integration/cics/test_commarea_roundtrip.py` (both call sites),
`tests/integration/cics/test_parse_strategy.py` (both call sites),
`tests/integration/cics/test_vsam_browse.py`,
`tests/integration/cics/test_vsam_roundtrip.py` (both call sites):

1. Replace `cics_text_parser=parse_exec_cics_text,` with `dialect_parsers=[CicsDialectParser()],`
   at every occurrence in the file.
2. If the file's only use of `from cics.cics_visitor import parse_exec_cics_text` was for this
   kwarg (check — some of these files import it at module level near the top, per this plan's own
   research showing `test_parse_strategy.py:15` does exactly this), replace that import line with
   `from cics.statements import CicsDialectParser`.
3. If `CobolFrontend(...)` is constructed directly (not via `compile_cics_program`/`compile_cobol`)
   in that file — `test_parse_strategy.py` does this (`CobolFrontend(cobol_parser=..., cics_text_parser=parse_exec_cics_text)`)
   — the same kwarg rename applies there too.

- [ ] **Step 3: Verify no call site was missed**

```bash
grep -rn "cics_text_parser" cics/ tests/ | grep -v "vendor/red-dragon"
```

Expected: no output.

- [ ] **Step 4: Run cicada's integration test suite**

```bash
make jar  # if not already built
uv run --no-sync python -m pytest tests/integration/ -x -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add cics/bootstrap.py tests/integration/cics/test_resp_writeback.py \
        tests/integration/cics/test_assign_formattime.py tests/integration/cics/test_commarea_roundtrip.py \
        tests/integration/cics/test_parse_strategy.py tests/integration/cics/test_vsam_browse.py \
        tests/integration/cics/test_vsam_roundtrip.py
git commit -m "Update all cics_text_parser= call sites to dialect_parsers=[CicsDialectParser()]"
```

---

### Task CI-4: Cicada — bump RedDragon pin, full test suite

**Files:**
- Modify: `vendor/red-dragon` (submodule gitlink)

**Interfaces:** none.

- [ ] **Step 1: Bump the pin**

```bash
cd vendor/red-dragon
git fetch origin main
git checkout <RedDragon's HEAD commit after Task RD-6>
cd ../..
git add vendor/red-dragon
```

- [ ] **Step 2: Run the full suite**

```bash
make jar
uv run --no-sync python -m pytest tests/ -x -q
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git commit -m "Bump vendor/red-dragon to pick up the generic DialectParser seam"
```

---

### Task SQ-1: Squall — relocate `ExecSqlStatement`, add `SqlDialectParser`

**Files:**
- Create: `squall/statements.py`
- Test: `tests/unit/test_statements.py`

**Interfaces:**
- Produces: `ExecSqlStatement` (text: str, unchanged shape), `SqlDialectParser`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_statements.py
from squall.statements import ExecSqlStatement, SqlDialectParser


class TestSqlDialectParser:
    def test_applies_to_exec_sql_type(self):
        assert SqlDialectParser().applies({"type": "EXEC_SQL"}) is True

    def test_does_not_apply_to_other_types(self):
        assert SqlDialectParser().applies({"type": "EXEC_CICS"}) is False

    def test_parse_carries_text_verbatim(self):
        data = {
            "type": "EXEC_SQL",
            "exec_sql_text": "EXEC SQL SELECT ACCT_BAL INTO :WS-BAL FROM ACCOUNT END-EXEC",
        }
        stmt = SqlDialectParser().parse(data)
        assert isinstance(stmt, ExecSqlStatement)
        assert stmt.text == data["exec_sql_text"]

    def test_parse_empty_text(self):
        stmt = SqlDialectParser().parse({"type": "EXEC_SQL"})
        assert stmt.text == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --no-sync python -m pytest tests/unit/test_statements.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'squall.statements'`

- [ ] **Step 3: Write `squall/statements.py`**

```python
"""SQL-owned COBOL statement types, relocated from RedDragon (red-dragon
commit b54471dc's DialectParser migration) — RedDragon itself now has zero
SQL-specific type names.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecSqlStatement:
    """EXEC SQL block. Carries the raw EXEC SQL text verbatim — including the
    EXEC SQL/END-EXEC envelope — exactly as the ProLeap bridge emits it. Squall's
    own strategy treats the body as opaque text: envelope removal and SQL
    parsing are done by squall.parser's grammar-based parser, never by string
    surgery here."""

    text: str

    def to_dict(self) -> dict:
        return {"type": "EXEC_SQL", "text": self.text}


class SqlDialectParser:
    """Constructs ExecSqlStatement from raw EXEC SQL bridge JSON."""

    def applies(self, data: dict) -> bool:
        return data.get("type") == "EXEC_SQL"

    def parse(self, data: dict) -> ExecSqlStatement:
        return ExecSqlStatement(text=data.get("exec_sql_text", "") or "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --no-sync python -m pytest tests/unit/test_statements.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add squall/statements.py tests/unit/test_statements.py
git commit -m "Add squall/statements.py — relocated ExecSqlStatement + SqlDialectParser"
```

---

### Task SQ-2: Squall — update `handles()`, test helper, and direct test imports

**Files:**
- Modify: `squall/strategy.py`
- Modify: `tests/integration/squall_cobol_helpers.py`
- Modify: `tests/unit/test_strategy.py`

**Interfaces:**
- Consumes: `ExecSqlStatement`, `SqlDialectParser` (Task SQ-1).

- [ ] **Step 1: Edit `squall/strategy.py`**

`handles()` (currently lines 107-110):
```python
# BEFORE:
    def handles(self, stmt: Any) -> bool:
        from interpreter.cobol.cobol_statements import ExecSqlStatement

        return isinstance(stmt, ExecSqlStatement)
# AFTER:
    def handles(self, stmt: Any) -> bool:
        from squall.statements import ExecSqlStatement

        return isinstance(stmt, ExecSqlStatement)
```

- [ ] **Step 2: Edit `tests/integration/squall_cobol_helpers.py`**

Its own `compile_cobol` wrapper (currently `return _rd_compile_cobol(..., extension_strategies=[strategy])`,
around line 101-104) previously relied on RedDragon's `_DISPATCH_TABLE` hardcoding `"EXEC_SQL"` —
that entry is gone (Task RD-2), so this helper MUST now inject a `SqlDialectParser` or every squall
integration test that compiles a program containing `EXEC SQL` breaks:

```python
# BEFORE:
    return _rd_compile_cobol(
        prepass.source.encode("utf-8"),
        parser=parser,
        extension_strategies=[strategy],
    )
# AFTER:
    from squall.statements import SqlDialectParser

    return _rd_compile_cobol(
        prepass.source.encode("utf-8"),
        parser=parser,
        extension_strategies=[strategy],
        dialect_parsers=[SqlDialectParser()],
    )
```

- [ ] **Step 3: Edit `tests/unit/test_strategy.py`**

```python
# BEFORE (line 27):
from interpreter.cobol.cobol_statements import ExecSqlStatement
# AFTER:
from squall.statements import ExecSqlStatement
```

- [ ] **Step 4: Run squall's unit suite**

```bash
uv run --no-sync python -m pytest tests/unit/ -x -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add squall/strategy.py tests/integration/squall_cobol_helpers.py tests/unit/test_strategy.py
git commit -m "Import ExecSqlStatement from squall.statements; inject SqlDialectParser in the shared test helper"
```

---

### Task SQ-3: Squall — bump RedDragon pin, full test suite

**Files:**
- Modify: `vendor/red-dragon` (submodule gitlink)

**Interfaces:** none.

- [ ] **Step 1: Bump the pin (same commit as Task CI-4)**

```bash
cd vendor/red-dragon
git fetch origin main
git checkout <RedDragon's HEAD commit after Task RD-6 — same SHA as cicada's Task CI-4>
cd ../..
git add vendor/red-dragon
```

- [ ] **Step 2: Run the full suite**

Requires the squall-db2 Docker container up (see red-dragon-forge's Task 9 from the earlier CICS+SQL
composition plan for the known recovery steps if the DRDA listener isn't bound):

```bash
export SQUALL_DB2_DSN="DATABASE=MOJO;HOSTNAME=localhost;PORT=15000;PROTOCOL=TCPIP;UID=db2inst1;PWD=squalltest123"
export SQUALL_DB2_DSN2="DATABASE=MOJO2;HOSTNAME=localhost;PORT=15000;PROTOCOL=TCPIP;UID=db2inst1;PWD=squalltest123"
uv run --no-sync python -m pytest tests/ -x -q
```

Expected: all pass (255+ passed, 1 skipped, matching the baseline established earlier).

- [ ] **Step 3: Commit**

```bash
git commit -m "Bump vendor/red-dragon to pick up the generic DialectParser seam"
```

---

### Task RDF-1: red-dragon-forge — `CoprocessorSpec.dialect_parser`, simplify `compile_program`

**Files:**
- Modify: `red_dragon_forge/coprocessor.py`
- Modify: `red_dragon_forge/compile.py`
- Modify: `tests/integration/test_coprocessor.py`
- Modify: `tests/integration/test_compile_program.py`

**Interfaces:**
- Consumes: `DialectParser`/`NullDialectParser` (RedDragon, `interpreter.cobol.dialect_parser`).
- Produces: `CoprocessorSpec.dialect_parser: DialectParser = NullDialectParser()`.

- [ ] **Step 1: Update the failing tests first (TDD — these currently pass against the old field;
  update them to the new field, confirm RED for the right reason)**

```python
# tests/integration/test_coprocessor.py — add/replace the cics_text_parser-related assertions:
def test_defaults_are_non_execution_owning_with_null_dialect_parser():
    spec = CoprocessorSpec(name="noop", make_strategy=lambda: object())
    assert spec.owns_execution is False
    assert isinstance(spec.dialect_parser, NullDialectParser)
    assert spec.dialect_parser.applies({"type": "ANYTHING"}) is False
```
(Add `from interpreter.cobol.dialect_parser import NullDialectParser` to the imports; remove the old
`test_defaults_are_non_execution_owning_with_no_cics_text_parser` test — it named a field that no
longer exists.)

```python
# tests/integration/test_compile_program.py — the "at most one cics_text_parser" test is deleted
# (the new mechanism has no such constraint — every spec always contributes a real DialectParser
# array entry now, harmlessly no-op for NullDialectParser). Remove
# test_at_most_one_cics_text_parser_allowed and its _FakeStrategy-with-cics_text_parser setup
# entirely; the remaining test (test_every_specs_prepass_runs_before_any_make_strategy) is
# unaffected by this change and stays as-is.
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --no-sync python -m pytest tests/integration/test_coprocessor.py tests/integration/test_compile_program.py -v`
Expected: FAIL — `AttributeError`/`TypeError` referencing the still-old `cics_text_parser` field/param.

- [ ] **Step 3: Edit `red_dragon_forge/coprocessor.py`**

```python
# BEFORE:
from interpreter.cobol.red_dragon_extension_strategy import (
    RedDragonExtensionLoweringStrategy,
)


def _identity(source: str) -> str:
    return source


@dataclass(frozen=True)
class CoprocessorSpec:
    ...
    name: str
    make_strategy: Callable[[], RedDragonExtensionLoweringStrategy]
    source_prepass: Callable[[str], str] = _identity
    owns_execution: bool = False
    cics_text_parser: Any | None = None

# AFTER:
from interpreter.cobol.dialect_parser import DialectParser, NullDialectParser
from interpreter.cobol.red_dragon_extension_strategy import (
    RedDragonExtensionLoweringStrategy,
)


def _identity(source: str) -> str:
    return source


@dataclass(frozen=True)
class CoprocessorSpec:
    ...
    name: str
    make_strategy: Callable[[], RedDragonExtensionLoweringStrategy]
    source_prepass: Callable[[str], str] = _identity
    owns_execution: bool = False
    dialect_parser: DialectParser = NullDialectParser()
```

Update the docstring's `cics_text_parser` paragraph:
```python
# BEFORE:
    ``cics_text_parser`` threads RedDragon's ``compile_cobol(cics_text_parser=...)``
    argument through without this module knowing what a "CICS text parser" is;
    only the CICS adapter ever sets it.
# AFTER:
    ``dialect_parser`` threads RedDragon's ``compile_cobol(dialect_parsers=[...])``
    array through without this module knowing what any dialect parser does —
    every adapter sets one (a real one, or the NullDialectParser default);
    compile_program collects them all unconditionally.
```

- [ ] **Step 4: Edit `red_dragon_forge/compile.py`**

```python
# BEFORE:
    strategies = [spec.make_strategy() for spec in specs]

    cics_text_parsers = [s.cics_text_parser for s in specs if s.cics_text_parser is not None]
    assert len(cics_text_parsers) <= 1, (
        f"at most one CoprocessorSpec may supply a cics_text_parser, got "
        f"{len(cics_text_parsers)}"
    )

    return compile_cobol(
        text.encode("utf-8"),
        parser=parser,
        extension_strategies=strategies,
        cics_text_parser=cics_text_parsers[0] if cics_text_parsers else None,
        program_source_dir=program_source_dir if program_source_dir is not None else Path("."),
        extra_subprogram_sources=extra_subprogram_sources
        if extra_subprogram_sources is not None
        else {},
    )

# AFTER:
    strategies = [spec.make_strategy() for spec in specs]
    dialect_parsers = [spec.dialect_parser for spec in specs]

    return compile_cobol(
        text.encode("utf-8"),
        parser=parser,
        extension_strategies=strategies,
        dialect_parsers=dialect_parsers,
        program_source_dir=program_source_dir if program_source_dir is not None else Path("."),
        extra_subprogram_sources=extra_subprogram_sources
        if extra_subprogram_sources is not None
        else {},
    )
```

Update the docstring paragraph naming the old "at most one" constraint (currently lines 33-34) —
delete it; the constraint no longer exists.

- [ ] **Step 5: Run to verify it passes**

Run: `uv run --no-sync python -m pytest tests/integration/test_coprocessor.py tests/integration/test_compile_program.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add red_dragon_forge/coprocessor.py red_dragon_forge/compile.py \
        tests/integration/test_coprocessor.py tests/integration/test_compile_program.py
git commit -m "CoprocessorSpec: replace cics_text_parser with dialect_parser: DialectParser = NullDialectParser()"
```

---

### Task RDF-2: red-dragon-forge — update both adapters

**Files:**
- Modify: `red_dragon_forge/adapters/cics.py`
- Modify: `red_dragon_forge/adapters/sql.py`

**Interfaces:**
- Consumes: `CicsDialectParser` (Cicada, `cics.statements`), `SqlDialectParser` (Squall,
  `squall.statements`).

- [ ] **Step 1: Edit `red_dragon_forge/adapters/cics.py`**

```python
# BEFORE:
from cics.preprocessor import apply_cics_prepass
from cics.strategy import CicsLoweringStrategy
from cics.cics_visitor import parse_exec_cics_text

from red_dragon_forge.coprocessor import CoprocessorSpec
...
    return CoprocessorSpec(
        name="cics",
        make_strategy=_make_strategy,
        source_prepass=apply_cics_prepass,
        owns_execution=True,
        cics_text_parser=parse_exec_cics_text,
    )

# AFTER:
from cics.preprocessor import apply_cics_prepass
from cics.statements import CicsDialectParser
from cics.strategy import CicsLoweringStrategy

from red_dragon_forge.coprocessor import CoprocessorSpec
...
    return CoprocessorSpec(
        name="cics",
        make_strategy=_make_strategy,
        source_prepass=apply_cics_prepass,
        owns_execution=True,
        dialect_parser=CicsDialectParser(),
    )
```

- [ ] **Step 2: Edit `red_dragon_forge/adapters/sql.py`**

```python
# BEFORE:
from squall.backend import SqlBackend
from squall.connector import DbConnector, NullDbConnector
from squall.parser.sql_model import FieldMeta
from squall.preprocess import apply_sql_prepass
from squall.strategy import SqlLoweringStrategy

from red_dragon_forge.coprocessor import CoprocessorSpec
...
    return CoprocessorSpec(
        name="sql",
        make_strategy=_make_strategy,
        source_prepass=_prepass,
        owns_execution=False,
    )

# AFTER:
from squall.backend import SqlBackend
from squall.connector import DbConnector, NullDbConnector
from squall.parser.sql_model import FieldMeta
from squall.preprocess import apply_sql_prepass
from squall.statements import SqlDialectParser
from squall.strategy import SqlLoweringStrategy

from red_dragon_forge.coprocessor import CoprocessorSpec
...
    return CoprocessorSpec(
        name="sql",
        make_strategy=_make_strategy,
        source_prepass=_prepass,
        owns_execution=False,
        dialect_parser=SqlDialectParser(),
    )
```

- [ ] **Step 3: Run the adapter tests**

```bash
export PROLEAP_BRIDGE_JAR=$PWD/vendor/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
uv run --no-sync python -m pytest tests/integration/test_cics_adapter.py tests/integration/test_sql_adapter.py -v
```

Expected: both pass. (Full-suite verification, including the real INQCUST test, happens in Task RDF-3
once all three vendored `vendor/red-dragon` copies and `vendor/cicada`/`vendor/squall` are bumped
together — running it now would fail on the still-unbumped pins.)

- [ ] **Step 4: Commit**

```bash
git add red_dragon_forge/adapters/cics.py red_dragon_forge/adapters/sql.py
git commit -m "Adapters: populate dialect_parser=CicsDialectParser()/SqlDialectParser()"
```

---

### Task RDF-3: red-dragon-forge — bump all pins, full suite

**Files:**
- Modify: `vendor/red-dragon` (own submodule gitlink)
- Modify: `vendor/cicada` (submodule gitlink)
- Modify: `vendor/squall` (submodule gitlink)

**Interfaces:** none.

This repo has **three** separate `vendor/red-dragon` checkouts to align (its own, plus the ones
nested inside `vendor/cicada` and `vendor/squall`) — Global Constraints.

- [ ] **Step 1: Bump this repo's own `vendor/red-dragon`**

```bash
cd vendor/red-dragon
git fetch origin main
git checkout <RedDragon's HEAD commit after Task RD-6>
cd ../..
```

- [ ] **Step 2: Bump `vendor/cicada` and `vendor/squall` to their post-Task-CI-4/SQ-3 commits**

```bash
cd vendor/cicada
git fetch origin main
git checkout <cicada's HEAD commit after Task CI-4>
cd ..
cd squall
git fetch origin main
git checkout <squall's HEAD commit after Task SQ-3>
cd ../..
git add vendor/red-dragon vendor/cicada vendor/squall
```

- [ ] **Step 3: Re-run `scripts/check_red_dragon_pin.py` to confirm all three RedDragon checkouts agree**

```bash
uv run --no-sync python scripts/check_red_dragon_pin.py
```

Expected: `OK: all three RedDragon pins match.`, exit code 0.

- [ ] **Step 4: `uv sync` + reinstall the `--no-deps` editables (their dependency metadata may have
  changed) and run the full suite**

```bash
uv sync
uv pip install -e vendor/cicada --no-deps
uv pip install -e vendor/squall --no-deps
export PROLEAP_BRIDGE_JAR=$PWD/vendor/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
export SQUALL_DB2_DSN="DATABASE=MOJO;HOSTNAME=localhost;PORT=15000;PROTOCOL=TCPIP;UID=db2inst1;PWD=squalltest123"
uv run --no-sync python -m pytest tests/ -v
```

Expected: 11 passed, including `test_inqcust_e2e.py::test_inqcust_found_and_not_found` (the real
Bank-of-Z INQCUST proof) — if the Db2 container's DRDA listener isn't bound, recover via
`docker start squall-db2` then `db2stop force`/`db2start` inside the container (documented fragility
from the earlier CICS+SQL composition plan's Task 9), not by editing test code.

- [ ] **Step 5: Commit**

```bash
git commit -m "Bump vendor/red-dragon, vendor/cicada, vendor/squall — generic DialectParser seam, all pins aligned"
```

---

## Self-Review Notes

- **Spec coverage:** §2 (RedDragon mechanism) → Tasks RD-1/RD-2/RD-4. §3 (Cicada) → CI-1/CI-2/CI-3.
  §4 (Squall) → SQ-1/SQ-2. §5 (red-dragon-forge) → RDF-1/RDF-2. §6 (sequencing) → the phase ordering
  and RDF-3's three-way pin bump. §6a (no-None-default coordination) → the two obsolete-assertion
  updates in Task RD-4 Step 5, and the Global Constraints note to re-read files fresh. Invariant #1
  (zero CICS/SQL type names in RedDragon) → RD-2/RD-5 remove every one, including `CicsOperand`
  (the one item the design doc's prose didn't name explicitly — flagged in Global Constraints).
  Invariant #2 (parsing/lowering independence) → `DialectParser` never touches `EmitContext`/IR;
  proven by RD-1's/RD-2's tests never constructing an `EmitContext`. Invariant #3 (no
  `Optional`/`None`) → `NullDialectParser` default throughout, no task introduces a bare `None`.
- **Placeholder scan:** every code step shows complete, real code (no "similar to Task N"). The two
  places that name "the exact list of file:line locations" instead of repeating identical 3-line
  diffs eleven times (Task CI-3) are followed by an executable verification grep — this is a uniform
  mechanical transform at named locations, not a vague instruction.
- **Type consistency:** `CoprocessorSpec.dialect_parser`, `build_cics_spec`/`build_sql_spec`'s
  `dialect_parser=` kwarg, `compile_program`'s `dialect_parsers` list, and RedDragon's
  `compile_cobol(dialect_parsers=...)` all agree in name and shape (`Sequence[DialectParser]` /
  `DialectParser`) across every task that touches them.
