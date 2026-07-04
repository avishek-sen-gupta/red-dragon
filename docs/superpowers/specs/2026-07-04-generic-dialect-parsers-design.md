# Generic Dialect Parsers — Design

**Date:** 2026-07-04
**Status:** design approved; implementation not yet started.
**Repos affected:** `red-dragon` (this repo, primary), `cicada`, `squall`, `red-dragon-forge`.

---

## 1. Motivation

RedDragon's COBOL frontend already has one clean, coprocessor-agnostic extension point for
**lowering**: `extension_strategies: Sequence[RedDragonExtensionLoweringStrategy]` on
`CobolFrontend`/`compile_cobol`, each strategy offering `handles(stmt)`/`lower(ctx, stmt, ...)`.
Neither RedDragon nor its lowering machinery knows CICS or SQL exist.

**Statement *construction*** (turning the raw ProLeap bridge JSON into typed dataclasses, before
any lowering happens) does not have the same symmetry. `cobol_statements.py`'s `_DISPATCH_TABLE`
hardcodes `"EXEC_CICS": ExecCicsStatement` and `"EXEC_SQL": ExecSqlStatement`, and
`ExecCicsStatement.from_dict()` requires a CICS-specific callback (`cics_text_parser`, threaded via
a `_cics_text_parser` `ContextVar`) to eagerly parse the raw text into `(verb, options)` at
construction time. `ExecSqlStatement.from_dict()`, by contrast, stays fully opaque (verbatim
`text: str`) and defers all parsing to Squall's own lowering step — it needs no injected callback
at all. This asymmetry means RedDragon's construction phase is *not* coprocessor-agnostic the way
its lowering phase is: it hardcodes both coprocessors' type names and (for CICS) their parsing
contract.

**Why not just defer CICS's parsing to lowering time too** (matching Squall, and removing the
asymmetry without adding any new mechanism)? Rejected: parsing and lowering must stay independently
pluggable. A future consumer (e.g. a static-analysis pass over the full parsed AST) should be able
to reuse the exact same construction-time parsing without triggering IR lowering at all. Coupling
"produce a structured statement" to "the statement gets lowered" forecloses that. This is the
deciding factor over the simpler alternative.

This design generalizes construction-time parsing into the same kind of array-of-pluggable-things
seam lowering already has — a `DialectParser` array, symmetric with
`RedDragonExtensionLoweringStrategy` — and removes `ExecCicsStatement`/`ExecSqlStatement` from
RedDragon's own dispatch table entirely, relocating them (and their parsing logic) to Cicada and
Squall respectively.

---

## 2. RedDragon-side mechanism

### 2.1 `DialectParser` protocol

