# Coprocessor-Compile Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the three independent re-implementations (red-dragon-forge, Cicada, Squall) of "compose N extension specs into one `compile_cobol` call" by hoisting the already-generic `CoprocessorSpec`/`compile_program` from red-dragon-forge into RedDragon itself.

**Architecture:** New module `interpreter/project/coprocessor_compile.py` in RedDragon hosts `CoprocessorSpec` + `compile_program`, moved essentially verbatim from `red_dragon_forge/coprocessor.py` + `compile.py` (which already import neither `cics.*` nor `squall.*`). Cicada's `compile_cics_program` and Squall's test `compile_cobol()` helper each build exactly one `CoprocessorSpec` inline and delegate to the shared function, keeping their own public signatures unchanged. red-dragon-forge deletes its own copies and imports from RedDragon directly.

**Tech Stack:** Python 3.13, pytest, ProLeap bridge (JAR-gated integration tests), uv/poetry across 4 repos (red-dragon, cicada, squall, red-dragon-forge) linked via git submodules.

## Global Constraints

- No behavior change to `CoprocessorSpec`'s fields or `compile_program`'s composition order (prepass-then-strategy, in spec order) — this is a pure move, not a redesign.
- Cicada's `compile_cics_program`/`run_carddemo_region` public signatures (`source, parser, strategy, *, program_source_dirs`) do not change.
- Squall's `squall_cobol_helpers.compile_cobol()` public signature does not change.
- red-dragon-forge's `red_dragon_forge/coprocessor.py` and `compile.py` are deleted outright — no re-export shim.
- Every task's full test suite (`poetry run pytest tests/ -q` for RedDragon; `make test` for cicada; the documented `uv run --no-sync python -m pytest tests/` invocations for squall/forge) must pass before that task's commit, per each repo's own pre-commit hook.
- Follow each repo's established cross-repo pin-bump discipline: after a producer repo (RedDragon, then cicada/squall) lands a commit, push it, then bump the consumer's `vendor/red-dragon` (or `vendor/cicada`/`vendor/squall`) pin — including red-dragon-forge's *nested* copies under `vendor/cicada/vendor/red-dragon` and `vendor/squall/vendor/red-dragon` — before running that consumer's suite.
- Db2 container flakiness is a known, benign, recurring issue: `docker exec squall-db2 su - db2inst1 -c 'db2start'` (occasionally preceded by `db2stop force`) is the documented, non-destructive recovery; never treat it as a real regression.

---

### Task 1: RedDragon — add `interpreter/project/coprocessor_compile.py`

**Files:**
- Create: `interpreter/project/coprocessor_compile.py`
- Create: `tests/unit/project/test_coprocessor_compile.py`

**Interfaces:**
- Produces: `CoprocessorSpec` (frozen dataclass: `name: str`, `make_strategy: Callable[[], RedDragonExtensionLoweringStrategy]`, `source_prepass: Callable[[str], str] = _identity`, `owns_execution: bool = False`, `dialect_parser: DialectParser = NullDialectParser()`, `extra_program_source_dirs: Callable[[], Sequence[Path]] = _no_extra_program_source_dirs`) and `compile_program(source: bytes, parser: Any, specs: Sequence[CoprocessorSpec], *, program_source_dirs: Sequence[Path] = ()) -> tuple[Any, LinkedProgram]`, both importable from `interpreter.project.coprocessor_compile`.
- Consumes: `interpreter.frontend_extension.{DialectParser, NullDialectParser, RedDragonExtensionLoweringStrategy}`, `interpreter.project.cobol_compile.compile_cobol`, `interpreter.project.types.LinkedProgram`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/project/test_coprocessor_compile.py`:

```python
from __future__ import annotations

import dataclasses

import pytest

from interpreter.frontend import make_cobol_parser
from interpreter.frontend_extension import NullDialectParser
from interpreter.project.coprocessor_compile import CoprocessorSpec, compile_program


def test_default_source_prepass_is_identity():
    spec = CoprocessorSpec(name="noop", make_strategy=lambda: object())
    assert spec.source_prepass("       IDENTIFICATION DIVISION.") == (
        "       IDENTIFICATION DIVISION."
    )