New file `interpreter/cobol/dialect_parser.py`, sibling to the existing
`red_dragon_extension_strategy.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DialectParser(Protocol):
    """One injectable parser for a coprocessor-extension statement's raw JSON
    (CICS, SQL, …). Mirrors RedDragonExtensionLoweringStrategy's handles()/lower()
    shape, but at statement-CONSTRUCTION time rather than lowering time — the two
    are independently pluggable so a future consumer (e.g. AST-only analysis) can
    reuse parsing without triggering lowering."""

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

### 2.2 `cobol_statements.py` changes

- Remove `ExecCicsStatement`, `ExecSqlStatement`, `CicsTextParserFn`, and the `_cics_text_parser`
  `ContextVar` entirely.
- Remove the `"EXEC_CICS"`/`"EXEC_SQL"` entries from `_DISPATCH_TABLE` — it retains only genuine
  core-COBOL statement types.
- Add a generic `_dialect_parsers: ContextVar[Sequence[DialectParser]] = ContextVar("_dialect_parsers", default=())`.
- `parse_statement(data)`: when `data.get("type")` is **not** found in `_DISPATCH_TABLE` (the
  fallback path only — a recognized core type is never second-guessed against dialect parsers, since
  no known or anticipated use case needs a dialect to override core COBOL statement parsing), try
  each dialect parser in `_dialect_parsers.get()` in order; the first whose `.applies(data)` is
  `True` gets `.parse(data)` called, and that return value is the result. If none applies, raise the
  same `ValueError(f"Unknown COBOL statement type: {stmt_type!r}")` as today.

**Why a `ContextVar` and not an explicit parameter threaded through `parse_statement`:**
`parse_statement` is already called recursively through many *other* statement types' own
`from_dict()` (e.g. `IfStatement.from_dict` recursively parses its nested statement lists,
`PerformStatement.from_dict` similarly) — none of those intermediate call sites know or care about
dialect parsers. Threading `dialect_parsers` as an explicit parameter would mean touching every
composite statement type's signature purely to pass a value through. A `ContextVar`, set once by
`CobolFrontend.lower()`/`lower_from_ast_dict()` before parsing starts and reset in a `finally`, makes
it ambient across that whole recursive graph without that invasiveness — exactly the same reason the
`ContextVar` this replaces (`_cics_text_parser`) already existed. It also happens to be the correct
primitive if statement construction (today sequential — `compile_cobol`'s own docstring: "Phase 2
loads each JSON and lowers sequentially, at most one ASG live at a time") is ever parallelized:
`ContextVar` is thread-local by construction, unlike a plain module-level global, and Phase 1 of this
same pipeline (`parallel_parse_to_cache`, `cobol_compile.py:62`) already uses a real
`ThreadPoolExecutor` elsewhere in this codebase, so concurrent construction is not a foreign
scenario here.

### 2.3 `CobolFrontend`/`compile_cobol` changes

- `cics_text_parser: Any = None` parameter removed everywhere (`CobolFrontend.__init__`,
  `compile_cobol`, `compile_cobol_module`) — replaced by `dialect_parsers: Sequence[DialectParser] = ()`.
- `CobolFrontend.lower()`/`lower_from_ast_dict()`: replace
  `token = _cics_text_parser.set(self._cics_text_parser)` with
  `token = _dialect_parsers.set(self._dialect_parsers)` (same `try/finally` shape, just the renamed
  contextvar and the stored array instead of a single callback).

**Clean break, no compatibility shim:** `cics_text_parser=` is removed, not deprecated-and-kept.
Every caller across Cicada, Squall, and red-dragon-forge updates in the same coordinated change —
all three already pin the same RedDragon commit (per the drift-fixing work done earlier this
session), so there is nothing to leave working "the old way" in the interim.

---

## 3. Cicada-side changes

- New file `cics/statements.py` owns `ExecCicsStatement` (unchanged shape: `verb: str`,
  `options: dict[str, CicsOperand | None]`, and its existing `to_dict()`), relocated verbatim from
  RedDragon.
- New `CicsDialectParser` in the same file (or a new small `cics/dialect_parser.py` if
  `statements.py` starts feeling crowded — decide at implementation time based on actual size):
  ```python
  @dataclass(frozen=True)
  class CicsDialectParser:
      def applies(self, data: dict) -> bool:
          return data.get("type") == "EXEC_CICS"

      def parse(self, data: dict) -> ExecCicsStatement:
          text = re.sub(r"\*>.*", "", data.get("exec_cics_text", ""), flags=re.MULTILINE).strip()
          verb, options = parse_exec_cics_text(text)
          return ExecCicsStatement(verb=verb, options=options)
  ```
  (body is `ExecCicsStatement.from_dict`'s existing logic, moved as-is — no behavior change, only
  relocation.)
- `CicsLoweringStrategy.handles()` updates its `isinstance(stmt, ExecCicsStatement)` import from
  `interpreter.cobol.cobol_statements` to `cics.statements`.
- `cics/bootstrap.py`'s `compile_cics_program` (and any other direct `compile_cobol` caller) changes
  `cics_text_parser=parse_exec_cics_text` to `dialect_parsers=[CicsDialectParser()]`.

## 4. Squall-side changes

- New file `squall/statements.py` owns `ExecSqlStatement` (unchanged trivial shape: `text: str`),
  relocated verbatim.
- New `SqlDialectParser`:
  ```python
  @dataclass(frozen=True)
  class SqlDialectParser:
      def applies(self, data: dict) -> bool:
          return data.get("type") == "EXEC_SQL"

      def parse(self, data: dict) -> ExecSqlStatement:
          return ExecSqlStatement(text=data.get("exec_sql_text", "") or "")
  ```
- `SqlLoweringStrategy.handles()` updates its `isinstance` import the same way.
- Squall's own `compile_cobol` call sites (its test helpers, any bootstrap-equivalent) add
  `dialect_parsers=[SqlDialectParser()]`.

## 5. red-dragon-forge-side changes

- `CoprocessorSpec.cics_text_parser: Any | None = None` becomes
  `dialect_parser: DialectParser = NullDialectParser()` (imported from RedDragon's
  `interpreter.cobol.dialect_parser`, not redefined locally — same pattern as importing
  `RedDragonExtensionLoweringStrategy` today). No `Optional`, no `None` anywhere.
- `compile_program()` simplifies:
  ```python
  dialect_parsers = [spec.dialect_parser for spec in specs]
  ```
  No filtering, no "at most one" assertion — every spec always has *some* `DialectParser` (real or
  null), and a `NullDialectParser`'s `applies()` is always `False`, so including it is harmless. This
  also **deletes** the `cics_text_parser` "at most one" assertion the final whole-branch review
  flagged as a Minor wart in the prior design — the new mechanism has no analogous constraint to
  enforce, since multiple dialect parsers coexisting is now the normal case, not an edge case to
  guard against.
- `adapters/cics.py`: `CoprocessorSpec(..., dialect_parser=CicsDialectParser())` instead of
  `cics_text_parser=parse_exec_cics_text`.
- `adapters/sql.py`: gains `dialect_parser=SqlDialectParser()` — previously this adapter had no
  equivalent field at all, since only CICS needed one; now both are symmetric, matching Squall's own
  trivial-but-present `SqlDialectParser`.

---

## 6. Sequencing across repos

RedDragon changes land first (a breaking API change to `compile_cobol`/`CobolFrontend`), verified
against RedDragon's own test suite in isolation. Then, in lockstep — since Cicada, Squall, and
red-dragon-forge are all currently pinned to the same RedDragon commit (per the pin-alignment work
done earlier this session) — each of the three:
1. Bumps its `vendor/red-dragon` pin to the new commit.
2. Updates its own call sites (`cics_text_parser=` → `dialect_parsers=[...]`) and relocated types.
3. Re-runs its own test suite to confirm compatibility before the next repo proceeds.

This mirrors exactly the pin-bump-and-verify sequencing already used earlier in this session for the
`DbConnector` redesign (implement in canonical repo → mirror into vendored copies → bump gitlinks →
re-verify). The one added wrinkle here: RedDragon has **four** physical checkouts to keep in sync
(canonical `~/code/red-dragon`, plus vendored copies inside `red-dragon-forge/vendor/red-dragon`,
`red-dragon-forge/vendor/cicada/vendor/red-dragon`, and `red-dragon-forge/vendor/squall/vendor/red-dragon`)
— more than the two (canonical + one vendored copy) each of Cicada's/Squall's own fixes needed. The
implementation plan must account for propagating the same commit content into all four, not just
one vendored copy, and re-running each of the three downstream repos' own test suites against the
updated pin before considering the change complete.

---

## 7. Testing

- RedDragon: unit tests for `DialectParser`/`NullDialectParser` (a fake dialect parser claiming a
  synthetic unrecognized `"type"`, proving the fallback dispatch and the "none applies → ValueError"
  path); `_DISPATCH_TABLE` no longer contains `"EXEC_CICS"`/`"EXEC_SQL"` (a regression test asserting
  those keys are absent, so no one silently reintroduces coprocessor-specific knowledge there).
- Cicada: `CicsDialectParser` unit tests (mirroring whatever tested `ExecCicsStatement.from_dict`
  today, just relocated); `cics/bootstrap.py` integration tests continue passing unchanged (pure
  relocation, no behavior change).
- Squall: `SqlDialectParser` unit tests (equally trivial, mirroring `ExecSqlStatement.from_dict`'s
  existing coverage).
- red-dragon-forge: existing test suite (all 11 tests, including the real `INQCUST` end-to-end
  proof) must continue passing unchanged — this is a pure internal-mechanism swap from the
  perspective of every test that compiles a CICS/SQL program; no test's assertions should need to
  change, only the `CoprocessorSpec`/adapter construction code they exercise indirectly through
  `compile_program`/`build_cics_spec`/`build_sql_spec`.

---

## 8. Invariants

1. RedDragon's `cobol_statements.py` contains no CICS- or SQL-specific type names, dispatch-table
   entries, or contextvars after this change — `DialectParser`/`NullDialectParser` are the only
   generic seam.
2. Parsing (statement construction) and lowering (IR emission) remain two independently pluggable
   extension points — a future consumer may register a `DialectParser` without any
   `RedDragonExtensionLoweringStrategy` at all, and vice versa.
3. No `Optional`/`None` for `dialect_parser` anywhere in `CoprocessorSpec` or its adapters —
   `NullDialectParser` is the uniform default, matching the `NullDbConnector` precedent already
   established in Squall's own `EXEC SQL CONNECT` redesign.
4. Clean break: `cics_text_parser=` is removed, not deprecated. All four affected repos move
   together, coordinated by their existing shared RedDragon pin.