def test_defaults_are_non_execution_owning_with_null_dialect_parser():
    spec = CoprocessorSpec(name="noop", make_strategy=lambda: object())
    assert spec.owns_execution is False
    assert isinstance(spec.dialect_parser, NullDialectParser)
    assert spec.dialect_parser.applies({"type": "ANYTHING"}) is False
    assert spec.extra_program_source_dirs() == ()


def test_spec_is_frozen():
    spec = CoprocessorSpec(name="noop", make_strategy=lambda: object())
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.name = "renamed"


_TRIVIAL_PROGRAM = b"""\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TRIVIAL.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-FIELD PIC X(10).
       PROCEDURE DIVISION.
           MOVE 'HELLO' TO WS-FIELD.
           STOP RUN.
"""


class _FakeStrategy:
    """A minimal RedDragonExtensionLoweringStrategy that handles nothing —
    proves compile_program's plumbing without needing real CICS/SQL lowering."""

    def handles(self, stmt) -> bool:
        return False

    def preprocess_program_dict(self, data: dict) -> dict:
        return data

    def on_procedure_entry(self, ctx, materialised) -> None:
        pass

    def lower(self, ctx, stmt, materialised) -> None:
        pass


def test_every_specs_prepass_runs_before_any_make_strategy():
    call_order = []

    def prepass_a(source: str) -> str:
        call_order.append("prepass_a")
        return source

    def prepass_b(source: str) -> str:
        call_order.append("prepass_b")
        return source

    def make_strategy_a():
        call_order.append("make_strategy_a")
        return _FakeStrategy()

    def make_strategy_b():
        call_order.append("make_strategy_b")
        return _FakeStrategy()

    specs = [
        CoprocessorSpec(name="a", make_strategy=make_strategy_a, source_prepass=prepass_a),
        CoprocessorSpec(name="b", make_strategy=make_strategy_b, source_prepass=prepass_b),
    ]
    parser = make_cobol_parser()

    compile_program(_TRIVIAL_PROGRAM, parser, specs)

    assert call_order == [
        "prepass_a",
        "prepass_b",
        "make_strategy_a",
        "make_strategy_b",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run pytest tests/unit/project/test_coprocessor_compile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'interpreter.project.coprocessor_compile'`

- [ ] **Step 3: Create `interpreter/project/coprocessor_compile.py`**

```python
"""CoprocessorSpec / compile_program — the generic seam for composing N
RedDragon extension-lowering strategies + dialect parsers into one
compile_cobol() call.

Coprocessor-agnostic: this module never imports anything CICS/SQL-specific
(it only knows RedDragonExtensionLoweringStrategy/DialectParser as Protocols
from interpreter.frontend_extension). Consumers (Cicada, Squall,
red-dragon-forge) each build their own CoprocessorSpec(s) inline and hand
them here — this module has no knowledge of what any of them are for.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from interpreter.frontend_extension import (
    DialectParser,
    NullDialectParser,
    RedDragonExtensionLoweringStrategy,
)
from interpreter.project.cobol_compile import compile_cobol
from interpreter.project.types import LinkedProgram


def _identity(source: str) -> str:
    return source


def _no_extra_program_source_dirs() -> Sequence[Path]:
    return ()


@dataclass(frozen=True)
class CoprocessorSpec:
    """One coprocessor's contribution to a composed COBOL program.

    ``make_strategy`` is a zero-arg closure built by a per-coprocessor adapter,
    already bound to whatever runtime state that coprocessor needs.
    ``source_prepass`` runs at the source-text layer, before ProLeap parses
    the program.

    A coprocessor whose strategy construction depends on state its own
    prepass computes (e.g. a dclgen field-metadata sidecar) closes over a
    private mutable one-element list shared between ``source_prepass`` and
    ``make_strategy`` — compile_program guarantees every spec's
    ``source_prepass`` runs before ANY spec's ``make_strategy`` is called, so
    that holder is always populated in time.

    ``owns_execution`` marks the (at most one) coprocessor that imposes
    execution semantics on the compiled program (e.g. a dispatcher loop) —
    consumers decide what to do with this; compile_program itself doesn't
    inspect it.

    ``dialect_parser`` threads compile_cobol's ``dialect_parsers=[...]`` array
    through without this module knowing what any dialect parser does — every
    caller sets one (a real one, or the NullDialectParser default);
    compile_program collects them all unconditionally.

    ``extra_program_source_dirs`` threads compile_cobol's
    ``program_source_dirs=[...]`` search path through the same way — a
    coprocessor whose CALLed subprograms are never on disk under the
    caller's own directory (e.g. IBM Language Environment stubs) sets this to
    contribute that directory, without this module knowing what's in it or
    what any of it is for. compile_program appends every spec's
    contribution, in order, after the caller's own program_source_dirs.
    """

    name: str
    make_strategy: Callable[[], RedDragonExtensionLoweringStrategy]
    source_prepass: Callable[[str], str] = _identity
    owns_execution: bool = False
    dialect_parser: DialectParser = NullDialectParser()
    extra_program_source_dirs: Callable[[], Sequence[Path]] = (
        _no_extra_program_source_dirs
    )


def compile_program(
    source: bytes,
    parser: Any,
    specs: Sequence[CoprocessorSpec],
    *,
    program_source_dirs: Sequence[Path] = (),
) -> tuple[Any, LinkedProgram]:
    """Compile ``source`` with every spec's prepass and strategy composed.

    Every spec's ``source_prepass`` runs, in order, before ANY spec's
    ``make_strategy`` is called — a spec whose strategy construction depends
    on state its own prepass populates relies on this ordering (see
    CoprocessorSpec's docstring).
    """
    text = functools.reduce(
        lambda t, spec: spec.source_prepass(t), specs, source.decode("utf-8")
    )

    strategies = [spec.make_strategy() for spec in specs]
    dialect_parsers = [spec.dialect_parser for spec in specs]
    all_program_source_dirs: tuple[Path, ...] = functools.reduce(
        lambda dirs, spec: (*dirs, *spec.extra_program_source_dirs()),
        specs,
        tuple(program_source_dirs),
    )

    return compile_cobol(
        text.encode("utf-8"),
        parser=parser,
        extension_strategies=strategies,
        dialect_parsers=dialect_parsers,
        program_source_dirs=all_program_source_dirs,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run pytest tests/unit/project/test_coprocessor_compile.py -v`
Expected: 4 passed

- [ ] **Step 5: Run the full RedDragon suite**

Run: `PROLEAP_BRIDGE_JAR=$PWD/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar poetry run pytest tests/ -q`
Expected: all pass (14696+4 passed, same skip/xfail counts as before)

- [ ] **Step 6: Commit and push**

```bash
git add interpreter/project/coprocessor_compile.py tests/unit/project/test_coprocessor_compile.py
git commit -m "feat(project): add CoprocessorSpec/compile_program, the generic N-spec compose seam"
git push origin main
```

Record the resulting commit SHA — it is needed for Tasks 2, 3, and 4's pin bumps.

---

### Task 2: Cicada — rewire `cics/bootstrap.py` onto the shared mechanism

**Files:**
- Modify: `cics/bootstrap.py`
- Modify: `vendor/red-dragon` (pin bump to Task 1's commit)

**Interfaces:**
- Consumes: `interpreter.project.coprocessor_compile.{CoprocessorSpec, compile_program}` (Task 1).
- Produces: `compile_cics_program(source: bytes, parser: Any, strategy: Any, *, program_source_dirs: Sequence[Path] = ()) -> Any` — signature unchanged from before this task; `run_carddemo_region(...)` — signature unchanged.

- [ ] **Step 1: Bump `vendor/red-dragon` to Task 1's commit**

```bash
cd vendor/red-dragon
git fetch origin
git checkout <task-1-commit-sha>
cd ../..
git add vendor/red-dragon
```

- [ ] **Step 2: Rewrite `compile_cics_program` in `cics/bootstrap.py`**

Replace the current body of `compile_cics_program` (which calls
`interpreter.project.cobol_compile.compile_cobol` directly) with:

```python
def compile_cics_program(
    source: bytes,
    parser: Any,
    strategy: Any,
    *,
    program_source_dirs: Sequence[Path] = (),
) -> Any:
    """Pre-passed CICS COBOL ``source`` -> ``LinkedProgram`` with ``strategy`` injected.

    ``source`` must already have been run through ``apply_cics_prepass`` (and
    encoded to bytes). Returns a :class:`LinkedProgram` ready for ``run_cics``.

    Builds one CoprocessorSpec around ``strategy`` and delegates to RedDragon's
    shared compile_program (interpreter.project.coprocessor_compile) — the
    same composition mechanism red-dragon-forge and Squall use. IBM Language
    Environment callable services (e.g. CEEDAYS, which have no CardDemo
    application source) resolve because LE_STUBS_DIR is always appended to
    the search path via the spec's extra_program_source_dirs, so callers
    never need to know these stubs exist.
    """
    from interpreter.project.coprocessor_compile import CoprocessorSpec, compile_program
    from cics.statements import CicsDialectParser
    from cics.preprocessor import apply_cics_prepass

    spec = CoprocessorSpec(
        name="cics",
        make_strategy=lambda: strategy,
        source_prepass=apply_cics_prepass,
        dialect_parser=CicsDialectParser(),
        extra_program_source_dirs=lambda: (LE_STUBS_DIR,),
    )
    _frontend, linked = compile_program(
        source,  # already CICS-prepassed by the caller
        parser,
        [spec],
        program_source_dirs=program_source_dirs,
    )
    return linked
```

Leave `run_carddemo_region` untouched — it already only forwards
`program_source_dirs` to `compile_cics_program` and doesn't otherwise touch
`compile_cobol`.

- [ ] **Step 3: Run the full cicada suite**

Run: `make test`
Expected: 348 passed (same as before this task — public behavior is unchanged)

- [ ] **Step 4: Commit and push**

```bash
git add cics/bootstrap.py vendor/red-dragon
git commit -m "refactor(bootstrap): delegate compile_cics_program to RedDragon's shared compile_program"
git push origin main
```

Record the resulting commit SHA — needed for Task 4's pin bump.

---

### Task 3: Squall — rewire `squall_cobol_helpers.py` onto the shared mechanism

**Files:**
- Modify: `tests/integration/squall_cobol_helpers.py`
- Modify: `vendor/red-dragon` (pin bump to Task 1's commit)

**Interfaces:**
- Consumes: `interpreter.project.coprocessor_compile.{CoprocessorSpec, compile_program}` (Task 1).
- Produces: `compile_cobol(source, bridge_jar_path, connections, copybook_dirs=None) -> tuple[CobolFrontend, LinkedProgram]` — signature unchanged from before this task. Note the return type is still annotated `CobolFrontend`, but `compile_program` actually returns whatever `interpreter.project.cobol_compile.compile_cobol` returns for its frontend slot (unchanged from today — this was already true before this task, since squall's helper already delegated to `_rd_compile_cobol`).

- [ ] **Step 1: Bump `vendor/red-dragon` to Task 1's commit**

```bash
cd vendor/red-dragon
git fetch origin
git checkout <task-1-commit-sha>
cd ../..
git add vendor/red-dragon
```

- [ ] **Step 2: Rewrite `compile_cobol` in `tests/integration/squall_cobol_helpers.py`**

Replace the current body (which calls `_rd_compile_cobol` directly) with:

```python
def compile_cobol(
    source: str,
    bridge_jar_path: str,
    connections,
    copybook_dirs: list[Path] | None = None,
) -> tuple[CobolFrontend, LinkedProgram]:
    """Compile a COBOL source string to a LinkedProgram.

    *connections* is the connection registry (name → backend) the program's
    EXEC SQL CONNECT selects from at run time; a run starts disconnected.

    Builds one CoprocessorSpec around a private one-element holder that
    threads the prepass's dclgen field_meta into the SQL strategy —
    compile_program guarantees the prepass runs before make_strategy is
    called — and delegates to RedDragon's shared compile_program
    (interpreter.project.coprocessor_compile), the same composition
    mechanism Cicada and red-dragon-forge use.

    Returns (frontend, linked) so that callers can access frontend.data_layout
    for assertions and pass the LinkedProgram to run_linked.
    """
    from squall.statements import SqlDialectParser
    from interpreter.project.coprocessor_compile import CoprocessorSpec, compile_program

    dirs = copybook_dirs or []
    parser = make_cobol_parser(bridge_jar_path, copybook_dirs=dirs)
    field_meta_holder: list = [{}]

    def _prepass(src: str) -> str:
        result = apply_sql_prepass(src, dirs)
        field_meta_holder[0] = result.field_meta
        return result.source

    spec = CoprocessorSpec(
        name="sql",
        make_strategy=lambda: SqlLoweringStrategy(connections, field_meta_holder[0]),
        source_prepass=_prepass,
        dialect_parser=SqlDialectParser(),
    )
    return compile_program(source.encode("utf-8"), parser, [spec])
```

Note: `source_prepass` in `CoprocessorSpec` is `Callable[[str], str]` and
receives/returns the RAW STRING (not encoded bytes) — `compile_program`
decodes `source` to `str` once up front and encodes the composed result back
to bytes once at the end, so `_prepass` here takes and returns `str` exactly
like `apply_sql_prepass`'s own `result.source` field already is. This
matches `CoprocessorSpec.source_prepass`'s contract exactly — no encoding
changes needed inside `_prepass` itself.

- [ ] **Step 3: Run the full squall suite**

```bash
export SQUALL_DB2_DSN="DATABASE=MOJO;HOSTNAME=localhost;PORT=15000;PROTOCOL=TCPIP;UID=db2inst1;PWD=squalltest123"
export SQUALL_DB2_DSN2="DATABASE=MOJO2;HOSTNAME=localhost;PORT=15000;PROTOCOL=TCPIP;UID=db2inst1;PWD=squalltest123"
export PROLEAP_BRIDGE_JAR=$PWD/vendor/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
uv run --no-sync python -m pytest tests/ -q
```

Expected: 271 passed, 1 skipped (same as before this task)

If any `db2` test fails with a communication error (`SQL30081N`), the Db2
container's DRDA listener needs a routine restart — this is NOT a
regression from this task:

```bash
docker exec squall-db2 su - db2inst1 -c 'db2start'
```

Then re-run the suite.

- [ ] **Step 4: Commit and push**

```bash
git add tests/integration/squall_cobol_helpers.py vendor/red-dragon
git commit -m "refactor(test-helpers): delegate compile_cobol to RedDragon's shared compile_program"
git push origin main
```

Record the resulting commit SHA — needed for Task 4's pin bump.

---

### Task 4: red-dragon-forge — delete old files, rewire consumers, bump all pins

**Files:**
- Delete: `red_dragon_forge/coprocessor.py`
- Delete: `red_dragon_forge/compile.py`
- Delete: `tests/integration/test_coprocessor.py`
- Delete: `tests/integration/test_compile_program.py`
- Modify: `red_dragon_forge/adapters/cics.py`
- Modify: `red_dragon_forge/adapters/sql.py`
- Modify: `red_dragon_forge/run.py`
- Modify: `tests/integration/test_cics_adapter.py`
- Modify: `tests/integration/test_cics_sql_composition.py`
- Modify: `tests/integration/test_inqcust_e2e.py`
- Modify: `tests/integration/test_sql_adapter.py`
- Modify: `tests/integration/test_run_program.py`
- Modify: `vendor/red-dragon`, `vendor/cicada`, `vendor/squall` (top-level pins) and `vendor/cicada/vendor/red-dragon`, `vendor/squall/vendor/red-dragon` (nested pins)

**Interfaces:**
- Consumes: `interpreter.project.coprocessor_compile.{CoprocessorSpec, compile_program}` (Task 1, via the bumped `vendor/red-dragon`).

- [ ] **Step 1: Bump all three top-level vendor pins**

```bash
cd vendor/red-dragon && git fetch origin && git checkout <task-1-commit-sha> && cd ../..
cd vendor/cicada && git fetch origin && git checkout <task-2-commit-sha> && cd ../..
cd vendor/squall && git fetch origin && git checkout <task-3-commit-sha> && cd ../..
```

- [ ] **Step 2: Bump the two nested `vendor/red-dragon` copies to match**

```bash
cd vendor/cicada/vendor/red-dragon && git fetch origin && git checkout <task-1-commit-sha> && cd ../../..
cd vendor/squall/vendor/red-dragon && git fetch origin && git checkout <task-1-commit-sha> && cd ../../..
```

- [ ] **Step 3: Verify pin alignment**

Run: `uv run --no-sync python scripts/check_red_dragon_pin.py`
Expected: `OK: all three RedDragon pins match.`

- [ ] **Step 4: Delete the old files**

```bash
rm red_dragon_forge/coprocessor.py red_dragon_forge/compile.py
rm tests/integration/test_coprocessor.py tests/integration/test_compile_program.py
```

- [ ] **Step 5: Rewire `red_dragon_forge/adapters/cics.py`**

Change the import:

```python
from interpreter.project.coprocessor_compile import CoprocessorSpec
```

(replacing `from red_dragon_forge.coprocessor import CoprocessorSpec`). No
other change to this file — `build_cics_spec`'s body is untouched.

- [ ] **Step 6: Rewire `red_dragon_forge/adapters/sql.py`**

Change the import:

```python
from interpreter.project.coprocessor_compile import CoprocessorSpec
```

(replacing `from red_dragon_forge.coprocessor import CoprocessorSpec`). No
other change to this file — `build_sql_spec`'s body is untouched.

- [ ] **Step 7: Rewire `red_dragon_forge/run.py`**

Change the import:

```python
from interpreter.project.coprocessor_compile import CoprocessorSpec
```

(replacing `from red_dragon_forge.coprocessor import CoprocessorSpec`). No
other change to this file.

- [ ] **Step 8: Rewire the 5 test files' imports**

In each of `tests/integration/test_cics_adapter.py`,
`tests/integration/test_cics_sql_composition.py`,
`tests/integration/test_inqcust_e2e.py`, `tests/integration/test_sql_adapter.py`:

Replace:
```python
from red_dragon_forge.compile import compile_program
```
with:
```python
from interpreter.project.coprocessor_compile import compile_program
```

In `tests/integration/test_run_program.py`:

Replace:
```python
from red_dragon_forge.coprocessor import CoprocessorSpec
```
with:
```python
from interpreter.project.coprocessor_compile import CoprocessorSpec
```

- [ ] **Step 9: Run the full red-dragon-forge suite**

```bash
export PROLEAP_BRIDGE_JAR=$PWD/vendor/red-dragon/proleap-bridge/target/proleap-bridge-0.1.0-shaded.jar
export SQUALL_DB2_DSN="DATABASE=MOJO;HOSTNAME=localhost;PORT=15000;PROTOCOL=TCPIP;UID=db2inst1;PWD=squalltest123"
uv run --no-sync python -m pytest tests/ -v
```

Expected: 11 passed (same 11 tests as before this task, including the live-Db2
`test_inqcust_found_and_not_found` and the CEEDAYS proof test
`test_cics_program_calling_le_service_stub_resolves`)

If any `db2`-backed test fails with a communication error, restart Db2
(`docker exec squall-db2 su - db2inst1 -c 'db2start'`) and re-run — not a
regression from this task.

- [ ] **Step 10: Commit**

```bash
git add -A -- red_dragon_forge tests vendor
git commit -m "refactor: delete red_dragon_forge's own CoprocessorSpec/compile_program, import from RedDragon"
```

(No push — this repo has no remote.)

---

## Final Verification

After all four tasks: re-run each repo's full suite one more time in
sequence (RedDragon, cicada, squall, red-dragon-forge) to confirm no
cross-repo drift, and re-run `scripts/check_red_dragon_pin.py` in
red-dragon-forge one final time.
